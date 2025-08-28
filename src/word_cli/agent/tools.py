"""
Tool definitions for the Word CLI agent.

This module defines all the tools that the AI agent can use to interact
with and modify Word documents, similar to how Claude Code has tools.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type, Union, Callable
from enum import Enum
import json

from ..core.document_model import DocumentModel
from ..core.ast_handler import ASTHandler, Position, Range, ElementType
from ..version.version_control import VersionController, DocumentChange, ChangeType
from ..converters.docx_to_ast import DocxToASTConverter
from pathlib import Path


class ToolCategory(Enum):
    """Categories of available tools."""
    NAVIGATION = "navigation"
    READING = "reading"
    EDITING = "editing"
    STRUCTURE = "structure"
    STYLE = "style"
    REFERENCE = "reference"
    VALIDATION = "validation"


@dataclass
class ToolCall:
    """Represents a tool call from the agent."""
    id: str
    name: str
    parameters: Dict[str, Any]


@dataclass
class ToolResult:
    """Result of a tool execution."""
    tool_call_id: str
    success: bool
    content: Optional[str] = None
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    document_modified: bool = False


@dataclass
class ToolExecutionResult:
    """Detailed result of tool execution."""
    success: bool
    content: str = ""
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    document_modified: bool = False
    changes: List[DocumentChange] = field(default_factory=list)


class DocumentTool(ABC):
    """Base class for all document tools."""
    
    name: str
    description: str
    category: ToolCategory
    parameters: Dict[str, Any]
    
    @abstractmethod
    async def execute(
        self, 
        parameters: Dict[str, Any],
        document: DocumentModel,
        version_controller: Optional[VersionController] = None
    ) -> ToolExecutionResult:
        """Execute the tool with given parameters."""
        pass
    
    def get_schema(self) -> Dict[str, Any]:
        """Get tool schema for Claude API."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.parameters,
                "required": list(self.parameters.keys())
            }
        }


# NAVIGATION TOOLS

class FindTextTool(DocumentTool):
    """Find text in the document."""
    
    name = "find_text"
    description = "Find specific text in the document and return its location"
    category = ToolCategory.NAVIGATION
    parameters = {
        "query": {
            "type": "string",
            "description": "Text to search for"
        },
        "case_sensitive": {
            "type": "boolean",
            "description": "Whether search should be case sensitive",
            "default": False
        }
    }
    
    async def execute(self, parameters: Dict[str, Any], document: DocumentModel, version_controller: Optional[VersionController] = None) -> ToolExecutionResult:
        query = parameters["query"]
        case_sensitive = parameters.get("case_sensitive", False)
        
        handler = ASTHandler(document.pandoc_ast)
        results = handler.find_by_text(query, case_sensitive)
        
        if not results:
            return ToolExecutionResult(
                success=True,
                content=f"Text '{query}' not found in document."
            )
        
        # Format results
        result_text = f"Found '{query}' in {len(results)} location(s):\n"
        for i, (pos, block) in enumerate(results[:5]):  # Limit to first 5 results
            content_preview = handler._extract_text_from_block(block)[:100]
            result_text += f"{i+1}. Paragraph {pos.block_index + 1}: {content_preview}...\n"
        
        if len(results) > 5:
            result_text += f"... and {len(results) - 5} more results"
        
        return ToolExecutionResult(
            success=True,
            content=result_text,
            data={
                "results": [{"position": str(pos), "content": handler._extract_text_from_block(block)[:200]} for pos, block in results]
            }
        )


