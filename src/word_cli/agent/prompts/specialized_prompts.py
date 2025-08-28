"""
Specialized prompts for specific agent tasks.
"""

from typing import Dict, Any, List


def get_edit_analysis_prompt(user_request: str, document_context: Dict[str, Any]) -> str:
    """
    Get prompt for analyzing complex edit requests.
    
    Args:
        user_request: The user's editing request
        document_context: Current document context and stats
        
    Returns:
        Prompt for edit analysis
    """
    return f"""Analyze this editing request and create a detailed execution plan:

USER REQUEST: "{user_request}"

DOCUMENT CONTEXT:
- Word count: {document_context.get('word_count', 'Unknown')}
- Paragraphs: {document_context.get('paragraph_count', 'Unknown')}
- Headings: {document_context.get('heading_count', 0)}
- Structure: {document_context.get('structure', 'Unknown')}

ANALYSIS FRAMEWORK:
1. **Intent Understanding**: What is the user really trying to achieve?
2. **Scope Assessment**: Which parts of the document are affected?
3. **Dependency Analysis**: What needs to happen in what order?
4. **Risk Assessment**: What could go wrong? What should be preserved?
5. **Strategy Selection**: What's the most efficient and safe approach?

Create a step-by-step execution plan that:
- Breaks complex requests into atomic operations
- Identifies all necessary information gathering steps
- Plans edits in logical order
- Includes validation checkpoints
- Considers rollback scenarios

Output your analysis and recommended approach."""


def get_validation_prompt(changes_made: List[Dict[str, Any]], document_stats: Dict[str, Any]) -> str:
    """
    Get prompt for post-edit validation.
    
    Args:
        changes_made: List of changes that were made
        document_stats: Current document statistics
        
    Returns:
        Prompt for validation
    """
    changes_summary = "\n".join([
        f"- {change.get('type', 'Unknown')}: {change.get('description', 'No description')}"
        for change in changes_made
    ])
    
    return f"""Validate the changes made to the document:

CHANGES MADE:
{changes_summary}

CURRENT DOCUMENT STATE:
- Word count: {document_stats.get('word_count', 'Unknown')}
- Paragraphs: {document_stats.get('paragraph_count', 'Unknown')}
- Modified: {'Yes' if document_stats.get('is_modified', False) else 'No'}

VALIDATION CHECKLIST:
1. **Content Integrity**: Are the changes what the user requested?
2. **Document Structure**: Is the document still well-formed?
3. **Formatting Preservation**: Has formatting been maintained appropriately?
4. **Logical Flow**: Does the document still read coherently?
5. **Completeness**: Are all requested changes complete?

Please provide:
- Validation summary (✅ passed / ❌ issues found)
- Any issues detected and suggested fixes
- Confirmation that the user's request has been fulfilled"""


def get_cross_document_prompt(operation_type: str, source_doc: str, target_element: str) -> str:
    """
    Get prompt for cross-document operations.
    
    Args:
        operation_type: Type of operation (reference, copy, etc.)
        source_doc: Source document name/path
        target_element: What to find/copy from source
        
    Returns:
        Prompt for cross-document operations
    """
    return f"""Perform cross-document operation:

OPERATION: {operation_type}
SOURCE DOCUMENT: {source_doc}
TARGET ELEMENT: "{target_element}"

PROCESS:
1. **Document Access**: Open and analyze the source document
2. **Element Location**: Find the specified element using semantic search
3. **Content Extraction**: Extract relevant content with context
4. **Integration Planning**: Determine how to integrate into current document
5. **Execution**: Perform the operation with proper formatting

Consider:
- Maintain consistency in style and formatting
- Preserve references and context where appropriate
- Ensure the integration makes sense in the target document
- Handle cases where the element might not be found

Provide clear feedback on what was found and how it will be integrated."""


def get_semantic_search_prompt(search_query: str, search_context: str = "") -> str:
    """
    Get prompt for semantic search operations.
    
    Args:
        search_query: What the user is looking for
        search_context: Additional context about the search
        
    Returns:
        Prompt for semantic search
    """
    return f"""Perform intelligent semantic search:

SEARCH QUERY: "{search_query}"
CONTEXT: {search_context}

SEARCH STRATEGY:
1. **Literal Matching**: Look for exact text matches first
2. **Semantic Matching**: Find content with similar meaning
3. **Structural Analysis**: Consider document organization (headings, sections)
4. **Context Relevance**: Prioritize results by relevance to user intent

Consider these search approaches:
- Direct text search for specific phrases
- Heading and section title analysis
- Content theme and topic matching
- Paragraph and section context

Provide search results with:
- Location information (paragraph numbers, sections)
- Content previews showing context
- Relevance ranking
- Suggestions if exact matches aren't found"""


def get_batch_operation_prompt(operations: List[str], safety_level: str = "normal") -> str:
    """
    Get prompt for batch operations.
    
    Args:
        operations: List of operations to perform
        safety_level: Level of safety checks (strict, normal, permissive)
        
    Returns:
        Prompt for batch operations
    """
    operations_list = "\n".join([f"{i+1}. {op}" for i, op in enumerate(operations)])
    
    safety_guidance = {
        "strict": "Validate each operation before proceeding. Stop if any validation fails.",
        "normal": "Validate operations but continue with safe operations if some fail.",
        "permissive": "Proceed with all operations, reporting issues at the end."
    }
    
    return f"""Execute batch operations with {safety_level} safety level:

OPERATIONS TO PERFORM:
{operations_list}

SAFETY LEVEL: {safety_level}
GUIDANCE: {safety_guidance.get(safety_level, 'Normal validation')}

BATCH EXECUTION PLAN:
1. **Pre-validation**: Check all operations for potential conflicts
2. **Dependency Resolution**: Order operations to handle dependencies
3. **Atomic Execution**: Each operation should complete or rollback cleanly
4. **Progress Tracking**: Report progress and any issues
5. **Final Validation**: Confirm all intended changes were made

Execute the operations systematically, providing clear progress updates and handling any errors gracefully."""