"""
Core document model implementing the hybrid AST + metadata approach.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field
from uuid import uuid4

from pydantic import BaseModel


class PandocAST(BaseModel):
    """Wrapper for Pandoc AST representation of document content."""
    
    version: str = "1.23"
    blocks: List[Dict[str, Any]] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_pandoc_json(cls, pandoc_json: Dict[str, Any]) -> PandocAST:
        """Create PandocAST from Pandoc JSON output."""
        return cls(
            version=pandoc_json.get("pandoc-api-version", "1.23"),
            blocks=pandoc_json.get("blocks", []),
            meta=pandoc_json.get("meta", {})
        )
    
    def to_pandoc_json(self) -> Dict[str, Any]:
        """Convert to Pandoc JSON format."""
        return {
            "pandoc-api-version": self.version,
            "meta": self.meta,
            "blocks": self.blocks
        }
    
    def find_block_by_id(self, block_id: str) -> Optional[Dict[str, Any]]:
        """Find a block by its ID."""
        for block in self.blocks:
            if block.get("c", [{}])[0].get("identifier") == block_id:
                return block
        return None
    
    def get_text_content(self) -> str:
        """Extract plain text content from AST."""
        # This is a simplified implementation
        # In practice, would need recursive text extraction
        text_parts = []
        for block in self.blocks:
            if block.get("t") == "Para":
                # Extract text from paragraph
                content = block.get("c", [])
                text_parts.append(self._extract_text_from_inlines(content))
        return "\n\n".join(text_parts)
    
    def _extract_text_from_inlines(self, inlines: List[Dict[str, Any]]) -> str:
        """Extract text from inline elements."""
        text_parts = []
        for inline in inlines:
            if inline.get("t") == "Str":
                text_parts.append(inline.get("c", ""))
            elif inline.get("t") == "Space":
                text_parts.append(" ")
        return "".join(text_parts)


@dataclass
class WordMetadata:
    """Preserves Word-specific metadata and formatting."""
    
    # Document properties
    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    comments: Optional[str] = None
    
    # Styles
    styles: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    default_style: Optional[str] = None
    
    # Document settings
    page_margins: Dict[str, float] = field(default_factory=dict)
    page_size: Dict[str, float] = field(default_factory=dict)
    
    # Track changes and comments
    track_changes_enabled: bool = False
    document_comments: List[Dict[str, Any]] = field(default_factory=list)
    
    # Custom XML parts (for advanced features)
    custom_xml_parts: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "title": self.title,
            "author": self.author,
            "subject": self.subject,
            "keywords": self.keywords,
            "comments": self.comments,
            "styles": self.styles,
            "default_style": self.default_style,
            "page_margins": self.page_margins,
            "page_size": self.page_size,
            "track_changes_enabled": self.track_changes_enabled,
            "document_comments": self.document_comments,
            "custom_xml_parts": self.custom_xml_parts,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WordMetadata:
        """Create from dictionary."""
        return cls(**data)


@dataclass
class XMLFragments:
    """Stores complex OOXML fragments that can't be represented in Pandoc AST."""
    
    # Complex elements that we preserve as raw XML
    headers_footers: Dict[str, str] = field(default_factory=dict)  # section -> xml
    footnotes: Dict[str, str] = field(default_factory=dict)        # id -> xml  
    endnotes: Dict[str, str] = field(default_factory=dict)         # id -> xml
    embedded_objects: Dict[str, bytes] = field(default_factory=dict)  # id -> binary
    
    # Charts, diagrams, equations
    complex_elements: Dict[str, str] = field(default_factory=dict)  # id -> xml
    
    def add_fragment(self, fragment_id: str, xml_content: str, fragment_type: str = "complex") -> None:
        """Add an XML fragment."""
        if fragment_type == "header_footer":
            self.headers_footers[fragment_id] = xml_content
        elif fragment_type == "footnote":
            self.footnotes[fragment_id] = xml_content
        elif fragment_type == "endnote":
            self.endnotes[fragment_id] = xml_content
        else:
            self.complex_elements[fragment_id] = xml_content
    
    def get_fragment(self, fragment_id: str) -> Optional[str]:
        """Retrieve an XML fragment by ID."""
        # Search across all fragment types
        for fragments in [self.headers_footers, self.footnotes, self.endnotes, self.complex_elements]:
            if fragment_id in fragments:
                return fragments[fragment_id]
        return None