class FindHeadingTool(DocumentTool):
    """Find headings in the document."""
    
    name = "find_heading"
    description = "Find a heading by text or level"
    category = ToolCategory.NAVIGATION
    parameters = {
        "heading_text": {
            "type": "string",
            "description": "Text to search for in headings (optional)"
        },
        "level": {
            "type": "integer",
            "description": "Heading level (1-6, optional)",
            "minimum": 1,
            "maximum": 6
        }
    }
    
    async def execute(self, parameters: Dict[str, Any], document: DocumentModel, version_controller: Optional[VersionController] = None) -> ToolExecutionResult:
        heading_text = parameters.get("heading_text")
        level = parameters.get("level")
        
        handler = ASTHandler(document.pandoc_ast)
        headings = handler.find_headings(level)
        
        if heading_text:
            # Filter by text content
            filtered_headings = []
            for pos, heading in headings:
                heading_content = handler._extract_text_from_block(heading)
                if heading_text.lower() in heading_content.lower():
                    filtered_headings.append((pos, heading))
            headings = filtered_headings
        
        if not headings:
            search_desc = f"level {level} headings" if level else "headings"
            if heading_text:
                search_desc += f" containing '{heading_text}'"
            return ToolExecutionResult(
                success=True,
                content=f"No {search_desc} found."
            )
        
        result_text = f"Found {len(headings)} heading(s):\n"
        for i, (pos, heading) in enumerate(headings):
            heading_level = heading.get("c", [None])[0]
            heading_content = handler._extract_text_from_block(heading)
            result_text += f"{i+1}. Level {heading_level} at paragraph {pos.block_index + 1}: {heading_content}\n"
        
        return ToolExecutionResult(
            success=True,
            content=result_text,
            data={
                "headings": [
                    {
                        "position": str(pos),
                        "level": heading.get("c", [None])[0],
                        "text": handler._extract_text_from_block(heading)
                    } for pos, heading in headings
                ]
            }
        )


class GetParagraphTool(DocumentTool):
    """Get a specific paragraph by index."""
    
    name = "get_paragraph"
    description = "Get the content of a specific paragraph by its number"
    category = ToolCategory.READING
    parameters = {
        "index": {
            "type": "integer",
            "description": "Paragraph number (1-based)"
        }
    }
    
    async def execute(self, parameters: Dict[str, Any], document: DocumentModel, version_controller: Optional[VersionController] = None) -> ToolExecutionResult:
        index = parameters["index"] - 1  # Convert to 0-based
        
        if index < 0 or index >= len(document.pandoc_ast.blocks):
            return ToolExecutionResult(
                success=False,
                error=f"Paragraph {parameters['index']} does not exist. Document has {len(document.pandoc_ast.blocks)} paragraphs."
            )
        
        handler = ASTHandler(document.pandoc_ast)
        block = document.pandoc_ast.blocks[index]
        content = handler._extract_text_from_block(block)
        block_type = block.get("t", "Unknown")
        
        return ToolExecutionResult(
            success=True,
            content=f"Paragraph {parameters['index']} ({block_type}):\n{content}",
            data={
                "index": index,
                "type": block_type,
                "content": content
            }
        )


# READING TOOLS

class ReadDocumentTool(DocumentTool):
    """Read document content within a range."""
    
    name = "read_document"
    description = "Read document content, optionally within a specific range"
    category = ToolCategory.READING
    parameters = {
        "start": {
            "type": "integer",
            "description": "Start paragraph number (1-based, optional)"
        },
        "end": {
            "type": "integer", 
            "description": "End paragraph number (1-based, optional)"
        },
        "max_length": {
            "type": "integer",
            "description": "Maximum characters to return (optional)",
            "default": 2000
        }
    }
    
    async def execute(self, parameters: Dict[str, Any], document: DocumentModel, version_controller: Optional[VersionController] = None) -> ToolExecutionResult:
        start = parameters.get("start", 1) - 1  # Convert to 0-based
        end = parameters.get("end", len(document.pandoc_ast.blocks)) - 1
        max_length = parameters.get("max_length", 2000)
        
        start = max(0, start)
        end = min(len(document.pandoc_ast.blocks) - 1, end)
        
        if start > end:
            return ToolExecutionResult(
                success=False,
                error="Start paragraph must be less than or equal to end paragraph"
            )
        
        handler = ASTHandler(document.pandoc_ast)
        content_parts = []
        
        for i in range(start, end + 1):
            block = document.pandoc_ast.blocks[i]
            block_content = handler._extract_text_from_block(block)
            content_parts.append(f"[{i+1}] {block_content}")
        
        full_content = "\n\n".join(content_parts)
        
        # Truncate if too long
        if len(full_content) > max_length:
            full_content = full_content[:max_length] + "...\n[Content truncated]"
        
        return ToolExecutionResult(
            success=True,
            content=f"Document content (paragraphs {start+1}-{end+1}):\n\n{full_content}",
            data={
                "start": start + 1,
                "end": end + 1,
                "paragraph_count": end - start + 1,
                "truncated": len(full_content) > max_length
            }
        )


