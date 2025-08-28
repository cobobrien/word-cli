"""
Edit Planner Agent for complex document editing operations.

This agent analyzes editing requests and creates detailed execution plans
for complex multi-step operations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
import re

from ..tools import ToolCall
from ...core.document_model import DocumentModel
from ...core.ast_handler import ASTHandler
from ...version.version_control import DocumentChange, ChangeType


class EditComplexity(Enum):
    """Complexity levels for edit operations."""
    SIMPLE = "simple"      # Single operation, no dependencies
    MODERATE = "moderate"   # Multiple operations, some dependencies
    COMPLEX = "complex"     # Many operations, complex dependencies
    RISKY = "risky"        # Operations that could damage document structure


class EditType(Enum):
    """Types of edit operations."""
    CONTENT_EDIT = "content_edit"
    STRUCTURE_CHANGE = "structure_change"
    STYLE_MODIFICATION = "style_modification"
    CROSS_REFERENCE = "cross_reference"
    BATCH_OPERATION = "batch_operation"


@dataclass
class EditStep:
    """A single step in an edit plan."""
    
    step_id: str
    description: str
    tool_call: ToolCall
    dependencies: List[str] = field(default_factory=list)
    validation_required: bool = True
    rollback_info: Optional[Dict[str, Any]] = None


@dataclass
class EditPlan:
    """Complete plan for executing an edit operation."""
    
    plan_id: str
    description: str
    complexity: EditComplexity
    edit_type: EditType
    steps: List[EditStep] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)
    estimated_changes: int = 0
    requires_confirmation: bool = False


class EditPlannerAgent:
    """
    Agent responsible for planning complex document edits.
    
    Analyzes user requests and creates detailed execution plans
    that can be safely executed by the tool system.
    """
    
    def __init__(self):
        self.complexity_thresholds = {
            'simple_operations': ['find_text', 'get_paragraph', 'read_document'],
            'moderate_operations': ['edit_paragraph', 'insert_text', 'delete_paragraph'],
            'complex_operations': ['replace_all', 'restructure_document'],
            'risky_operations': ['delete_section', 'merge_documents']
        }
    
    def analyze_request(self, user_request: str, document: DocumentModel) -> EditPlan:
        """
        Analyze a user request and create an edit plan.
        
        Args:
            user_request: The user's editing request
            document: Current document model
            
        Returns:
            EditPlan with steps to execute the request
        """
        # Parse the request to understand intent
        intent = self._parse_intent(user_request)
        
        # Determine edit type and complexity
        edit_type = self._classify_edit_type(intent)
        complexity = self._assess_complexity(intent, document)
        
        # Create the plan
        plan = EditPlan(
            plan_id=self._generate_plan_id(),
            description=f"Execute: {user_request}",
            complexity=complexity,
            edit_type=edit_type,
            requires_confirmation=complexity in [EditComplexity.COMPLEX, EditComplexity.RISKY]
        )
        
        # Generate steps based on intent
        if edit_type == EditType.CONTENT_EDIT:
            self._plan_content_edit(plan, intent, document)
        elif edit_type == EditType.STRUCTURE_CHANGE:
            self._plan_structure_change(plan, intent, document)
        elif edit_type == EditType.CROSS_REFERENCE:
            self._plan_cross_reference(plan, intent, document)
        elif edit_type == EditType.BATCH_OPERATION:
            self._plan_batch_operation(plan, intent, document)
        else:
            self._plan_generic_edit(plan, intent, document)
        
        # Add validation and safety checks
        self._add_safety_checks(plan, document)
        
        return plan
    
    def _parse_intent(self, user_request: str) -> Dict[str, Any]:
        """Parse user request to extract intent and parameters."""
        intent = {
            'action': None,
            'target': None,
            'content': None,
            'source': None,
            'modifiers': [],
            'raw_request': user_request
        }
        
        request_lower = user_request.lower()
        
        # Identify action verbs
        action_patterns = {
            'edit': r'\b(edit|change|modify|update|revise)\b',
            'insert': r'\b(insert|add|include|append)\b',
            'delete': r'\b(delete|remove|eliminate)\b',
            'replace': r'\b(replace|substitute|swap)\b',
            'find': r'\b(find|locate|search)\b',
            'copy': r'\b(copy|duplicate|clone)\b',
            'move': r'\b(move|relocate|transfer)\b',
            'reference': r'\b(reference|cite|link)\b'
        }
        
        for action, pattern in action_patterns.items():
            if re.search(pattern, request_lower):
                intent['action'] = action
                break
        
        # Extract targets (paragraphs, sections, clauses, etc.)
        target_patterns = {
            'paragraph': r'\bparagraph\s+(\d+)\b',
            'section': r'\bsection\s+([^\s,]+)\b',
            'clause': r'\bclause\s+([^\s,]+)\b',
            'heading': r'\bheading\s+(.+?)(?:\s+to|\s+with|\s*$)',
            'text': r'"([^"]+)"'
        }
        
        for target_type, pattern in target_patterns.items():
            match = re.search(pattern, request_lower)
            if match:
                intent['target'] = {
                    'type': target_type,
                    'value': match.group(1)
                }
                break
        
        # Extract content (what to change to)
        content_patterns = [
            r'\bto\s+"([^"]+)"',
            r'\bwith\s+"([^"]+)"',
            r'\bto\s+(.+?)(?:\s+from|\s*$)',
        ]
        
        for pattern in content_patterns:
            match = re.search(pattern, user_request)
            if match:
                intent['content'] = match.group(1).strip()
                break
        
        # Extract source references (from other documents)
        source_patterns = [
            r'\bfrom\s+([^\s]+\.docx)\b',
            r'\bfrom\s+document\s+"([^"]+)"',
            r'\bin\s+([^\s]+\.docx)\b'
        ]
        
        for pattern in source_patterns:
            match = re.search(pattern, request_lower):
            if match:
                intent['source'] = match.group(1)
                break
        
        return intent
    
    def _classify_edit_type(self, intent: Dict[str, Any]) -> EditType:
        """Classify the type of edit operation."""
        action = intent.get('action', '').lower()
        
        if intent.get('source'):
            return EditType.CROSS_REFERENCE
        
        structure_actions = ['move', 'restructure', 'organize']
        if action in structure_actions:
            return EditType.STRUCTURE_CHANGE
        
        batch_indicators = ['all', 'every', 'throughout']
        if any(indicator in intent['raw_request'].lower() for indicator in batch_indicators):
            return EditType.BATCH_OPERATION
        
        style_indicators = ['format', 'style', 'font', 'bold', 'italic']
        if any(indicator in intent['raw_request'].lower() for indicator in style_indicators):
            return EditType.STYLE_MODIFICATION
        
        return EditType.CONTENT_EDIT
    
    def _assess_complexity(self, intent: Dict[str, Any], document: DocumentModel) -> EditComplexity:
        """Assess the complexity of the requested operation."""
        factors = {
            'multiple_targets': 0,
            'cross_document': 0,
            'structural_changes': 0,
            'batch_operations': 0,
            'risky_operations': 0
        }
        
        # Check for multiple targets
        if 'all' in intent['raw_request'].lower() or 'every' in intent['raw_request'].lower():
            factors['multiple_targets'] = 2
        
        # Check for cross-document operations
        if intent.get('source'):
            factors['cross_document'] = 2
        
        # Check for structural changes
        action = intent.get('action', '').lower()
        if action in ['move', 'restructure', 'delete'] and intent.get('target', {}).get('type') in ['section', 'heading']:
            factors['structural_changes'] = 3
        
        # Check for batch operations
        if 'replace' in action and ('all' in intent['raw_request'].lower() or 'throughout' in intent['raw_request'].lower()):
            factors['batch_operations'] = 2
        
        # Check for risky operations
        if action == 'delete' and intent.get('target', {}).get('type') in ['section', 'heading']:
            factors['risky_operations'] = 4
        
        total_complexity = sum(factors.values())
        
        if total_complexity >= 4:
            return EditComplexity.RISKY
        elif total_complexity >= 3:
            return EditComplexity.COMPLEX
        elif total_complexity >= 1:
            return EditComplexity.MODERATE
        else:
            return EditComplexity.SIMPLE
    
    def _plan_content_edit(self, plan: EditPlan, intent: Dict[str, Any], document: DocumentModel) -> None:
        """Plan a content editing operation."""
        action = intent.get('action', '').lower()
        target = intent.get('target', {})
        content = intent.get('content', '')
        
        if action == 'edit' and target.get('type') == 'paragraph':
            # Edit specific paragraph
            step = EditStep(
                step_id="edit_paragraph",
                description=f"Edit paragraph {target['value']}",
                tool_call=ToolCall(
                    id="edit_1",
                    name="edit_paragraph",
                    parameters={
                        "index": int(target['value']),
                        "new_text": content
                    }
                )
            )
            plan.steps.append(step)
            plan.estimated_changes = 1
        
        elif action == 'replace':
            # Find and replace operation
            # First find what to replace
            find_step = EditStep(
                step_id="find_target",
                description=f"Find text to replace",
                tool_call=ToolCall(
                    id="find_1",
                    name="find_text",
                    parameters={"query": target.get('value', '')}
                ),
                validation_required=False
            )
            plan.steps.append(find_step)
            
            # Then replace it
            replace_step = EditStep(
                step_id="replace_text", 
                description=f"Replace text with new content",
                tool_call=ToolCall(
                    id="replace_1",
                    name="replace_all",
                    parameters={
                        "find": target.get('value', ''),
                        "replace": content
                    }
                ),
                dependencies=["find_target"]
            )
            plan.steps.append(replace_step)
            plan.estimated_changes = 5  # Could affect multiple paragraphs
    
    def _plan_structure_change(self, plan: EditPlan, intent: Dict[str, Any], document: DocumentModel) -> None:
        """Plan a structural change operation."""
        plan.risks.append("Structural changes may affect document flow and formatting")
        
        # Add steps for structural changes
        validation_step = EditStep(
            step_id="validate_structure",
            description="Validate document structure before changes",
            tool_call=ToolCall(
                id="validate_1",
                name="validate_document",
                parameters={}
            )
        )
        plan.steps.append(validation_step)
    
    def _plan_cross_reference(self, plan: EditPlan, intent: Dict[str, Any], document: DocumentModel) -> None:
        """Plan a cross-reference operation."""
        source = intent.get('source', '')
        target = intent.get('target', {})
        
        # Step 1: Open reference document
        open_step = EditStep(
            step_id="open_reference",
            description=f"Open reference document {source}",
            tool_call=ToolCall(
                id="open_1",
                name="open_reference_document",
                parameters={"path": source}
            ),
            validation_required=False
        )
        plan.steps.append(open_step)
        
        # Step 2: Find content in reference document
        find_step = EditStep(
            step_id="find_reference_content",
            description=f"Find {target.get('value', '')} in reference document",
            tool_call=ToolCall(
                id="find_2",
                name="find_text",
                parameters={"query": target.get('value', '')}
            ),
            dependencies=["open_reference"],
            validation_required=False
        )
        plan.steps.append(find_step)
        
        plan.prerequisites.append(f"Reference document {source} must exist and be accessible")
        plan.estimated_changes = 1
    
    def _plan_batch_operation(self, plan: EditPlan, intent: Dict[str, Any], document: DocumentModel) -> None:
        """Plan a batch operation."""
        plan.risks.append("Batch operations affect multiple parts of the document")
        plan.requires_confirmation = True
        
        # Use replace_all for batch text changes
        if intent.get('action') == 'replace':
            step = EditStep(
                step_id="batch_replace",
                description="Replace all instances throughout document",
                tool_call=ToolCall(
                    id="batch_1",
                    name="replace_all",
                    parameters={
                        "find": intent.get('target', {}).get('value', ''),
                        "replace": intent.get('content', '')
                    }
                )
            )
            plan.steps.append(step)
            plan.estimated_changes = 10  # Could be many changes
    
    def _plan_generic_edit(self, plan: EditPlan, intent: Dict[str, Any], document: DocumentModel) -> None:
        """Plan a generic edit operation when specific planning isn't available."""
        # Start with document analysis
        analyze_step = EditStep(
            step_id="analyze_document",
            description="Analyze document to understand current state",
            tool_call=ToolCall(
                id="analyze_1",
                name="summarize_document",
                parameters={}
            ),
            validation_required=False
        )
        plan.steps.append(analyze_step)
        
        plan.risks.append("Generic edit plan may require user guidance during execution")
    
    def _add_safety_checks(self, plan: EditPlan, document: DocumentModel) -> None:
        """Add safety and validation checks to the plan."""
        if plan.complexity in [EditComplexity.COMPLEX, EditComplexity.RISKY]:
            # Add final validation step
            final_validation = EditStep(
                step_id="final_validation",
                description="Validate document integrity after all changes",
                tool_call=ToolCall(
                    id="final_validate",
                    name="validate_document", 
                    parameters={}
                ),
                dependencies=[step.step_id for step in plan.steps if step.step_id != "final_validation"]
            )
            plan.steps.append(final_validation)
        
        # Add rollback information
        for step in plan.steps:
            if step.tool_call.name in ['edit_paragraph', 'replace_all', 'delete_paragraph']:
                step.rollback_info = {
                    'requires_version_restore': True,
                    'backup_needed': True
                }
    
    def _generate_plan_id(self) -> str:
        """Generate a unique plan ID."""
        import uuid
        return f"plan_{uuid.uuid4().hex[:8]}"
    
    def optimize_plan(self, plan: EditPlan) -> EditPlan:
        """Optimize an edit plan for efficiency."""
        # Combine similar operations
        optimized_steps = []
        
        # Group consecutive similar operations
        current_group = []
        current_operation = None
        
        for step in plan.steps:
            operation_type = step.tool_call.name
            
            if operation_type == current_operation and operation_type in ['edit_paragraph', 'insert_text']:
                current_group.append(step)
            else:
                # Process current group
                if current_group:
                    if len(current_group) > 1:
                        # Create batch operation
                        batch_step = self._create_batch_step(current_group)
                        optimized_steps.append(batch_step)
                    else:
                        optimized_steps.extend(current_group)
                
                # Start new group
                current_group = [step]
                current_operation = operation_type
        
        # Process final group
        if current_group:
            if len(current_group) > 1:
                batch_step = self._create_batch_step(current_group)
                optimized_steps.append(batch_step)
            else:
                optimized_steps.extend(current_group)
        
        plan.steps = optimized_steps
        return plan
    
    def _create_batch_step(self, steps: List[EditStep]) -> EditStep:
        """Create a batch step from multiple similar steps."""
        operation_type = steps[0].tool_call.name
        
        return EditStep(
            step_id=f"batch_{operation_type}",
            description=f"Batch {operation_type} operation ({len(steps)} items)",
            tool_call=ToolCall(
                id=f"batch_{len(steps)}",
                name=f"batch_{operation_type}",
                parameters={
                    "operations": [step.tool_call.parameters for step in steps]
                }
            ),
            dependencies=[],
            validation_required=True
        )