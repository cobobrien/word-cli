"""
Validation Agent for ensuring document integrity and edit safety.

This agent validates documents before and after edits, ensuring that
changes don't break document structure or introduce errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
import re

from ...core.document_model import DocumentModel
from ...core.ast_handler import ASTHandler, Position
from ...version.version_control import DocumentChange, ChangeType


class ValidationLevel(Enum):
    """Levels of validation strictness."""
    PERMISSIVE = "permissive"  # Basic checks only
    NORMAL = "normal"          # Standard validation
    STRICT = "strict"          # Comprehensive validation


class IssueType(Enum):
    """Types of validation issues."""
    CRITICAL = "critical"      # Must be fixed
    WARNING = "warning"        # Should be reviewed
    INFO = "info"             # Informational only


@dataclass
class ValidationIssue:
    """Represents a validation issue found in the document."""
    
    issue_type: IssueType
    category: str
    description: str
    location: Optional[Position] = None
    suggested_fix: Optional[str] = None
    auto_fixable: bool = False


@dataclass
class ValidationResult:
    """Result of a document validation operation."""
    
    passed: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    summary: str = ""
    recommendations: List[str] = field(default_factory=list)
    
    @property
    def critical_issues(self) -> List[ValidationIssue]:
        """Get all critical issues."""
        return [issue for issue in self.issues if issue.issue_type == IssueType.CRITICAL]
    
    @property
    def warnings(self) -> List[ValidationIssue]:
        """Get all warning issues."""
        return [issue for issue in self.issues if issue.issue_type == IssueType.WARNING]
    
    @property
    def info_items(self) -> List[ValidationIssue]:
        """Get all informational items."""
        return [issue for issue in self.issues if issue.issue_type == IssueType.INFO]


class ValidationAgent:
    """
    Agent responsible for validating document integrity and edit safety.
    
    Performs comprehensive validation of Word documents to ensure
    structural integrity and content quality.
    """
    
    def __init__(self, validation_level: ValidationLevel = ValidationLevel.NORMAL):
        self.validation_level = validation_level
        self.validation_rules = self._initialize_validation_rules()
    
    def _initialize_validation_rules(self) -> Dict[str, Any]:
        """Initialize validation rules based on validation level."""
        base_rules = {
            'check_ast_structure': True,
            'check_content_integrity': True,
            'check_heading_hierarchy': True,
            'check_empty_paragraphs': True,
            'check_broken_references': True
        }
        
        if self.validation_level == ValidationLevel.STRICT:
            base_rules.update({
                'check_spelling': True,
                'check_grammar': False,  # Would need external service
                'check_style_consistency': True,
                'check_formatting_consistency': True,
                'check_cross_references': True
            })
        elif self.validation_level == ValidationLevel.NORMAL:
            base_rules.update({
                'check_style_consistency': True,
                'check_formatting_consistency': False
            })
        
        return base_rules
    
    def validate_document(self, document: DocumentModel) -> ValidationResult:
        """
        Perform comprehensive document validation.
        
        Args:
            document: Document to validate
            
        Returns:
            ValidationResult with issues and recommendations
        """
        issues = []
        
        # Core structural validation
        issues.extend(self._validate_ast_structure(document))
        issues.extend(self._validate_content_integrity(document))
        
        # Content-specific validation
        if self.validation_rules.get('check_heading_hierarchy'):
            issues.extend(self._validate_heading_hierarchy(document))
        
        if self.validation_rules.get('check_empty_paragraphs'):
            issues.extend(self._validate_empty_paragraphs(document))
        
        if self.validation_rules.get('check_style_consistency'):
            issues.extend(self._validate_style_consistency(document))
        
        # Advanced validation for strict mode
        if self.validation_level == ValidationLevel.STRICT:
            issues.extend(self._validate_advanced_features(document))
        
        # Generate summary
        critical_count = len([i for i in issues if i.issue_type == IssueType.CRITICAL])
        warning_count = len([i for i in issues if i.issue_type == IssueType.WARNING])
        
        if critical_count > 0:
            passed = False
            summary = f"Validation FAILED: {critical_count} critical issues found"
        elif warning_count > 0:
            passed = True
            summary = f"Validation PASSED with {warning_count} warnings"
        else:
            passed = True
            summary = "Validation PASSED: No issues found"
        
        recommendations = self._generate_recommendations(issues)
        
        return ValidationResult(
            passed=passed,
            issues=issues,
            summary=summary,
            recommendations=recommendations
        )
    
    def _validate_ast_structure(self, document: DocumentModel) -> List[ValidationIssue]:
        """Validate the AST structure integrity."""
        issues = []
        
        if not document.pandoc_ast.blocks:
            issues.append(ValidationIssue(
                issue_type=IssueType.CRITICAL,
                category="AST Structure",
                description="Document has no content blocks",
                suggested_fix="Add content to the document"
            ))
            return issues
        
        handler = ASTHandler(document.pandoc_ast)
        ast_issues = handler.validate_structure()
        
        for issue_desc in ast_issues:
            issues.append(ValidationIssue(
                issue_type=IssueType.CRITICAL,
                category="AST Structure",
                description=issue_desc,
                suggested_fix="Fix AST structure issues"
            ))
        
        return issues
    
    def _validate_content_integrity(self, document: DocumentModel) -> List[ValidationIssue]:
        """Validate content integrity and completeness."""
        issues = []
        handler = ASTHandler(document.pandoc_ast)
        
        # Check for corrupted or malformed blocks
        for i, block in enumerate(document.pandoc_ast.blocks):
            block_type = block.get('t')
            if not block_type:
                issues.append(ValidationIssue(
                    issue_type=IssueType.CRITICAL,
                    category="Content Integrity",
                    description=f"Block {i+1} has no type information",
                    location=Position(block_index=i),
                    suggested_fix="Remove or fix corrupted block"
                ))
            
            # Check block content structure
            content = block.get('c')
            if content is None and block_type not in ['Null', 'HorizontalRule']:
                issues.append(ValidationIssue(
                    issue_type=IssueType.WARNING,
                    category="Content Integrity", 
                    description=f"Block {i+1} ({block_type}) has no content",
                    location=Position(block_index=i)
                ))
        
        return issues
    
    def _validate_heading_hierarchy(self, document: DocumentModel) -> List[ValidationIssue]:
        """Validate heading hierarchy and structure."""
        issues = []
        handler = ASTHandler(document.pandoc_ast)
        
        headings = handler.find_headings()
        if not headings:
            return issues  # No headings to validate
        
        previous_level = 0
        for pos, heading in headings:
            level = heading.get('c', [None])[0]
            if level is None:
                continue
            
            # Check for level jumps (skipping levels)
            if level > previous_level + 1:
                issues.append(ValidationIssue(
                    issue_type=IssueType.WARNING,
                    category="Heading Hierarchy",
                    description=f"Heading level jumps from {previous_level} to {level} at paragraph {pos.block_index + 1}",
                    location=pos,
                    suggested_fix=f"Consider using level {previous_level + 1} instead"
                ))
            
            # Check for empty headings
            heading_text = handler._extract_text_from_block(heading).strip()
            if not heading_text:
                issues.append(ValidationIssue(
                    issue_type=IssueType.WARNING,
                    category="Heading Hierarchy",
                    description=f"Empty heading at paragraph {pos.block_index + 1}",
                    location=pos,
                    suggested_fix="Add descriptive text to heading or remove it"
                ))
            
            previous_level = level
        
        return issues
    
    def _validate_empty_paragraphs(self, document: DocumentModel) -> List[ValidationIssue]:
        """Validate and identify empty or whitespace-only paragraphs."""
        issues = []
        handler = ASTHandler(document.pandoc_ast)
        
        for i, block in enumerate(document.pandoc_ast.blocks):
            if block.get('t') in ['Para', 'Plain']:
                content = handler._extract_text_from_block(block).strip()
                
                if not content:
                    issues.append(ValidationIssue(
                        issue_type=IssueType.INFO,
                        category="Content Quality",
                        description=f"Empty paragraph at position {i + 1}",
                        location=Position(block_index=i),
                        suggested_fix="Remove empty paragraph or add content",
                        auto_fixable=True
                    ))
                elif len(content) < 3:  # Very short content
                    issues.append(ValidationIssue(
                        issue_type=IssueType.INFO,
                        category="Content Quality",
                        description=f"Very short paragraph at position {i + 1}: '{content}'",
                        location=Position(block_index=i)
                    ))
        
        return issues
    
    def _validate_style_consistency(self, document: DocumentModel) -> List[ValidationIssue]:
        """Validate style consistency throughout the document."""
        issues = []
        
        # Check for consistent heading styles
        styles = document.word_metadata.styles
        if not styles:
            issues.append(ValidationIssue(
                issue_type=IssueType.WARNING,
                category="Style Consistency",
                description="No style information available",
                suggested_fix="Ensure document has proper style definitions"
            ))
        
        return issues
    
    def _validate_advanced_features(self, document: DocumentModel) -> List[ValidationIssue]:
        """Perform advanced validation (strict mode only)."""
        issues = []
        
        # Check for potential spell check issues (simplified)
        handler = ASTHandler(document.pandoc_ast)
        
        # Look for common spelling indicators
        spell_indicators = [
            r'\b\w*[aeiou]{3,}\w*\b',  # Multiple consecutive vowels
            r'\b\w*[bcdfghjklmnpqrstvwxyz]{4,}\w*\b',  # Multiple consecutive consonants
        ]
        
        for i, block in enumerate(document.pandoc_ast.blocks):
            text = handler._extract_text_from_block(block)
            
            for pattern in spell_indicators:
                matches = re.findall(pattern, text, re.IGNORECASE)
                if matches:
                    issues.append(ValidationIssue(
                        issue_type=IssueType.INFO,
                        category="Content Quality",
                        description=f"Potential spelling issues at paragraph {i + 1}: {', '.join(set(matches[:3]))}",
                        location=Position(block_index=i),
                        suggested_fix="Review and correct spelling"
                    ))
        
        return issues
    
    def _generate_recommendations(self, issues: List[ValidationIssue]) -> List[str]:
        """Generate recommendations based on found issues."""
        recommendations = []
        
        critical_count = len([i for i in issues if i.issue_type == IssueType.CRITICAL])
        warning_count = len([i for i in issues if i.issue_type == IssueType.WARNING])
        
        if critical_count > 0:
            recommendations.append("Fix critical issues before proceeding with edits")
        
        if warning_count > 3:
            recommendations.append("Consider reviewing document structure and content quality")
        
        # Auto-fixable issues
        auto_fix_count = len([i for i in issues if i.auto_fixable])
        if auto_fix_count > 0:
            recommendations.append(f"Auto-fix {auto_fix_count} simple issues to improve document quality")
        
        return recommendations
    
    def validate_edit_plan(self, plan: Any, document: DocumentModel) -> ValidationResult:
        """
        Validate an edit plan before execution.
        
        Args:
            plan: Edit plan to validate
            document: Target document
            
        Returns:
            ValidationResult for the edit plan
        """
        issues = []
        
        # Check if plan is safe to execute
        if hasattr(plan, 'complexity') and plan.complexity.value == 'risky':
            issues.append(ValidationIssue(
                issue_type=IssueType.WARNING,
                category="Edit Safety",
                description="Edit plan contains risky operations",
                suggested_fix="Consider creating a backup before proceeding"
            ))
        
        # Check plan dependencies
        if hasattr(plan, 'steps'):
            step_ids = {step.step_id for step in plan.steps}
            for step in plan.steps:
                for dep in step.dependencies:
                    if dep not in step_ids:
                        issues.append(ValidationIssue(
                            issue_type=IssueType.CRITICAL,
                            category="Plan Validation",
                            description=f"Step '{step.step_id}' has unresolved dependency '{dep}'",
                            suggested_fix="Fix plan dependencies"
                        ))
        
        passed = len([i for i in issues if i.issue_type == IssueType.CRITICAL]) == 0
        summary = "Edit plan validation passed" if passed else "Edit plan has critical issues"
        
        return ValidationResult(
            passed=passed,
            issues=issues,
            summary=summary
        )
    
    def validate_changes(self, changes: List[DocumentChange], document: DocumentModel) -> ValidationResult:
        """
        Validate a list of changes before applying them.
        
        Args:
            changes: List of changes to validate
            document: Target document
            
        Returns:
            ValidationResult for the changes
        """
        issues = []
        handler = ASTHandler(document.pandoc_ast)
        
        for change in changes:
            # Validate change targets exist
            if change.target_path.startswith('paragraph['):
                # Extract paragraph index
                match = re.search(r'paragraph\[(\d+)\]', change.target_path)
                if match:
                    index = int(match.group(1))
                    if index >= len(document.pandoc_ast.blocks):
                        issues.append(ValidationIssue(
                            issue_type=IssueType.CRITICAL,
                            category="Change Validation",
                            description=f"Change targets non-existent paragraph {index + 1}",
                            suggested_fix="Update change target to valid paragraph"
                        ))
            
            # Validate change types
            if change.change_type == ChangeType.STRUCTURE_CHANGE:
                issues.append(ValidationIssue(
                    issue_type=IssueType.WARNING,
                    category="Change Safety",
                    description="Structural change may affect document formatting",
                    suggested_fix="Review structural changes carefully"
                ))
        
        passed = len([i for i in issues if i.issue_type == IssueType.CRITICAL]) == 0
        summary = f"Change validation: {len(changes)} changes validated"
        
        return ValidationResult(
            passed=passed,
            issues=issues,
            summary=summary
        )
    
    def auto_fix_issues(self, issues: List[ValidationIssue], document: DocumentModel) -> Tuple[List[ValidationIssue], List[str]]:
        """
        Automatically fix issues that can be safely auto-fixed.
        
        Args:
            issues: List of issues to attempt to fix
            document: Document to fix
            
        Returns:
            Tuple of (remaining_issues, fixes_applied)
        """
        remaining_issues = []
        fixes_applied = []
        handler = ASTHandler(document.pandoc_ast)
        
        for issue in issues:
            if not issue.auto_fixable:
                remaining_issues.append(issue)
                continue
            
            if issue.category == "Content Quality" and "Empty paragraph" in issue.description:
                # Remove empty paragraph
                if issue.location:
                    deleted = handler.delete_block(issue.location.block_index)
                    if deleted:
                        fixes_applied.append(f"Removed empty paragraph at position {issue.location.block_index + 1}")
                        document.mark_modified()
                    else:
                        remaining_issues.append(issue)
                else:
                    remaining_issues.append(issue)
            else:
                # Can't auto-fix this issue
                remaining_issues.append(issue)
        
        return remaining_issues, fixes_applied