class SummarizeDocumentTool(DocumentTool):
    """Get a summary of the document structure."""
    
    name = "summarize_document"
    description = "Get a structural summary of the document"
    category = ToolCategory.READING
    parameters = {}
    
    async def execute(self, parameters: Dict[str, Any], document: DocumentModel, version_controller: Optional[VersionController] = None) -> ToolExecutionResult:
        handler = ASTHandler(document.pandoc_ast)
        stats = document.get_stats()
        
        # Analyze structure
        headings = handler.find_headings()
        lists = handler.find_by_type(ElementType.ORDERED_LIST) + handler.find_by_type(ElementType.BULLET_LIST)
        tables = handler.find_by_type(ElementType.TABLE)
        
        summary_parts = [
            f"Document Summary:",
            f"• {stats['word_count']} words across {stats['paragraph_count']} paragraphs",
            f"• {len(headings)} headings",
            f"• {len(lists)} lists",
            f"• {len(tables)} tables"
        ]
        
        if headings:
            summary_parts.append("\nDocument Structure:")
            for i, (pos, heading) in enumerate(headings[:10]):  # First 10 headings
                level = heading.get("c", [None])[0]
                text = handler._extract_text_from_block(heading)
                indent = "  " * (level - 1) if level else ""
                summary_parts.append(f"{indent}• {text} (¶{pos.block_index + 1})")
            
            if len(headings) > 10:
                summary_parts.append(f"... and {len(headings) - 10} more headings")
        
        return ToolExecutionResult(
            success=True,
            content="\n".join(summary_parts),
            data={
                "stats": stats,
                "structure": {
                    "headings": len(headings),
                    "lists": len(lists),
                    "tables": len(tables)
                }
            }
        )


# EDITING TOOLS

class EditParagraphTool(DocumentTool):
    """Edit the content of a specific paragraph."""
    
    name = "edit_paragraph"
    description = "Replace the content of a specific paragraph"
    category = ToolCategory.EDITING
    parameters = {
        "index": {
            "type": "integer",
            "description": "Paragraph number (1-based)"
        },
        "new_text": {
            "type": "string",
            "description": "New text content for the paragraph"
        }
    }
    
    async def execute(self, parameters: Dict[str, Any], document: DocumentModel, version_controller: Optional[VersionController] = None) -> ToolExecutionResult:
        index = parameters["index"] - 1  # Convert to 0-based
        new_text = parameters["new_text"]
        
        if index < 0 or index >= len(document.pandoc_ast.blocks):
            return ToolExecutionResult(
                success=False,
                error=f"Paragraph {parameters['index']} does not exist. Document has {len(document.pandoc_ast.blocks)} paragraphs."
            )
        
        handler = ASTHandler(document.pandoc_ast)
        
        # Get old content for tracking
        old_block = document.pandoc_ast.blocks[index]
        old_text = handler._extract_text_from_block(old_block)
        
        # Create new paragraph
        new_block = handler.create_paragraph(new_text)
        
        # Replace the block
        handler.replace_block(index, new_block)
        document.mark_modified()
        
        # Create change record
        change = DocumentChange(
            change_type=ChangeType.CONTENT_MODIFY,
            target_path=f"paragraph[{index}]",
            old_value=old_text,
            new_value=new_text,
            description=f"Edited paragraph {parameters['index']}"
        )
        
        return ToolExecutionResult(
            success=True,
            content=f"Successfully updated paragraph {parameters['index']}",
            document_modified=True,
            changes=[change],
            data={
                "index": parameters["index"],
                "old_text": old_text[:100] + "..." if len(old_text) > 100 else old_text,
                "new_text": new_text[:100] + "..." if len(new_text) > 100 else new_text
            }
        )


class InsertTextTool(DocumentTool):
    """Insert text at a specific position."""
    
    name = "insert_text"
    description = "Insert new text as a paragraph at a specific position"
    category = ToolCategory.EDITING
    parameters = {
        "position": {
            "type": "integer",
            "description": "Position to insert at (1-based, after this paragraph)"
        },
        "text": {
            "type": "string",
            "description": "Text to insert"
        }
    }
    
    async def execute(self, parameters: Dict[str, Any], document: DocumentModel, version_controller: Optional[VersionController] = None) -> ToolExecutionResult:
        position = parameters["position"]  # 1-based position
        text = parameters["text"]
        
        if position < 0 or position > len(document.pandoc_ast.blocks):
            return ToolExecutionResult(
                success=False,
                error=f"Invalid position {position}. Document has {len(document.pandoc_ast.blocks)} paragraphs."
            )
        
        handler = ASTHandler(document.pandoc_ast)
        
        # Create new paragraph
        new_block = handler.create_paragraph(text)
        
        # Insert the block
        handler.insert_block(position, new_block)
        document.mark_modified()
        
        # Create change record
        change = DocumentChange(
            change_type=ChangeType.CONTENT_INSERT,
            target_path=f"paragraph[{position}]",
            new_value=text,
            description=f"Inserted text at position {position}"
        )
        
        return ToolExecutionResult(
            success=True,
            content=f"Successfully inserted text at position {position}",
            document_modified=True,
            changes=[change],
            data={
                "position": position,
                "text": text[:100] + "..." if len(text) > 100 else text
            }
        )


