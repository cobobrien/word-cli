"""
Context Management for Word CLI Agent.

This module manages document context for the AI agent, providing relevant
information for decision-making and maintaining conversation context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime
import hashlib

from ..core.document_model import DocumentModel
from ..core.ast_handler import ASTHandler, Position
from .sub_agents.search_agent import SearchAgent, SearchQuery, SearchType


@dataclass
class DocumentContext:
    """Represents the current document context for the agent."""
    
    # Document metadata
    document_name: str = ""
    word_count: int = 0
    paragraph_count: int = 0
    heading_count: int = 0
    is_modified: bool = False
    last_modified: str = ""
    
    # Recent changes
    recent_edits: List[str] = field(default_factory=list)
    active_section: Optional[str] = None
    
    # Content summaries
    document_summary: str = ""
    section_summaries: Dict[str, str] = field(default_factory=dict)
    
    # Search context
    relevant_content: List[str] = field(default_factory=list)
    content_hash: str = ""


@dataclass
class ConversationContext:
    """Tracks conversation-level context for better understanding."""
    
    current_topic: Optional[str] = None
    mentioned_elements: Set[str] = field(default_factory=set)
    referenced_documents: Set[str] = field(default_factory=set)
    
    # Patterns in conversation
    editing_patterns: List[str] = field(default_factory=list)
    user_preferences: Dict[str, Any] = field(default_factory=dict)


class ContextManager:
    """
    Manages document and conversation context for the Word CLI agent.
    
    Provides relevant context to help the agent make better decisions
    and maintain coherent conversations about document editing.
    """
    
    def __init__(self, max_context_chunks: int = 10, chunk_size: int = 1000):
        self.max_context_chunks = max_context_chunks
        self.chunk_size = chunk_size
        
        self.search_agent = SearchAgent()
        
        # Current context state
        self.document: Optional[DocumentModel] = None
        self.document_context = DocumentContext()
        self.conversation_context = ConversationContext()
        
        # Context caching
        self._context_cache: Dict[str, Any] = {}
        self._last_update_hash: Optional[str] = None
    
    def set_document(self, document: DocumentModel) -> None:
        """Set the current document and update context."""
        self.document = document
        self.update_context()
    
    def update_context(self) -> None:
        """Update document context after changes."""
        if not self.document:
            return
        
        # Check if document has changed since last update
        current_hash = self._calculate_document_hash(self.document)
        if current_hash == self._last_update_hash:
            return  # No changes, skip update
        
        self._last_update_hash = current_hash
        
        # Update document context
        self._update_document_context()
        
        # Clear relevant caches
        self._context_cache.clear()
    
    def get_relevant_context(self, query: str, include_content: bool = True) -> DocumentContext:
        """
        Get context relevant to a specific query or request.
        
        Args:
            query: User query or request
            include_content: Whether to include relevant content snippets
            
        Returns:
            DocumentContext with relevant information
        """
        if not self.document:
            return DocumentContext()
        
        # Check cache first
        cache_key = f"context_{hashlib.sha256(query.encode()).hexdigest()[:16]}"
        if cache_key in self._context_cache:
            return self._context_cache[cache_key]
        
        # Start with base document context
        context = DocumentContext(
            document_name=getattr(self.document.source_path, 'name', 'document') if self.document.source_path else 'document',
            word_count=self.document_context.word_count,
            paragraph_count=self.document_context.paragraph_count,
            heading_count=self.document_context.heading_count,
            is_modified=self.document.is_modified,
            last_modified=self.document_context.last_modified,
            document_summary=self.document_context.document_summary,
            content_hash=current_hash
        )
        
        if include_content:
            # Find relevant content based on query
            relevant_content = self._find_relevant_content(query)
            context.relevant_content = relevant_content
            
            # Update conversation context
            self._update_conversation_context(query)
        
        # Cache the context
        self._context_cache[cache_key] = context
        
        return context
    
    def _update_document_context(self) -> None:
        """Update the document context with current document state."""
        if not self.document:
            return
        
        stats = self.document.get_stats()
        
        self.document_context = DocumentContext(
            document_name=getattr(self.document.source_path, 'name', 'document') if self.document.source_path else 'document',
            word_count=stats['word_count'],
            paragraph_count=stats['paragraph_count'],
            heading_count=stats['heading_count'],
            is_modified=stats['is_modified'],
            last_modified=stats['last_modified'],
            document_summary=self._generate_document_summary(),
            section_summaries=self._generate_section_summaries()
        )
    
    def _generate_document_summary(self) -> str:
        """Generate a brief summary of the document structure."""
        if not self.document:
            return ""
        
        handler = ASTHandler(self.document.pandoc_ast)
        
        # Get document structure
        headings = handler.find_headings()
        stats = self.document.get_stats()
        
        summary_parts = [
            f"Document with {stats['word_count']} words across {stats['paragraph_count']} paragraphs."
        ]
        
        if headings:
            summary_parts.append(f"Contains {len(headings)} headings:")
            
            # List main headings (level 1 and 2)
            main_headings = []
            for pos, heading in headings:
                level = heading.get('c', [None])[0]
                if level and level <= 2:
                    text = handler._extract_text_from_block(heading)
                    main_headings.append(f"  • {text}")
            
            if main_headings:
                summary_parts.extend(main_headings[:5])  # First 5 headings
                if len(main_headings) > 5:
                    summary_parts.append(f"  ... and {len(main_headings) - 5} more sections")
        
        return " ".join(summary_parts)
    
    def _generate_section_summaries(self) -> Dict[str, str]:
        """Generate summaries for major document sections."""
        if not self.document:
            return {}
        
        handler = ASTHandler(self.document.pandoc_ast)
        headings = handler.find_headings()
        
        summaries = {}
        
        for pos, heading in headings:
            level = heading.get('c', [None])[0]
            if level and level <= 2:  # Only major headings
                heading_text = handler._extract_text_from_block(heading)
                
                # Get content after this heading
                section_content = self._get_section_content(pos.block_index, handler)
                if section_content:
                    summary = self._summarize_text(section_content)
                    summaries[heading_text] = summary
        
        return summaries
    
    def _get_section_content(self, heading_index: int, handler: ASTHandler) -> str:
        """Get content that belongs to a section starting at heading_index."""
        content_parts = []
        current_heading_level = None
        
        # Get the level of the current heading
        if heading_index < len(handler.ast.blocks):
            heading_block = handler.ast.blocks[heading_index]
            current_heading_level = heading_block.get('c', [None])[0]
        
        # Collect content until next heading of same or higher level
        for i in range(heading_index + 1, len(handler.ast.blocks)):
            block = handler.ast.blocks[i]
            
            # Stop at next heading of same or higher level
            if block.get('t') == 'Header':
                block_level = block.get('c', [None])[0]
                if block_level and current_heading_level and block_level <= current_heading_level:
                    break
            
            # Extract content
            block_content = handler._extract_text_from_block(block)
            if block_content.strip():
                content_parts.append(block_content)
                
                # Limit content length
                if len(' '.join(content_parts)) > self.chunk_size:
                    break
        
        return ' '.join(content_parts)
    
    def _summarize_text(self, text: str, max_length: int = 200) -> str:
        """Create a brief summary of text content."""
        if len(text) <= max_length:
            return text
        
        # Simple summarization: take first sentence(s) up to max_length
        sentences = text.split('. ')
        summary_parts = []
        current_length = 0
        
        for sentence in sentences:
            if current_length + len(sentence) + 2 <= max_length:
                summary_parts.append(sentence)
                current_length += len(sentence) + 2
            else:
                break
        
        if summary_parts:
            summary = '. '.join(summary_parts)
            if not summary.endswith('.'):
                summary += '.'
            return summary
        else:
            # Fallback: truncate at word boundary
            words = text[:max_length].split()
            return ' '.join(words[:-1]) + '...' if len(words) > 1 else text[:max_length] + '...'
    
    def _find_relevant_content(self, query: str) -> List[str]:
        """Find content relevant to the query."""
        if not self.document:
            return []
        
        # Use semantic search to find relevant content
        search_query = SearchQuery(
            text=query,
            search_type=SearchType.SEMANTIC,
            max_results=self.max_context_chunks,
            min_confidence=0.3
        )
        
        search_result = self.search_agent.search(search_query, self.document)
        
        relevant_content = []
        for match in search_result.matches:
            # Truncate content if too long
            content = match.content
            if len(content) > self.chunk_size:
                content = content[:self.chunk_size] + "..."
            
            # Add position information
            content_with_pos = f"[Paragraph {match.position.block_index + 1}] {content}"
            relevant_content.append(content_with_pos)
        
        return relevant_content
    
    def _update_conversation_context(self, query: str) -> None:
        """Update conversation context based on query."""
        query_lower = query.lower()
        
        # Extract mentioned elements
        if 'paragraph' in query_lower:
            import re
            para_matches = re.findall(r'paragraph\s+(\d+)', query_lower)
            for match in para_matches:
                self.conversation_context.mentioned_elements.add(f"paragraph_{match}")
        
        if 'section' in query_lower or 'heading' in query_lower:
            # Could extract section names here
            pass
        
        # Extract referenced documents
        doc_patterns = [r'(\w+\.docx)', r'document\s+"([^"]+)"']
        for pattern in doc_patterns:
            import re
            matches = re.findall(pattern, query_lower)
            for match in matches:
                self.conversation_context.referenced_documents.add(match)
        
        # Identify editing patterns
        editing_verbs = ['edit', 'change', 'modify', 'update', 'replace', 'delete', 'add', 'insert']
        for verb in editing_verbs:
            if verb in query_lower:
                if verb not in self.conversation_context.editing_patterns:
                    self.conversation_context.editing_patterns.append(verb)
                break
    
    def _calculate_document_hash(self, document: DocumentModel) -> str:
        """Calculate a hash of the document for change detection."""
        # Simple hash based on content
        content = document.get_text_content()
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def get_context_for_prompt(self, query: str) -> str:
        """
        Get formatted context string for inclusion in prompts.
        
        Args:
            query: User query to get context for
            
        Returns:
            Formatted context string
        """
        context = self.get_relevant_context(query, include_content=True)
        
        context_parts = [
            f"**Document:** {context.document_name}",
            f"**Stats:** {context.word_count} words, {context.paragraph_count} paragraphs, {context.heading_count} headings",
            f"**Status:** {'Modified' if context.is_modified else 'Unmodified'}"
        ]
        
        if context.document_summary:
            context_parts.append(f"**Structure:** {context.document_summary}")
        
        if context.relevant_content:
            context_parts.append("**Relevant Content:**")
            for i, content in enumerate(context.relevant_content[:3], 1):  # Limit to top 3
                context_parts.append(f"{i}. {content}")
        
        return "\n".join(context_parts)
    
    def get_conversation_summary(self) -> Dict[str, Any]:
        """Get summary of conversation context."""
        return {
            'current_topic': self.conversation_context.current_topic,
            'mentioned_elements': list(self.conversation_context.mentioned_elements),
            'referenced_documents': list(self.conversation_context.referenced_documents),
            'editing_patterns': self.conversation_context.editing_patterns,
            'document_context': {
                'name': self.document_context.document_name,
                'modified': self.document_context.is_modified,
                'word_count': self.document_context.word_count
            }
        }
    
    def clear_context(self) -> None:
        """Clear all context information."""
        self.document_context = DocumentContext()
        self.conversation_context = ConversationContext()
        self._context_cache.clear()
        self._last_update_hash = None