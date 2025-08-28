"""
AST handler for navigation and manipulation of Pandoc AST structures.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union, Iterator
from enum import Enum
import re

from .document_model import PandocAST


class ElementType(Enum):
    """Pandoc element types for navigation."""
    PARA = "Para"
    HEADER = "Header"
    PLAIN = "Plain"
    CODE_BLOCK = "CodeBlock"
    RAW_BLOCK = "RawBlock"
    BLOCK_QUOTE = "BlockQuote"
    ORDERED_LIST = "OrderedList"
    BULLET_LIST = "BulletList"
    DEF_LIST = "DefinitionList"
    TABLE = "Table"
    DIV = "Div"
    NULL = "Null"
    
    # Inline elements
    STR = "Str"
    EMPH = "Emph"
    UNDERLINE = "Underline"
    STRONG = "Strong"
    STRIKEOUT = "Strikeout"
    SUPERSCRIPT = "Superscript"
    SUBSCRIPT = "Subscript"
    SMALL_CAPS = "SmallCaps"
    QUOTED = "Quoted"
    CITE = "Cite"
    CODE = "Code"
    SPACE = "Space"
    SOFT_BREAK = "SoftBreak"
    LINE_BREAK = "LineBreak"
    RAW_INLINE = "RawInline"
    LINK = "Link"
    IMAGE = "Image"
    NOTE = "Note"
    SPAN = "Span"


@dataclass
class Position:
    """Represents a position in the document."""
    
    block_index: int
    inline_index: Optional[int] = None
    char_offset: Optional[int] = None
    
    def __str__(self) -> str:
        if self.inline_index is not None:
            if self.char_offset is not None:
                return f"block:{self.block_index},inline:{self.inline_index},char:{self.char_offset}"
            return f"block:{self.block_index},inline:{self.inline_index}"
        return f"block:{self.block_index}"
    
    def __lt__(self, other: Position) -> bool:
        if self.block_index != other.block_index:
            return self.block_index < other.block_index
        if self.inline_index is None or other.inline_index is None:
            return False
        if self.inline_index != other.inline_index:
            return self.inline_index < other.inline_index
        if self.char_offset is None or other.char_offset is None:
            return False
        return self.char_offset < other.char_offset


@dataclass
class Range:
    """Represents a range in the document."""
    
    start: Position
    end: Position
    
    def __str__(self) -> str:
        return f"{self.start} -> {self.end}"
    
    def contains(self, pos: Position) -> bool:
        """Check if position is within this range."""
        return self.start <= pos <= self.end
    
    def overlaps(self, other: Range) -> bool:
        """Check if this range overlaps with another."""
        return self.start <= other.end and other.start <= self.end


class ASTHandler:
    """
    Handles navigation and manipulation of Pandoc AST structures.
    
    Provides methods for finding, extracting, and modifying elements
    in the document AST with precise position tracking.
    """
    
    def __init__(self, ast: PandocAST):
        self.ast = ast
        self._element_cache: Dict[str, Any] = {}
        self._position_cache: Dict[str, Position] = {}
    
    def find_by_type(self, element_type: ElementType) -> List[Tuple[Position, Dict[str, Any]]]:
        """Find all elements of a specific type."""
        results = []
        
        for block_idx, block in enumerate(self.ast.blocks):
            if block.get("t") == element_type.value:
                pos = Position(block_index=block_idx)
                results.append((pos, block))
            
            # Search inline elements within blocks
            if element_type.value in ["Str", "Emph", "Strong", "Link", "Image"]:
                inline_results = self._find_inlines_by_type(block_idx, block, element_type)
                results.extend(inline_results)
        
        return results
    
    def _find_inlines_by_type(
        self, 
        block_idx: int, 
        block: Dict[str, Any], 
        element_type: ElementType
    ) -> List[Tuple[Position, Dict[str, Any]]]:
        """Find inline elements of specific type within a block."""
        results = []
        
        def search_inlines(inlines: List[Dict[str, Any]], parent_idx: int = 0) -> None:
            for inline_idx, inline in enumerate(inlines):
                if inline.get("t") == element_type.value:
                    pos = Position(
                        block_index=block_idx,
                        inline_index=parent_idx + inline_idx
                    )
                    results.append((pos, inline))
                
                # Recursively search nested inlines
                content = inline.get("c", [])
                if isinstance(content, list) and len(content) > 0:
                    if isinstance(content[-1], list):  # Last element is inline list
                        search_inlines(content[-1], parent_idx + inline_idx + 1)
        
        # Get inline content from block
        block_content = block.get("c", [])
        if isinstance(block_content, list):
            search_inlines(block_content)
        
        return results
    
    def find_by_text(self, text: str, case_sensitive: bool = True) -> List[Tuple[Position, Dict[str, Any]]]:
        """Find elements containing specific text."""
        if not case_sensitive:
            text = text.lower()
        
        results = []
        
        for block_idx, block in enumerate(self.ast.blocks):
            block_text = self._extract_text_from_block(block)
            if not case_sensitive:
                block_text = block_text.lower()
            
            if text in block_text:
                pos = Position(block_index=block_idx)
                results.append((pos, block))
        
        return results
    
    def find_by_regex(self, pattern: str, flags: int = 0) -> List[Tuple[Position, Dict[str, Any], re.Match]]:
        """Find elements matching a regex pattern."""
        regex = re.compile(pattern, flags)
        results = []
        
        for block_idx, block in enumerate(self.ast.blocks):
            block_text = self._extract_text_from_block(block)
            
            for match in regex.finditer(block_text):
                pos = Position(
                    block_index=block_idx,
                    char_offset=match.start()
                )
                results.append((pos, block, match))
        
        return results
    
    def find_headings(self, level: Optional[int] = None) -> List[Tuple[Position, Dict[str, Any]]]:
        """Find heading elements, optionally filtered by level."""
        results = []
        
        for block_idx, block in enumerate(self.ast.blocks):
            if block.get("t") == "Header":
                header_level = block.get("c", [None])[0]
                
                if level is None or header_level == level:
                    pos = Position(block_index=block_idx)
                    results.append((pos, block))
        
        return results
    
    def find_by_id(self, element_id: str) -> Optional[Tuple[Position, Dict[str, Any]]]:
        """Find an element by its ID."""
        for block_idx, block in enumerate(self.ast.blocks):
            # Check block attributes for ID
            if self._has_id(block, element_id):
                pos = Position(block_index=block_idx)
                return (pos, block)
            
            # Check inline elements
            inline_result = self._find_inline_by_id(block_idx, block, element_id)
            if inline_result:
                return inline_result
        
        return None
    
    def _has_id(self, element: Dict[str, Any], element_id: str) -> bool:
        """Check if element has the specified ID."""
        content = element.get("c", [])
        
        # For blocks with attributes (Header, Div, etc.)
        if isinstance(content, list) and len(content) > 0:
            first_item = content[0]
            if isinstance(first_item, list) and len(first_item) >= 3:
                # [id, classes, attributes]
                return first_item[0] == element_id
        
        return False
    
    def _find_inline_by_id(
        self, 
        block_idx: int, 
        block: Dict[str, Any], 
        element_id: str
    ) -> Optional[Tuple[Position, Dict[str, Any]]]:
        """Find inline element by ID within a block."""
        def search_inlines(inlines: List[Dict[str, Any]], parent_idx: int = 0) -> Optional[Tuple[Position, Dict[str, Any]]]:
            for inline_idx, inline in enumerate(inlines):
                if self._has_id(inline, element_id):
                    pos = Position(
                        block_index=block_idx,
                        inline_index=parent_idx + inline_idx
                    )
                    return (pos, inline)
                
                # Search nested inlines
                content = inline.get("c", [])
                if isinstance(content, list) and len(content) > 0:
                    if isinstance(content[-1], list):
                        result = search_inlines(content[-1], parent_idx + inline_idx + 1)
                        if result:
                            return result
            
            return None
        
        block_content = block.get("c", [])
        if isinstance(block_content, list):
            return search_inlines(block_content)
        
        return None
    
    def get_element_at(self, position: Position) -> Optional[Dict[str, Any]]:
        """Get element at specific position."""
        if position.block_index >= len(self.ast.blocks):
            return None
        
        block = self.ast.blocks[position.block_index]
        
        if position.inline_index is None:
            return block
        
        # Navigate to inline element
        return self._get_inline_at(block, position.inline_index)
    
    def _get_inline_at(self, block: Dict[str, Any], inline_index: int) -> Optional[Dict[str, Any]]:
        """Get inline element at specific index."""
        def get_inlines(element: Dict[str, Any]) -> List[Dict[str, Any]]:
            content = element.get("c", [])
            if isinstance(content, list) and content:
                if isinstance(content[-1], list):
                    return content[-1]
            return []
        
        inlines = get_inlines(block)
        if inline_index < len(inlines):
            return inlines[inline_index]
        
        return None
    
    def _extract_text_from_block(self, block: Dict[str, Any]) -> str:
        """Extract plain text content from a block."""
        def extract_from_inlines(inlines: List[Dict[str, Any]]) -> str:
            text_parts = []
            for inline in inlines:
                if inline.get("t") == "Str":
                    text_parts.append(inline.get("c", ""))
                elif inline.get("t") == "Space":
                    text_parts.append(" ")
                elif inline.get("t") == "SoftBreak":
                    text_parts.append(" ")
                elif inline.get("t") == "LineBreak":
                    text_parts.append("\n")
                else:
                    # For complex inlines, recursively extract text
                    content = inline.get("c", [])
                    if isinstance(content, list) and content:
                        if isinstance(content[-1], list):
                            text_parts.append(extract_from_inlines(content[-1]))
            return "".join(text_parts)
        
        block_type = block.get("t", "")
        content = block.get("c", [])
        
        if block_type in ["Para", "Plain"]:
            if isinstance(content, list):
                return extract_from_inlines(content)
        elif block_type == "Header":
            if isinstance(content, list) and len(content) >= 3:
                return extract_from_inlines(content[2])
        elif block_type == "CodeBlock":
            if isinstance(content, list) and len(content) >= 2:
                return content[1]
        
        return ""
    
    def insert_block(self, position: int, block: Dict[str, Any]) -> None:
        """Insert a block at the specified position."""
        if position < 0:
            position = 0
        elif position > len(self.ast.blocks):
            position = len(self.ast.blocks)
        
        self.ast.blocks.insert(position, block)
        self._clear_caches()
    
    def delete_block(self, position: int) -> Optional[Dict[str, Any]]:
        """Delete a block at the specified position."""
        if 0 <= position < len(self.ast.blocks):
            deleted_block = self.ast.blocks.pop(position)
            self._clear_caches()
            return deleted_block
        return None
    
    def replace_block(self, position: int, new_block: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Replace a block at the specified position."""
        if 0 <= position < len(self.ast.blocks):
            old_block = self.ast.blocks[position]
            self.ast.blocks[position] = new_block
            self._clear_caches()
            return old_block
        return None
    
    def move_block(self, from_pos: int, to_pos: int) -> bool:
        """Move a block from one position to another."""
        if not (0 <= from_pos < len(self.ast.blocks)):
            return False
        
        if to_pos < 0:
            to_pos = 0
        elif to_pos > len(self.ast.blocks):
            to_pos = len(self.ast.blocks)
        
        block = self.ast.blocks.pop(from_pos)
        
        # Adjust target position if necessary
        if to_pos > from_pos:
            to_pos -= 1
        
        self.ast.blocks.insert(to_pos, block)
        self._clear_caches()
        return True
    
    def get_text_range(self, range_obj: Range) -> str:
        """Extract text content from a range."""
        if range_obj.start.block_index == range_obj.end.block_index:
            # Single block range
            block = self.ast.blocks[range_obj.start.block_index]
            block_text = self._extract_text_from_block(block)
            
            start_char = range_obj.start.char_offset or 0
            end_char = range_obj.end.char_offset or len(block_text)
            
            return block_text[start_char:end_char]
        else:
            # Multi-block range
            text_parts = []
            
            for block_idx in range(range_obj.start.block_index, range_obj.end.block_index + 1):
                if block_idx >= len(self.ast.blocks):
                    break
                
                block = self.ast.blocks[block_idx]
                block_text = self._extract_text_from_block(block)
                
                if block_idx == range_obj.start.block_index:
                    start_char = range_obj.start.char_offset or 0
                    block_text = block_text[start_char:]
                elif block_idx == range_obj.end.block_index:
                    end_char = range_obj.end.char_offset or len(block_text)
                    block_text = block_text[:end_char]
                
                text_parts.append(block_text)
            
            return "\n\n".join(text_parts)
    
    def create_paragraph(self, text: str) -> Dict[str, Any]:
        """Create a paragraph block with the given text."""
        # Simple implementation - create basic Str inlines
        words = text.split()
        inlines = []
        
        for i, word in enumerate(words):
            if i > 0:
                inlines.append({"t": "Space"})
            inlines.append({"t": "Str", "c": word})
        
        return {
            "t": "Para",
            "c": inlines
        }
    
    def create_header(self, level: int, text: str, element_id: str = "") -> Dict[str, Any]:
        """Create a header block."""
        # Simple implementation
        words = text.split()
        inlines = []
        
        for i, word in enumerate(words):
            if i > 0:
                inlines.append({"t": "Space"})
            inlines.append({"t": "Str", "c": word})
        
        return {
            "t": "Header",
            "c": [level, [element_id, [], []], inlines]
        }
    
    def _clear_caches(self) -> None:
        """Clear internal caches after modifications."""
        self._element_cache.clear()
        self._position_cache.clear()
    
    def validate_structure(self) -> List[str]:
        """Validate AST structure and return any issues."""
        issues = []
        
        for block_idx, block in enumerate(self.ast.blocks):
            block_type = block.get("t")
            if not block_type:
                issues.append(f"Block {block_idx} has no type")
                continue
            
            # Validate block structure based on type
            content = block.get("c")
            if content is None:
                issues.append(f"Block {block_idx} ({block_type}) has no content")
            
            # Type-specific validation
            if block_type == "Header":
                if not isinstance(content, list) or len(content) < 3:
                    issues.append(f"Header block {block_idx} has invalid structure")
                else:
                    level = content[0]
                    if not isinstance(level, int) or level < 1 or level > 6:
                        issues.append(f"Header block {block_idx} has invalid level: {level}")
        
        return issues