@dataclass  
class ASTToXMLMapping:
    """Tracks the relationship between AST elements and XML positions."""
    
    # Maps AST element IDs to XML locations
    ast_to_xml: Dict[str, str] = field(default_factory=dict)  # ast_element_id -> xml_path
    xml_to_ast: Dict[str, str] = field(default_factory=dict)  # xml_path -> ast_element_id
    
    # Preserved element positions for round-trip fidelity
    element_positions: Dict[str, int] = field(default_factory=dict)  # element_id -> position
    
    def add_mapping(self, ast_element_id: str, xml_path: str, position: int = 0) -> None:
        """Add a bidirectional mapping."""
        self.ast_to_xml[ast_element_id] = xml_path
        self.xml_to_ast[xml_path] = ast_element_id
        self.element_positions[ast_element_id] = position
    
    def get_xml_path(self, ast_element_id: str) -> Optional[str]:
        """Get XML path for an AST element."""
        return self.ast_to_xml.get(ast_element_id)
    
    def get_ast_element(self, xml_path: str) -> Optional[str]:
        """Get AST element ID for an XML path."""
        return self.xml_to_ast.get(xml_path)


class DocumentModel:
    """
    Main document model implementing the hybrid AST + metadata approach.
    
    This is the core class that combines Pandoc AST for content manipulation
    with metadata preservation for Word-specific features.
    """
    
    def __init__(
        self,
        pandoc_ast: Optional[PandocAST] = None,
        word_metadata: Optional[WordMetadata] = None,
        xml_fragments: Optional[XMLFragments] = None,
        mapping: Optional[ASTToXMLMapping] = None,
        source_path: Optional[Path] = None,
    ):
        self.document_id = str(uuid4())
        self.pandoc_ast = pandoc_ast or PandocAST()
        self.word_metadata = word_metadata or WordMetadata()
        self.xml_fragments = xml_fragments or XMLFragments()
        self.mapping = mapping or ASTToXMLMapping()
        self.source_path = source_path
        
        # Track modification state
        self.is_modified = False
        self.last_modified = datetime.now()
        
        # Version tracking
        self.current_version: Optional[str] = None
        self.base_version: Optional[str] = None
    
    @classmethod
    def from_docx(cls, docx_path: Path) -> DocumentModel:
        """Create DocumentModel from a DOCX file."""
        # This will be implemented in the converters module
        from ..converters.docx_to_ast import DocxToASTConverter
        
        converter = DocxToASTConverter()
        return converter.convert(docx_path)
    
    def to_docx(self, output_path: Path) -> None:
        """Save DocumentModel to a DOCX file."""
        # This will be implemented in the converters module
        from ..converters.ast_to_docx import ASTToDocxConverter
        
        converter = ASTToDocxConverter()
        converter.convert(self, output_path)
    
    def get_text_content(self) -> str:
        """Get the plain text content of the document."""
        return self.pandoc_ast.get_text_content()
    
    def mark_modified(self) -> None:
        """Mark the document as modified."""
        self.is_modified = True
        self.last_modified = datetime.now()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get document statistics."""
        text_content = self.get_text_content()
        return {
            "document_id": self.document_id,
            "word_count": len(text_content.split()),
            "character_count": len(text_content),
            "paragraph_count": len([b for b in self.pandoc_ast.blocks if b.get("t") == "Para"]),
            "heading_count": len([b for b in self.pandoc_ast.blocks if b.get("t") == "Header"]),
            "is_modified": self.is_modified,
            "last_modified": self.last_modified.isoformat(),
        }
    
    def validate_integrity(self) -> List[str]:
        """Validate document integrity and return any issues."""
        issues = []
        
        # Check AST structure
        if not self.pandoc_ast.blocks:
            issues.append("Document has no content blocks")
        
        # Check for broken mappings
        for ast_id, xml_path in self.mapping.ast_to_xml.items():
            if xml_path not in self.mapping.xml_to_ast:
                issues.append(f"Broken mapping for AST element {ast_id}")
        
        # Check for missing required metadata
        if not self.word_metadata.default_style:
            issues.append("No default style defined")
        
        return issues
    
    def clone(self) -> DocumentModel:
        """Create a deep copy of the document model."""
        return DocumentModel(
            pandoc_ast=PandocAST.model_validate(self.pandoc_ast.model_dump()),
            word_metadata=WordMetadata.from_dict(self.word_metadata.to_dict()),
            xml_fragments=XMLFragments(**{
                k: v.copy() if isinstance(v, dict) else v 
                for k, v in self.xml_fragments.__dict__.items()
            }),
            mapping=ASTToXMLMapping(**{
                k: v.copy() if isinstance(v, dict) else v 
                for k, v in self.mapping.__dict__.items()
            }),
            source_path=self.source_path,
        )