class DeleteParagraphTool(DocumentTool):
    """Delete a specific paragraph."""
    
    name = "delete_paragraph"
    description = "Delete a specific paragraph from the document"
    category = ToolCategory.EDITING
    parameters = {
        "index": {
            "type": "integer",
            "description": "Paragraph number to delete (1-based)"
        }
    }
    
    async def execute(self, parameters: Dict[str, Any], document: DocumentModel, version_controller: Optional[VersionController] = None) -> ToolExecutionResult:
        index = parameters["index"] - 1  # Convert to 0-based
        
        if index < 0 or index >= len(document.pandoc_ast.blocks):
            return ToolExecutionResult(
                success=False,
                error=f"Paragraph {parameters['index']} does not exist. Document has {len(document.pandoc_ast.blocks)} paragraphs."
            )
        
        handler = ASTHandler(document.pandoc_ast)
        
        # Get content for tracking
        old_block = document.pandoc_ast.blocks[index]
        old_text = handler._extract_text_from_block(old_block)
        
        # Delete the block
        deleted_block = handler.delete_block(index)
        if deleted_block:
            document.mark_modified()
            
            # Create change record
            change = DocumentChange(
                change_type=ChangeType.CONTENT_DELETE,
                target_path=f"paragraph[{index}]",
                old_value=old_text,
                description=f"Deleted paragraph {parameters['index']}"
            )
            
            return ToolExecutionResult(
                success=True,
                content=f"Successfully deleted paragraph {parameters['index']}",
                document_modified=True,
                changes=[change],
                data={
                    "index": parameters["index"],
                    "deleted_text": old_text[:100] + "..." if len(old_text) > 100 else old_text
                }
            )
        else:
            return ToolExecutionResult(
                success=False,
                error=f"Failed to delete paragraph {parameters['index']}"
            )


class ReplaceAllTool(DocumentTool):
    """Find and replace all instances of text."""
    
    name = "replace_all"
    description = "Find and replace all instances of text in the document"
    category = ToolCategory.EDITING
    parameters = {
        "find": {
            "type": "string",
            "description": "Text to find"
        },
        "replace": {
            "type": "string",
            "description": "Text to replace with"
        },
        "case_sensitive": {
            "type": "boolean",
            "description": "Whether search should be case sensitive",
            "default": False
        }
    }
    
    async def execute(self, parameters: Dict[str, Any], document: DocumentModel, version_controller: Optional[VersionController] = None) -> ToolExecutionResult:
        find_text = parameters["find"]
        replace_text = parameters["replace"]
        case_sensitive = parameters.get("case_sensitive", False)
        
        handler = ASTHandler(document.pandoc_ast)
        replacements_made = 0
        changes = []
        
        # Find all instances first
        results = handler.find_by_text(find_text, case_sensitive)
        
        if not results:
            return ToolExecutionResult(
                success=True,
                content=f"No instances of '{find_text}' found to replace."
            )
        
        # Process replacements (in reverse order to maintain indices)
        for pos, block in reversed(results):
            block_content = handler._extract_text_from_block(block)
            
            if case_sensitive:
                new_content = block_content.replace(find_text, replace_text)
            else:
                # Case-insensitive replace
                import re
                new_content = re.sub(re.escape(find_text), replace_text, block_content, flags=re.IGNORECASE)
            
            if new_content != block_content:
                # Create new paragraph and replace
                new_block = handler.create_paragraph(new_content)
                handler.replace_block(pos.block_index, new_block)
                replacements_made += 1
                
                # Track change
                change = DocumentChange(
                    change_type=ChangeType.CONTENT_MODIFY,
                    target_path=f"paragraph[{pos.block_index}]",
                    old_value=block_content,
                    new_value=new_content,
                    description=f"Replace '{find_text}' with '{replace_text}'"
                )
                changes.append(change)
        
        if replacements_made > 0:
            document.mark_modified()
        
        return ToolExecutionResult(
            success=True,
            content=f"Replaced {replacements_made} instance(s) of '{find_text}' with '{replace_text}'",
            document_modified=replacements_made > 0,
            changes=changes,
            data={
                "find": find_text,
                "replace": replace_text,
                "replacements": replacements_made
            }
        )


