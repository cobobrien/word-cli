"""
Core document handling and representation modules.
"""

from .document_model import DocumentModel, WordMetadata, XMLFragments, ASTToXMLMapping
from .ast_handler import ASTHandler, Position, Range

__all__ = [
    "DocumentModel",
    "WordMetadata", 
    "XMLFragments",
    "ASTToXMLMapping",
    "ASTHandler",
    "Position",
    "Range",
]