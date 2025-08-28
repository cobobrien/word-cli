"""
Reference Agent for cross-document operations and external references.

This agent handles operations that involve multiple documents, such as
copying content, referencing clauses from other documents, and maintaining
cross-document consistency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
from pathlib import Path
import json

from ...core.document_model import DocumentModel
from ...core.ast_handler import ASTHandler, Position
from ...converters.docx_to_ast import DocxToASTConverter
from .search_agent import SearchAgent, SearchQuery, SearchType


class ReferenceType(Enum):
    """Types of document references."""
    COPY = "copy"                    # Copy content from another document
    CITATION = "citation"            # Reference another document
    LINK = "link"                   # Create a link to another document
    MERGE = "merge"                 # Merge content from another document
    COMPARISON = "comparison"        # Compare with another document


@dataclass
class DocumentReference:
    """Represents a reference to another document."""
    
    doc_path: Path
    element_id: Optional[str] = None
    element_type: Optional[str] = None  # 'clause', 'section', 'paragraph'
    element_text: Optional[str] = None
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CrossDocumentOperation:
    """Represents an operation involving multiple documents."""
    
    operation_id: str
    operation_type: ReferenceType
    source_doc: Path
    target_element: str
    target_position: Optional[Position] = None
    extracted_content: Optional[str] = None
    integration_plan: List[str] = field(default_factory=list)


class ReferenceAgent:
    """
    Agent responsible for cross-document operations and references.
    
    Handles operations that involve multiple Word documents, such as
    copying content, referencing external clauses, and maintaining
    consistency across document sets.
    """
    
    def __init__(self):
        self.search_agent = SearchAgent()
        self.document_cache: Dict[str, DocumentModel] = {}
        self.reference_patterns = {
            'clause': [
                r'clause\s+(\d+(?:\.\d+)*)',
                r'section\s+(\d+(?:\.\d+)*)',
                r'paragraph\s+(\d+(?:\.\d+)*)'
            ],
            'payment_terms': [
                r'payment\s+terms?',
                r'payment\s+schedule',
                r'billing\s+terms?'
            ],
            'liability': [
                r'liability\s+clause',
                r'limitation\s+of\s+liability',
                r'indemnification'
            ]
        }
    
    def open_reference_document(self, doc_path: Path) -> Optional[DocumentModel]:
        """
        Open and cache a reference document.
        
        Args:
            doc_path: Path to the document to open
            
        Returns:
            DocumentModel if successful, None otherwise
        """
        doc_key = str(doc_path.resolve())
        
        # Check cache first
        if doc_key in self.document_cache:
            return self.document_cache[doc_key]
        
        if not doc_path.exists():
            return None
        
        if not doc_path.suffix.lower() == '.docx':
            return None
        
        try:
            converter = DocxToASTConverter()
            document = converter.convert(doc_path)
            
            # Cache the document
            self.document_cache[doc_key] = document
            
            return document
        except Exception:
            return None
    
    def find_element_in_document(
        self, 
        element_description: str, 
        document: DocumentModel
    ) -> List[DocumentReference]:
        """
        Find a specific element in a document using intelligent search.
        
        Args:
            element_description: Description of what to find
            document: Document to search in
            
        Returns:
            List of matching references
        """
        references = []
        
        # Try different search strategies
        search_strategies = [
            (SearchType.LITERAL, 1.0),
            (SearchType.SEMANTIC, 0.8),
            (SearchType.REGEX, 0.9),
            (SearchType.FUZZY, 0.6)
        ]
        
        for search_type, confidence_boost in search_strategies:
            query = SearchQuery(
                text=element_description,
                search_type=search_type,
                max_results=5,
                min_confidence=0.3
            )
            
            result = self.search_agent.search(query, document)
            
            for match in result.matches:
                # Determine element type
                element_type = self._classify_element_type(match.content, element_description)
                
                ref = DocumentReference(
                    doc_path=document.source_path or Path("unknown"),
                    element_id=f"para_{match.position.block_index}",
                    element_type=element_type,
                    element_text=match.content,
                    confidence=match.confidence * confidence_boost,
                    metadata={
                        'search_type': search_type.value,
                        'position': str(match.position)
                    }
                )
                references.append(ref)
        
        # Remove duplicates and sort by confidence
        unique_refs = self._deduplicate_references(references)
        unique_refs.sort(key=lambda r: r.confidence, reverse=True)
        
        return unique_refs[:3]  # Return top 3 results
    
    def extract_content_for_reference(
        self, 
        reference: DocumentReference, 
        context_size: int = 1
    ) -> str:
        """
        Extract content from a document reference with appropriate context.
        
        Args:
            reference: Document reference to extract from
            context_size: Number of paragraphs before/after to include
            
        Returns:
            Extracted content with context
        """
        if not reference.element_text:
            return ""
        
        # For now, return the element text
        # In a more advanced implementation, would include surrounding context
        content_parts = []
        
        if reference.element_type == 'clause':
            # For clauses, might want to include sub-clauses
            content_parts.append(f"[{reference.element_type.title()}]")
        
        content_parts.append(reference.element_text)
        
        return "\n".join(content_parts)
    
    def create_cross_reference_text(
        self, 
        reference: DocumentReference, 
        reference_style: str = "formal"
    ) -> str:
        """
        Create appropriate cross-reference text for inclusion in a document.
        
        Args:
            reference: Document reference
            reference_style: Style of reference (formal, informal, citation)
            
        Returns:
            Formatted reference text
        """
        doc_name = reference.doc_path.stem if reference.doc_path else "referenced document"
        
        if reference_style == "formal":
            if reference.element_type and reference.element_id:
                return f"as specified in {reference.element_type} {reference.element_id} of {doc_name}"
            else:
                return f"as specified in {doc_name}"
        
        elif reference_style == "citation":
            return f"(see {doc_name})"
        
        else:  # informal
            return f"per {doc_name}"
    
    def plan_cross_document_operation(
        self, 
        operation_type: ReferenceType,
        source_doc_path: Path,
        target_element: str,
        integration_context: Optional[str] = None
    ) -> CrossDocumentOperation:
        """
        Plan a cross-document operation.
        
        Args:
            operation_type: Type of operation to perform
            source_doc_path: Path to source document
            target_element: Description of element to find/copy
            integration_context: Context about where to integrate
            
        Returns:
            Planned operation
        """
        import uuid
        
        operation = CrossDocumentOperation(
            operation_id=f"xdoc_{uuid.uuid4().hex[:8]}",
            operation_type=operation_type,
            source_doc=source_doc_path,
            target_element=target_element
        )
        
        # Create integration plan
        if operation_type == ReferenceType.COPY:
            operation.integration_plan = [
                "Open source document",
                f"Find '{target_element}' in source",
                "Extract content with appropriate context",
                "Format for integration",
                "Insert into target document"
            ]
        
        elif operation_type == ReferenceType.CITATION:
            operation.integration_plan = [
                "Open source document",
                f"Locate '{target_element}' in source",
                "Create formal reference text",
                "Insert reference in target document"
            ]
        
        return operation
    
    def execute_copy_operation(
        self, 
        source_doc_path: Path,
        target_element: str,
        target_document: DocumentModel,
        insert_position: Optional[Position] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Execute a copy operation from one document to another.
        
        Args:
            source_doc_path: Source document path
            target_element: Element to copy
            target_document: Target document
            insert_position: Where to insert (None for end)
            
        Returns:
            Tuple of (success, message, copied_content)
        """
        # Open source document
        source_doc = self.open_reference_document(source_doc_path)
        if not source_doc:
            return False, f"Could not open source document: {source_doc_path}", None
        
        # Find element in source
        references = self.find_element_in_document(target_element, source_doc)
        if not references:
            return False, f"Could not find '{target_element}' in {source_doc_path.name}", None
        
        # Use the best reference
        best_ref = references[0]
        content = self.extract_content_for_reference(best_ref)
        
        if not content:
            return False, "No content found to copy", None
        
        # The actual insertion would be handled by the calling code
        # This method returns the content to be inserted
        
        success_msg = f"Found content to copy from {source_doc_path.name}"
        return True, success_msg, content
    
    def create_reference_operation(
        self,
        source_doc_path: Path,
        reference_element: str,
        reference_style: str = "formal"
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Create a reference to content in another document.
        
        Args:
            source_doc_path: Document to reference
            reference_element: Element to reference
            reference_style: Style of reference
            
        Returns:
            Tuple of (success, message, reference_text)
        """
        # Open source document
        source_doc = self.open_reference_document(source_doc_path)
        if not source_doc:
            return False, f"Could not open reference document: {source_doc_path}", None
        
        # Find element
        references = self.find_element_in_document(reference_element, source_doc)
        if not references:
            return False, f"Could not find '{reference_element}' in {source_doc_path.name}", None
        
        # Create reference text
        best_ref = references[0]
        ref_text = self.create_cross_reference_text(best_ref, reference_style)
        
        success_msg = f"Created reference to {source_doc_path.name}"
        return True, success_msg, ref_text
    
    def _classify_element_type(self, content: str, query: str) -> str:
        """Classify the type of element based on content and query."""
        content_lower = content.lower()
        query_lower = query.lower()
        
        # Check for specific patterns
        for element_type, patterns in self.reference_patterns.items():
            for pattern in patterns:
                import re
                if re.search(pattern, content_lower) or re.search(pattern, query_lower):
                    return element_type
        
        # Default classification based on content characteristics
        if len(content) < 100:
            return "clause"
        elif any(word in content_lower for word in ['section', 'chapter', 'part']):
            return "section"
        else:
            return "paragraph"
    
    def _deduplicate_references(self, references: List[DocumentReference]) -> List[DocumentReference]:
        """Remove duplicate references based on content similarity."""
        if not references:
            return references
        
        unique_refs = []
        seen_content = set()
        
        for ref in references:
            if ref.element_text:
                # Create a simplified version for comparison
                simplified = ' '.join(ref.element_text.lower().split()[:10])  # First 10 words
                
                if simplified not in seen_content:
                    unique_refs.append(ref)
                    seen_content.add(simplified)
        
        return unique_refs
    
    def validate_cross_references(
        self, 
        document: DocumentModel
    ) -> List[Dict[str, Any]]:
        """
        Validate existing cross-references in a document.
        
        Args:
            document: Document to validate
            
        Returns:
            List of validation issues found
        """
        issues = []
        handler = ASTHandler(document.pandoc_ast)
        
        # Look for potential cross-references
        reference_patterns = [
            r'see\s+([^\.]+\.docx)',
            r'as\s+specified\s+in\s+([^\.]+\.docx)',
            r'per\s+([^\.]+\.docx)'
        ]
        
        for i, block in enumerate(document.pandoc_ast.blocks):
            text = handler._extract_text_from_block(block)
            
            for pattern in reference_patterns:
                import re
                matches = re.finditer(pattern, text, re.IGNORECASE)
                
                for match in matches:
                    referenced_doc = match.group(1)
                    doc_path = Path(referenced_doc)
                    
                    if not doc_path.is_absolute():
                        # Try relative to current document
                        if document.source_path:
                            doc_path = document.source_path.parent / doc_path
                    
                    if not doc_path.exists():
                        issues.append({
                            'type': 'broken_reference',
                            'location': f"paragraph {i + 1}",
                            'message': f"Referenced document not found: {referenced_doc}",
                            'suggested_fix': f"Verify path to {referenced_doc}"
                        })
        
        return issues
    
    def get_document_summary(self, doc_path: Path) -> Optional[Dict[str, Any]]:
        """
        Get a summary of a document for reference purposes.
        
        Args:
            doc_path: Path to document
            
        Returns:
            Document summary or None if not accessible
        """
        document = self.open_reference_document(doc_path)
        if not document:
            return None
        
        stats = document.get_stats()
        handler = ASTHandler(document.pandoc_ast)
        
        # Get headings structure
        headings = handler.find_headings()
        heading_structure = []
        
        for pos, heading in headings[:10]:  # First 10 headings
            level = heading.get('c', [None])[0]
            text = handler._extract_text_from_block(heading)
            heading_structure.append({
                'level': level,
                'text': text,
                'paragraph': pos.block_index + 1
            })
        
        return {
            'path': str(doc_path),
            'name': doc_path.name,
            'stats': stats,
            'headings': heading_structure,
            'accessible': True
        }