# REFERENCE TOOLS

class OpenReferenceDocumentTool(DocumentTool):
    """Open another document for reference."""
    
    name = "open_reference_document"
    description = "Open another Word document for reference purposes"
    category = ToolCategory.REFERENCE
    parameters = {
        "path": {
            "type": "string",
            "description": "Path to the document to open for reference"
        }
    }
    
    async def execute(self, parameters: Dict[str, Any], document: DocumentModel, version_controller: Optional[VersionController] = None) -> ToolExecutionResult:
        doc_path = Path(parameters["path"])
        
        if not doc_path.exists():
            return ToolExecutionResult(
                success=False,
                error=f"Document not found: {doc_path}"
            )
        
        if not doc_path.suffix.lower() == '.docx':
            return ToolExecutionResult(
                success=False,
                error=f"Only .docx files are supported. Got: {doc_path.suffix}"
            )
        
        try:
            # Load the reference document
            converter = DocxToASTConverter()
            ref_document = converter.convert(doc_path)
            
            # Get basic info about the reference document
            ref_stats = ref_document.get_stats()
            
            # Store reference document (this would need global state management in a real implementation)
            # For now, just return the summary
            
            return ToolExecutionResult(
                success=True,
                content=f"Opened reference document: {doc_path.name}\nWord count: {ref_stats['word_count']}, Paragraphs: {ref_stats['paragraph_count']}",
                data={
                    "path": str(doc_path),
                    "name": doc_path.name,
                    "stats": ref_stats
                }
            )
            
        except Exception as e:
            return ToolExecutionResult(
                success=False,
                error=f"Failed to open reference document: {str(e)}"
            )


# VALIDATION TOOLS

class ValidateDocumentTool(DocumentTool):
    """Validate document integrity."""
    
    name = "validate_document"
    description = "Check document for structural integrity and issues"
    category = ToolCategory.VALIDATION
    parameters = {}
    
    async def execute(self, parameters: Dict[str, Any], document: DocumentModel, version_controller: Optional[VersionController] = None) -> ToolExecutionResult:
        # Check document integrity
        issues = document.validate_integrity()
        
        # Check AST structure
        handler = ASTHandler(document.pandoc_ast)
        ast_issues = handler.validate_structure()
        
        all_issues = issues + ast_issues
        
        if not all_issues:
            return ToolExecutionResult(
                success=True,
                content="Document validation passed. No issues found.",
                data={"valid": True, "issues": []}
            )
        else:
            issue_text = "Document validation found issues:\n" + "\n".join(f"• {issue}" for issue in all_issues)
            return ToolExecutionResult(
                success=True,
                content=issue_text,
                data={"valid": False, "issues": all_issues}
            )


class ToolRegistry:
    """Registry for all available document tools."""
    
    def __init__(self):
        self.tools: Dict[str, DocumentTool] = {}
        self._register_default_tools()
    
    def _register_default_tools(self):
        """Register all default tools."""
        default_tools = [
            # Navigation
            FindTextTool(),
            FindHeadingTool(),
            GetParagraphTool(),
            
            # Reading
            ReadDocumentTool(),
            SummarizeDocumentTool(),
            
            # Editing
            EditParagraphTool(),
            InsertTextTool(),
            DeleteParagraphTool(),
            ReplaceAllTool(),
            
            # Reference
            OpenReferenceDocumentTool(),
            
            # Validation
            ValidateDocumentTool(),
        ]
        
        for tool in default_tools:
            self.register_tool(tool)
    
    def register_tool(self, tool: DocumentTool) -> None:
        """Register a tool."""
        self.tools[tool.name] = tool
    
    def get_tool(self, name: str) -> Optional[DocumentTool]:
        """Get a tool by name."""
        return self.tools.get(name)
    
    def get_tools_by_category(self, category: ToolCategory) -> List[DocumentTool]:
        """Get all tools in a category."""
        return [tool for tool in self.tools.values() if tool.category == category]
    
    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Get tool schemas for Claude API."""
        return [tool.get_schema() for tool in self.tools.values()]
    
    def list_tools(self) -> List[str]:
        """List all available tool names."""
        return list(self.tools.keys())


def get_all_tools() -> ToolRegistry:
    """Get the default tool registry."""
    return ToolRegistry()