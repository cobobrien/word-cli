"""
Diff engine for calculating and visualizing document differences.

Provides detailed comparison between document versions with support for
content, structure, and metadata changes.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union
from enum import Enum

from ..core.document_model import DocumentModel, PandocAST
from ..core.ast_handler import ASTHandler, Position, Range


class DiffType(Enum):
    """Types of differences between documents."""
    INSERT = "insert"
    DELETE = "delete"
    MODIFY = "modify"
    MOVE = "move"
    STYLE_CHANGE = "style_change"
    METADATA_CHANGE = "metadata_change"


@dataclass
class DiffHunk:
    """Represents a single difference between documents."""
    
    diff_type: DiffType
    location: Position
    old_content: Optional[Any] = None
    new_content: Optional[Any] = None
    old_range: Optional[Range] = None
    new_range: Optional[Range] = None
    confidence: float = 1.0  # Confidence in the diff (0-1)
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "diff_type": self.diff_type.value,
            "location": str(self.location),
            "old_content": self.old_content,
            "new_content": self.new_content,
            "old_range": str(self.old_range) if self.old_range else None,
            "new_range": str(self.new_range) if self.new_range else None,
            "confidence": self.confidence,
            "description": self.description,
        }


@dataclass
class DocumentDiff:
    """Represents the complete diff between two documents."""
    
    source_version: str
    target_version: str
    timestamp: str
    hunks: List[DiffHunk] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)
    
    def __post_init__(self):
        """Calculate summary statistics."""
        self.summary = {
            "total_changes": len(self.hunks),
            "insertions": len([h for h in self.hunks if h.diff_type == DiffType.INSERT]),
            "deletions": len([h for h in self.hunks if h.diff_type == DiffType.DELETE]),
            "modifications": len([h for h in self.hunks if h.diff_type == DiffType.MODIFY]),
            "moves": len([h for h in self.hunks if h.diff_type == DiffType.MOVE]),
            "style_changes": len([h for h in self.hunks if h.diff_type == DiffType.STYLE_CHANGE]),
            "metadata_changes": len([h for h in self.hunks if h.diff_type == DiffType.METADATA_CHANGE]),
        }
    
    def get_hunks_by_type(self, diff_type: DiffType) -> List[DiffHunk]:
        """Get all hunks of a specific type."""
        return [h for h in self.hunks if h.diff_type == diff_type]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source_version": self.source_version,
            "target_version": self.target_version,
            "timestamp": self.timestamp,
            "hunks": [h.to_dict() for h in self.hunks],
            "summary": self.summary,
        }


class DiffEngine:
    """
    Engine for calculating detailed diffs between document versions.
    
    Provides multiple diff algorithms optimized for different types of changes.
    """
    
    def __init__(self):
        self.similarity_threshold = 0.7  # Threshold for considering content similar
    
    def diff_documents(
        self, 
        doc1: DocumentModel, 
        doc2: DocumentModel,
        version1_id: str = "v1",
        version2_id: str = "v2"
    ) -> DocumentDiff:
        """
        Calculate comprehensive diff between two documents.
        
        Args:
            doc1: First document (source)
            doc2: Second document (target)
            version1_id: ID of first version
            version2_id: ID of second version
            
        Returns:
            DocumentDiff containing all changes
        """
        from datetime import datetime
        
        diff = DocumentDiff(
            source_version=version1_id,
            target_version=version2_id,
            timestamp=datetime.now().isoformat(),
        )
        
        # Calculate content diffs
        content_hunks = self._diff_content(doc1, doc2)
        diff.hunks.extend(content_hunks)
        
        # Calculate metadata diffs
        metadata_hunks = self._diff_metadata(doc1, doc2)
        diff.hunks.extend(metadata_hunks)
        
        # Calculate style diffs
        style_hunks = self._diff_styles(doc1, doc2)
        diff.hunks.extend(style_hunks)
        
        # Update summary
        diff.__post_init__()
        
        return diff
    
    def _diff_content(self, doc1: DocumentModel, doc2: DocumentModel) -> List[DiffHunk]:
        """Calculate content differences between documents."""
        hunks = []
        
        handler1 = ASTHandler(doc1.pandoc_ast)
        handler2 = ASTHandler(doc2.pandoc_ast)
        
        # Get text content for each block
        blocks1 = [(i, handler1._extract_text_from_block(block)) 
                   for i, block in enumerate(doc1.pandoc_ast.blocks)]
        blocks2 = [(i, handler2._extract_text_from_block(block)) 
                   for i, block in enumerate(doc2.pandoc_ast.blocks)]
        
        # Use sequence matching to find changes
        texts1 = [text for _, text in blocks1]
        texts2 = [text for _, text in blocks2]
        
        matcher = difflib.SequenceMatcher(None, texts1, texts2)
        
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                continue
            elif tag == 'delete':
                # Content was deleted
                for i in range(i1, i2):
                    if i < len(blocks1):
                        hunks.append(DiffHunk(
                            diff_type=DiffType.DELETE,
                            location=Position(block_index=i),
                            old_content=blocks1[i][1],
                            description=f"Deleted paragraph {i + 1}: '{blocks1[i][1][:50]}...'"
                        ))
            elif tag == 'insert':
                # Content was inserted
                for j in range(j1, j2):
                    if j < len(blocks2):
                        hunks.append(DiffHunk(
                            diff_type=DiffType.INSERT,
                            location=Position(block_index=j),
                            new_content=blocks2[j][1],
                            description=f"Inserted paragraph {j + 1}: '{blocks2[j][1][:50]}...'"
                        ))
            elif tag == 'replace':
                # Content was modified
                for i, j in zip(range(i1, i2), range(j1, j2)):
                    old_text = blocks1[i][1] if i < len(blocks1) else ""
                    new_text = blocks2[j][1] if j < len(blocks2) else ""
                    
                    # Check if this is a modification or a move
                    similarity = self._calculate_similarity(old_text, new_text)
                    
                    if similarity > self.similarity_threshold:
                        # Similar content - likely a modification
                        hunks.append(DiffHunk(
                            diff_type=DiffType.MODIFY,
                            location=Position(block_index=j),
                            old_content=old_text,
                            new_content=new_text,
                            confidence=similarity,
                            description=f"Modified paragraph {j + 1}"
                        ))
                    else:
                        # Different content - deletion + insertion
                        if i < len(blocks1):
                            hunks.append(DiffHunk(
                                diff_type=DiffType.DELETE,
                                location=Position(block_index=i),
                                old_content=old_text,
                                description=f"Deleted paragraph {i + 1}"
                            ))
                        if j < len(blocks2):
                            hunks.append(DiffHunk(
                                diff_type=DiffType.INSERT,
                                location=Position(block_index=j),
                                new_content=new_text,
                                description=f"Inserted paragraph {j + 1}"
                            ))
        
        return hunks
    
    def _diff_metadata(self, doc1: DocumentModel, doc2: DocumentModel) -> List[DiffHunk]:
        """Calculate metadata differences."""
        hunks = []
        
        meta1 = doc1.word_metadata
        meta2 = doc2.word_metadata
        
        # Compare basic properties
        properties = ['title', 'author', 'subject', 'comments']
        for prop in properties:
            val1 = getattr(meta1, prop)
            val2 = getattr(meta2, prop)
            
            if val1 != val2:
                hunks.append(DiffHunk(
                    diff_type=DiffType.METADATA_CHANGE,
                    location=Position(block_index=-1),  # Metadata doesn't have a block position
                    old_content=val1,
                    new_content=val2,
                    description=f"Changed {prop} from '{val1}' to '{val2}'"
                ))
        
        # Compare keywords
        if set(meta1.keywords) != set(meta2.keywords):
            hunks.append(DiffHunk(
                diff_type=DiffType.METADATA_CHANGE,
                location=Position(block_index=-1),
                old_content=meta1.keywords,
                new_content=meta2.keywords,
                description="Changed document keywords"
            ))
        
        # Compare page settings
        if meta1.page_margins != meta2.page_margins:
            hunks.append(DiffHunk(
                diff_type=DiffType.METADATA_CHANGE,
                location=Position(block_index=-1),
                old_content=meta1.page_margins,
                new_content=meta2.page_margins,
                description="Changed page margins"
            ))
        
        if meta1.page_size != meta2.page_size:
            hunks.append(DiffHunk(
                diff_type=DiffType.METADATA_CHANGE,
                location=Position(block_index=-1),
                old_content=meta1.page_size,
                new_content=meta2.page_size,
                description="Changed page size"
            ))
        
        return hunks
    
    def _diff_styles(self, doc1: DocumentModel, doc2: DocumentModel) -> List[DiffHunk]:
        """Calculate style differences."""
        hunks = []
        
        styles1 = doc1.word_metadata.styles
        styles2 = doc2.word_metadata.styles
        
        # Find added styles
        for style_name in styles2:
            if style_name not in styles1:
                hunks.append(DiffHunk(
                    diff_type=DiffType.INSERT,
                    location=Position(block_index=-1),
                    new_content=styles2[style_name],
                    description=f"Added style '{style_name}'"
                ))
        
        # Find removed styles
        for style_name in styles1:
            if style_name not in styles2:
                hunks.append(DiffHunk(
                    diff_type=DiffType.DELETE,
                    location=Position(block_index=-1),
                    old_content=styles1[style_name],
                    description=f"Removed style '{style_name}'"
                ))
        
        # Find modified styles
        for style_name in styles1:
            if style_name in styles2 and styles1[style_name] != styles2[style_name]:
                hunks.append(DiffHunk(
                    diff_type=DiffType.STYLE_CHANGE,
                    location=Position(block_index=-1),
                    old_content=styles1[style_name],
                    new_content=styles2[style_name],
                    description=f"Modified style '{style_name}'"
                ))
        
        return hunks
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two text strings."""
        if not text1 and not text2:
            return 1.0
        if not text1 or not text2:
            return 0.0
        
        # Use difflib's ratio for similarity
        return difflib.SequenceMatcher(None, text1, text2).ratio()
    
    def generate_text_diff(
        self, 
        doc1: DocumentModel, 
        doc2: DocumentModel,
        context_lines: int = 3
    ) -> str:
        """
        Generate a unified text diff similar to git diff.
        
        Args:
            doc1: First document
            doc2: Second document
            context_lines: Number of context lines to show
            
        Returns:
            Unified diff as string
        """
        text1 = doc1.get_text_content().splitlines(keepends=True)
        text2 = doc2.get_text_content().splitlines(keepends=True)
        
        diff_lines = list(difflib.unified_diff(
            text1, 
            text2,
            fromfile='document_v1.txt',
            tofile='document_v2.txt',
            n=context_lines
        ))
        
        return ''.join(diff_lines)
    
    def generate_html_diff(
        self, 
        doc1: DocumentModel, 
        doc2: DocumentModel
    ) -> str:
        """
        Generate an HTML diff visualization.
        
        Args:
            doc1: First document
            doc2: Second document
            
        Returns:
            HTML string with diff visualization
        """
        text1 = doc1.get_text_content().splitlines()
        text2 = doc2.get_text_content().splitlines()
        
        differ = difflib.HtmlDiff()
        return differ.make_file(
            text1,
            text2,
            fromdesc='Version 1',
            todesc='Version 2',
            context=True,
            numlines=3
        )
    
    def get_word_level_diff(
        self, 
        text1: str, 
        text2: str
    ) -> List[Tuple[str, str]]:
        """
        Get word-level differences between two text strings.
        
        Args:
            text1: First text
            text2: Second text
            
        Returns:
            List of (operation, word) tuples where operation is 'equal', 'delete', or 'insert'
        """
        words1 = text1.split()
        words2 = text2.split()
        
        matcher = difflib.SequenceMatcher(None, words1, words2)
        
        diff_words = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                for word in words1[i1:i2]:
                    diff_words.append(('equal', word))
            elif tag == 'delete':
                for word in words1[i1:i2]:
                    diff_words.append(('delete', word))
            elif tag == 'insert':
                for word in words2[j1:j2]:
                    diff_words.append(('insert', word))
            elif tag == 'replace':
                for word in words1[i1:i2]:
                    diff_words.append(('delete', word))
                for word in words2[j1:j2]:
                    diff_words.append(('insert', word))
        
        return diff_words
    
    def summarize_changes(self, diff: DocumentDiff) -> Dict[str, Any]:
        """
        Generate a human-readable summary of changes.
        
        Args:
            diff: DocumentDiff to summarize
            
        Returns:
            Dictionary with change summary
        """
        summary = {
            "overview": f"Found {diff.summary['total_changes']} changes between versions",
            "content_changes": [],
            "metadata_changes": [],
            "style_changes": [],
        }
        
        # Summarize content changes
        if diff.summary['insertions']:
            summary["content_changes"].append(f"Added {diff.summary['insertions']} new sections")
        if diff.summary['deletions']:
            summary["content_changes"].append(f"Removed {diff.summary['deletions']} sections")
        if diff.summary['modifications']:
            summary["content_changes"].append(f"Modified {diff.summary['modifications']} sections")
        
        # Summarize metadata changes
        metadata_hunks = diff.get_hunks_by_type(DiffType.METADATA_CHANGE)
        for hunk in metadata_hunks:
            summary["metadata_changes"].append(hunk.description)
        
        # Summarize style changes
        style_hunks = diff.get_hunks_by_type(DiffType.STYLE_CHANGE)
        for hunk in style_hunks:
            summary["style_changes"].append(hunk.description)
        
        return summary
    
    def apply_diff(
        self, 
        document: DocumentModel, 
        diff: DocumentDiff,
        reverse: bool = False
    ) -> DocumentModel:
        """
        Apply a diff to a document to get the target state.
        
        Args:
            document: Source document
            diff: Diff to apply
            reverse: If True, apply diff in reverse (undo)
            
        Returns:
            New DocumentModel with diff applied
        """
        # Create a copy of the document
        result_doc = document.clone()
        
        # Sort hunks by position (reverse order for reverse application)
        hunks = sorted(diff.hunks, key=lambda h: h.location.block_index, reverse=True)
        
        if reverse:
            # For reverse application, swap old and new content
            hunks = [DiffHunk(
                diff_type=hunk.diff_type,
                location=hunk.location,
                old_content=hunk.new_content,
                new_content=hunk.old_content,
                description=f"Undo: {hunk.description}"
            ) for hunk in hunks]
        
        handler = ASTHandler(result_doc.pandoc_ast)
        
        # Apply each hunk
        for hunk in hunks:
            if hunk.diff_type == DiffType.INSERT and hunk.new_content:
                # Insert new content
                new_para = handler.create_paragraph(hunk.new_content)
                handler.insert_block(hunk.location.block_index, new_para)
                
            elif hunk.diff_type == DiffType.DELETE:
                # Delete content
                if 0 <= hunk.location.block_index < len(result_doc.pandoc_ast.blocks):
                    handler.delete_block(hunk.location.block_index)
                    
            elif hunk.diff_type == DiffType.MODIFY and hunk.new_content:
                # Modify content
                new_para = handler.create_paragraph(hunk.new_content)
                handler.replace_block(hunk.location.block_index, new_para)
                
            elif hunk.diff_type == DiffType.METADATA_CHANGE:
                # Apply metadata changes (simplified)
                pass  # Would need to implement specific metadata application
        
        # Mark as modified
        result_doc.mark_modified()
        
        return result_doc