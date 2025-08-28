"""
Search Agent for intelligent document search and content discovery.

This agent provides semantic search capabilities, going beyond simple
text matching to understand content meaning and context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
import re
from difflib import SequenceMatcher

from ...core.document_model import DocumentModel
from ...core.ast_handler import ASTHandler, Position, ElementType


class SearchType(Enum):
    """Types of search operations."""
    LITERAL = "literal"        # Exact text matching
    SEMANTIC = "semantic"      # Meaning-based search
    STRUCTURAL = "structural"  # Document structure search
    REGEX = "regex"           # Pattern matching
    FUZZY = "fuzzy"           # Approximate matching


@dataclass
class SearchMatch:
    """Represents a search result match."""
    
    position: Position
    content: str
    match_type: SearchType
    confidence: float
    context: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def preview(self, max_length: int = 100) -> str:
        """Get a preview of the match with context."""
        preview_text = self.context or self.content
        if len(preview_text) > max_length:
            return preview_text[:max_length] + "..."
        return preview_text


@dataclass
class SearchQuery:
    """Represents a search query with parameters."""
    
    text: str
    search_type: SearchType = SearchType.LITERAL
    case_sensitive: bool = False
    whole_words: bool = False
    max_results: int = 10
    min_confidence: float = 0.5
    include_context: bool = True
    context_size: int = 50


@dataclass
class SearchResult:
    """Complete search result with matches and metadata."""
    
    query: SearchQuery
    matches: List[SearchMatch] = field(default_factory=list)
    total_found: int = 0
    search_time_ms: float = 0.0
    suggestions: List[str] = field(default_factory=list)
    
    @property
    def has_results(self) -> bool:
        """Check if search returned any results."""
        return len(self.matches) > 0
    
    @property
    def best_match(self) -> Optional[SearchMatch]:
        """Get the highest confidence match."""
        if not self.matches:
            return None
        return max(self.matches, key=lambda m: m.confidence)


class SearchAgent:
    """
    Agent responsible for intelligent document search operations.
    
    Provides various search capabilities from simple text matching
    to advanced semantic search and pattern recognition.
    """
    
    def __init__(self):
        self.common_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'up', 'about', 'into', 'over', 'after',
            'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has',
            'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should'
        }
        
        # Semantic keyword mappings
        self.semantic_mappings = {
            'payment': ['payment', 'pay', 'fee', 'cost', 'charge', 'amount', 'price'],
            'agreement': ['agreement', 'contract', 'deal', 'arrangement', 'accord'],
            'termination': ['termination', 'end', 'cancel', 'conclude', 'finish'],
            'liability': ['liability', 'responsibility', 'obligation', 'duty'],
            'confidential': ['confidential', 'private', 'secret', 'proprietary'],
        }
    
    def search(self, query: SearchQuery, document: DocumentModel) -> SearchResult:
        """
        Perform a comprehensive search of the document.
        
        Args:
            query: Search query with parameters
            document: Document to search
            
        Returns:
            SearchResult with matches and metadata
        """
        import time
        start_time = time.time()
        
        handler = ASTHandler(document.pandoc_ast)
        matches = []
        
        # Perform search based on type
        if query.search_type == SearchType.LITERAL:
            matches = self._literal_search(query, handler)
        elif query.search_type == SearchType.SEMANTIC:
            matches = self._semantic_search(query, handler)
        elif query.search_type == SearchType.STRUCTURAL:
            matches = self._structural_search(query, handler)
        elif query.search_type == SearchType.REGEX:
            matches = self._regex_search(query, handler)
        elif query.search_type == SearchType.FUZZY:
            matches = self._fuzzy_search(query, handler)
        
        # Filter by confidence
        matches = [m for m in matches if m.confidence >= query.min_confidence]
        
        # Sort by confidence (highest first)
        matches.sort(key=lambda m: m.confidence, reverse=True)
        
        # Limit results
        if query.max_results > 0:
            matches = matches[:query.max_results]
        
        # Add context if requested
        if query.include_context:
            for match in matches:
                match.context = self._get_context(match.position, handler, query.context_size)
        
        # Generate suggestions if no results
        suggestions = []
        if not matches:
            suggestions = self._generate_suggestions(query, document)
        
        search_time = (time.time() - start_time) * 1000
        
        return SearchResult(
            query=query,
            matches=matches,
            total_found=len(matches),
            search_time_ms=search_time,
            suggestions=suggestions
        )
    
    def _literal_search(self, query: SearchQuery, handler: ASTHandler) -> List[SearchMatch]:
        """Perform literal text search."""
        matches = []
        search_text = query.text if query.case_sensitive else query.text.lower()
        
        for i, block in enumerate(handler.ast.blocks):
            block_text = handler._extract_text_from_block(block)
            compare_text = block_text if query.case_sensitive else block_text.lower()
            
            if query.whole_words:
                # Word boundary search
                pattern = r'\b' + re.escape(search_text) + r'\b'
                flags = 0 if query.case_sensitive else re.IGNORECASE
                if re.search(pattern, block_text, flags):
                    matches.append(SearchMatch(
                        position=Position(block_index=i),
                        content=block_text,
                        match_type=SearchType.LITERAL,
                        confidence=1.0,
                        metadata={'match_method': 'whole_word'}
                    ))
            else:
                # Substring search
                if search_text in compare_text:
                    matches.append(SearchMatch(
                        position=Position(block_index=i),
                        content=block_text,
                        match_type=SearchType.LITERAL,
                        confidence=1.0,
                        metadata={'match_method': 'substring'}
                    ))
        
        return matches
    
    def _semantic_search(self, query: SearchQuery, handler: ASTHandler) -> List[SearchMatch]:
        """Perform semantic search using keyword mappings and context."""
        matches = []
        query_words = self._extract_keywords(query.text.lower())
        
        # Expand query with semantic alternatives
        expanded_terms = set(query_words)
        for word in query_words:
            if word in self.semantic_mappings:
                expanded_terms.update(self.semantic_mappings[word])
        
        for i, block in enumerate(handler.ast.blocks):
            block_text = handler._extract_text_from_block(block)
            block_words = self._extract_keywords(block_text.lower())
            
            # Calculate semantic similarity
            confidence = self._calculate_semantic_similarity(expanded_terms, block_words)
            
            if confidence > 0:
                matches.append(SearchMatch(
                    position=Position(block_index=i),
                    content=block_text,
                    match_type=SearchType.SEMANTIC,
                    confidence=confidence,
                    metadata={
                        'matched_terms': list(expanded_terms.intersection(block_words)),
                        'query_words': list(query_words)
                    }
                ))
        
        return matches
    
    def _structural_search(self, query: SearchQuery, handler: ASTHandler) -> List[SearchMatch]:
        """Search for structural elements (headings, lists, etc.)."""
        matches = []
        query_lower = query.text.lower()
        
        # Search in headings
        if 'heading' in query_lower or 'title' in query_lower:
            headings = handler.find_headings()
            for pos, heading in headings:
                heading_text = handler._extract_text_from_block(heading)
                if self._text_matches(query.text, heading_text, query.case_sensitive):
                    level = heading.get('c', [None])[0]
                    matches.append(SearchMatch(
                        position=pos,
                        content=heading_text,
                        match_type=SearchType.STRUCTURAL,
                        confidence=0.9,
                        metadata={'element_type': 'heading', 'level': level}
                    ))
        
        # Search in lists
        if 'list' in query_lower or 'item' in query_lower:
            lists = (handler.find_by_type(ElementType.ORDERED_LIST) + 
                    handler.find_by_type(ElementType.BULLET_LIST))
            for pos, list_elem in lists:
                list_text = handler._extract_text_from_block(list_elem)
                if self._text_matches(query.text, list_text, query.case_sensitive):
                    matches.append(SearchMatch(
                        position=pos,
                        content=list_text,
                        match_type=SearchType.STRUCTURAL,
                        confidence=0.8,
                        metadata={'element_type': 'list'}
                    ))
        
        return matches
    
    def _regex_search(self, query: SearchQuery, handler: ASTHandler) -> List[SearchMatch]:
        """Perform regex pattern search."""
        matches = []
        
        try:
            flags = 0 if query.case_sensitive else re.IGNORECASE
            pattern = re.compile(query.text, flags)
            
            for i, block in enumerate(handler.ast.blocks):
                block_text = handler._extract_text_from_block(block)
                
                regex_matches = list(pattern.finditer(block_text))
                if regex_matches:
                    # Calculate confidence based on match quality
                    confidence = min(1.0, len(regex_matches) * 0.3 + 0.4)
                    
                    matches.append(SearchMatch(
                        position=Position(block_index=i),
                        content=block_text,
                        match_type=SearchType.REGEX,
                        confidence=confidence,
                        metadata={
                            'pattern': query.text,
                            'match_count': len(regex_matches),
                            'matches': [m.group() for m in regex_matches[:3]]  # First 3 matches
                        }
                    ))
        except re.error as e:
            # Invalid regex pattern
            return []
        
        return matches
    
    def _fuzzy_search(self, query: SearchQuery, handler: ASTHandler) -> List[SearchMatch]:
        """Perform fuzzy (approximate) search."""
        matches = []
        query_words = query.text.lower().split()
        
        for i, block in enumerate(handler.ast.blocks):
            block_text = handler._extract_text_from_block(block)
            
            # Calculate fuzzy similarity for each sentence/paragraph
            similarity = self._calculate_fuzzy_similarity(query.text, block_text)
            
            if similarity >= query.min_confidence:
                matches.append(SearchMatch(
                    position=Position(block_index=i),
                    content=block_text,
                    match_type=SearchType.FUZZY,
                    confidence=similarity,
                    metadata={'similarity_score': similarity}
                ))
        
        return matches
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract meaningful keywords from text."""
        # Simple keyword extraction (remove common words)
        words = re.findall(r'\b\w+\b', text.lower())
        return [word for word in words if word not in self.common_words and len(word) > 2]
    
    def _calculate_semantic_similarity(self, query_terms: set, block_words: set) -> float:
        """Calculate semantic similarity between query terms and block content."""
        if not query_terms or not block_words:
            return 0.0
        
        # Count matching terms
        matches = len(query_terms.intersection(block_words))
        
        # Calculate similarity score
        similarity = matches / len(query_terms)
        
        # Boost score if many terms match
        if matches > 2:
            similarity = min(1.0, similarity * 1.2)
        
        return similarity
    
    def _calculate_fuzzy_similarity(self, query: str, text: str) -> float:
        """Calculate fuzzy string similarity."""
        return SequenceMatcher(None, query.lower(), text.lower()).ratio()
    
    def _text_matches(self, query: str, text: str, case_sensitive: bool) -> bool:
        """Check if query matches text with case sensitivity option."""
        if case_sensitive:
            return query in text
        else:
            return query.lower() in text.lower()
    
    def _get_context(self, position: Position, handler: ASTHandler, context_size: int) -> str:
        """Get context around a search match."""
        block_text = handler._extract_text_from_block(
            handler.ast.blocks[position.block_index]
        )
        
        # For now, just return the paragraph context
        # In a more advanced implementation, could include surrounding paragraphs
        if len(block_text) <= context_size * 2:
            return block_text
        
        # Try to find the match position and center the context around it
        return block_text[:context_size * 2] + "..."
    
    def _generate_suggestions(self, query: SearchQuery, document: DocumentModel) -> List[str]:
        """Generate search suggestions when no results are found."""
        suggestions = []
        
        # Suggest different search types
        if query.search_type == SearchType.LITERAL:
            suggestions.append("Try a semantic search to find related content")
            suggestions.append("Check spelling and try a fuzzy search")
        
        # Suggest related terms based on semantic mappings
        query_words = self._extract_keywords(query.text.lower())
        for word in query_words:
            if word in self.semantic_mappings:
                alternatives = self.semantic_mappings[word]
                suggestions.append(f"Try searching for: {', '.join(alternatives)}")
        
        # Suggest structural search if query contains structural terms
        structural_terms = ['section', 'heading', 'title', 'paragraph', 'list']
        if any(term in query.text.lower() for term in structural_terms):
            suggestions.append("Try a structural search to find document elements")
        
        return suggestions[:3]  # Limit to 3 suggestions
    
    def find_similar_content(self, reference_text: str, document: DocumentModel, min_similarity: float = 0.6) -> List[SearchMatch]:
        """Find content similar to a reference text."""
        query = SearchQuery(
            text=reference_text,
            search_type=SearchType.FUZZY,
            min_confidence=min_similarity
        )
        
        result = self.search(query, document)
        return result.matches
    
    def find_clause_references(self, clause_id: str, document: DocumentModel) -> List[SearchMatch]:
        """Find references to a specific clause (e.g., 'clause 3.2', 'section 4.1')."""
        patterns = [
            f"clause\\s+{re.escape(clause_id)}",
            f"section\\s+{re.escape(clause_id)}",
            f"paragraph\\s+{re.escape(clause_id)}",
            f"\\b{re.escape(clause_id)}\\b"
        ]
        
        matches = []
        for pattern in patterns:
            query = SearchQuery(
                text=pattern,
                search_type=SearchType.REGEX,
                case_sensitive=False
            )
            
            result = self.search(query, document)
            matches.extend(result.matches)
        
        # Remove duplicates based on position
        unique_matches = []
        seen_positions = set()
        
        for match in matches:
            pos_key = (match.position.block_index, match.position.inline_index)
            if pos_key not in seen_positions:
                unique_matches.append(match)
                seen_positions.add(pos_key)
        
        return unique_matches
    
    def search_by_document_section(self, section_name: str, document: DocumentModel) -> Optional[SearchMatch]:
        """Find a document section by name or number."""
        handler = ASTHandler(document.pandoc_ast)
        
        # First try to find as heading
        headings = handler.find_headings()
        for pos, heading in headings:
            heading_text = handler._extract_text_from_block(heading)
            if self._text_matches(section_name, heading_text, False):
                return SearchMatch(
                    position=pos,
                    content=heading_text,
                    match_type=SearchType.STRUCTURAL,
                    confidence=1.0,
                    metadata={'element_type': 'heading'}
                )
        
        # Then try semantic search
        query = SearchQuery(
            text=section_name,
            search_type=SearchType.SEMANTIC,
            max_results=1
        )
        
        result = self.search(query, document)
        return result.best_match