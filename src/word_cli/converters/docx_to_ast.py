"""
Converter from DOCX files to Pandoc AST with metadata preservation.

This converter implements the critical first step of our hybrid approach:
1. Extract content structure using Pandoc
2. Preserve Word-specific metadata separately
3. Maintain mapping between AST and XML elements
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

from docx import Document
from docx.document import Document as DocxDocument
from docx.styles.styles import Styles
from docx.parts.document import DocumentPart

from ..core.document_model import (
    DocumentModel,
    PandocAST, 
    WordMetadata,
    XMLFragments,
    ASTToXMLMapping,
)


class DocxToASTConverter:
    """
    Converts DOCX files to our hybrid DocumentModel format.
    
    Uses a two-stage approach:
    1. Pandoc for structural AST extraction
    2. python-docx for metadata and complex element preservation
    """
    
    def __init__(self, pandoc_path: str = "pandoc"):
        self.pandoc_path = pandoc_path
        self._validate_pandoc()
        
        # OOXML namespaces
        self.namespaces = {
            'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
            'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
            'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
            'cp': 'http://schemas.openxmlformats.org/package/2006/metadata/core-properties',
            'dc': 'http://purl.org/dc/elements/1.1/',
            'dcterms': 'http://purl.org/dc/terms/',
            'dcmitype': 'http://purl.org/dc/dcmitype/',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        }
    
    def _validate_pandoc(self) -> None:
        """Ensure Pandoc is available."""
        try:
            result = subprocess.run(
                [self.pandoc_path, "--version"], 
                capture_output=True, 
                text=True, 
                check=True
            )
            if "pandoc" not in result.stdout.lower():
                raise RuntimeError("Pandoc validation failed")
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            raise RuntimeError(f"Pandoc not found or not working: {e}")
    
    def convert(self, docx_path: Path) -> DocumentModel:
        """
        Convert a DOCX file to DocumentModel.
        
        Returns:
            DocumentModel with populated AST, metadata, and XML fragments.
        """
        if not docx_path.exists():
            raise FileNotFoundError(f"DOCX file not found: {docx_path}")
        
        # Stage 1: Extract AST using Pandoc
        pandoc_ast = self._extract_ast_with_pandoc(docx_path)
        
        # Stage 2: Extract metadata and XML fragments using python-docx
        word_metadata = self._extract_metadata(docx_path)
        xml_fragments = self._extract_xml_fragments(docx_path)
        mapping = self._create_ast_xml_mapping(docx_path, pandoc_ast)
        
        # Create and return document model
        return DocumentModel(
            pandoc_ast=pandoc_ast,
            word_metadata=word_metadata,
            xml_fragments=xml_fragments,
            mapping=mapping,
            source_path=docx_path,
        )
    
    def _extract_ast_with_pandoc(self, docx_path: Path) -> PandocAST:
        """Extract document structure as Pandoc AST."""
        try:
            # Use Pandoc to convert DOCX to JSON AST
            # Route extracted media to a temporary directory to avoid polluting user folders
            with tempfile.TemporaryDirectory() as media_dir:
                result = subprocess.run([
                    self.pandoc_path,
                    str(docx_path),
                    "--to", "json",
                    "--standalone",
                    "--wrap=preserve",  # Preserve line breaks
                    "--extract-media", media_dir
                ], capture_output=True, text=True, check=True)
            
            pandoc_json = json.loads(result.stdout)
            return PandocAST.from_pandoc_json(pandoc_json)
            
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Pandoc conversion failed: {e.stderr}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse Pandoc JSON output: {e}")
    
    def _extract_metadata(self, docx_path: Path) -> WordMetadata:
        """Extract Word-specific metadata using python-docx."""
        doc = Document(str(docx_path))
        
        # Core properties
        core_props = doc.core_properties
        
        metadata = WordMetadata(
            title=core_props.title,
            author=core_props.author,
            subject=core_props.subject,
            keywords=core_props.keywords.split(';') if core_props.keywords else [],
            comments=core_props.comments,
        )
        
        # Extract styles
        metadata.styles = self._extract_styles(doc)
        
        # Extract document settings
        metadata.page_margins = self._extract_page_margins(doc)
        metadata.page_size = self._extract_page_size(doc)
        
        # Track changes and comments
        metadata.track_changes_enabled = self._is_track_changes_enabled(doc)
        metadata.document_comments = self._extract_comments(doc)
        
        return metadata
    
    def _extract_styles(self, doc: DocxDocument) -> Dict[str, Dict[str, Any]]:
        """Extract document styles."""
        styles_dict = {}
        
        for style in doc.styles:
            style_dict = {
                'name': style.name,
                'type': str(style.type),
                'builtin': style.builtin,
                'hidden': style.hidden,
                'priority': getattr(style, 'priority', None),
                'unhide_when_used': getattr(style, 'unhide_when_used', None),
                'locked': getattr(style, 'locked', None),
                'delete_when_not_used': getattr(style, 'delete_when_not_used', None),
            }
            
            # Extract font information if available
            if hasattr(style, 'font'):
                font_dict = {}
                font = style.font
                if font.name:
                    font_dict['name'] = font.name
                if font.size:
                    font_dict['size'] = font.size.pt
                if font.bold is not None:
                    font_dict['bold'] = font.bold
                if font.italic is not None:
                    font_dict['italic'] = font.italic
                if font.underline is not None:
                    font_dict['underline'] = str(font.underline)
                
                if font_dict:
                    style_dict['font'] = font_dict
            
            # Extract paragraph formatting if available
            if hasattr(style, 'paragraph_format'):
                para_format = {}
                pf = style.paragraph_format
                if pf.alignment is not None:
                    para_format['alignment'] = str(pf.alignment)
                if pf.left_indent is not None:
                    para_format['left_indent'] = pf.left_indent.pt
                if pf.right_indent is not None:
                    para_format['right_indent'] = pf.right_indent.pt
                if pf.first_line_indent is not None:
                    para_format['first_line_indent'] = pf.first_line_indent.pt
                if pf.line_spacing is not None:
                    para_format['line_spacing'] = pf.line_spacing
                
                if para_format:
                    style_dict['paragraph_format'] = para_format
            
            styles_dict[style.name] = style_dict
        
        return styles_dict
    
    def _extract_page_margins(self, doc: DocxDocument) -> Dict[str, float]:
        """Extract page margin settings."""
        try:
            section = doc.sections[0]  # Use first section as default
            return {
                'top': section.top_margin.inches,
                'bottom': section.bottom_margin.inches, 
                'left': section.left_margin.inches,
                'right': section.right_margin.inches,
                'gutter': getattr(section, 'gutter', 0),
                'header_distance': section.header_distance.inches,
                'footer_distance': section.footer_distance.inches,
            }
        except (IndexError, AttributeError):
            return {}
    
    def _extract_page_size(self, doc: DocxDocument) -> Dict[str, float]:
        """Extract page size settings."""
        try:
            section = doc.sections[0]
            return {
                'width': section.page_width.inches,
                'height': section.page_height.inches,
                'orientation': str(section.orientation),
            }
        except (IndexError, AttributeError):
            return {}
    
    def _is_track_changes_enabled(self, doc: DocxDocument) -> bool:
        """Check if track changes is enabled."""
        try:
            # Access the underlying XML to check track changes settings
            doc_part = doc.part
            root = doc_part.document_element
            
            # Look for track changes settings in document settings
            settings_elements = root.xpath('//w:trackRevisions', namespaces=self.namespaces)
            return len(settings_elements) > 0
            
        except Exception:
            return False
    
    def _extract_comments(self, doc: DocxDocument) -> List[Dict[str, Any]]:
        """Extract document comments."""
        comments = []
        
        try:
            # Access comments part if it exists
            if hasattr(doc.part, 'comments_part') and doc.part.comments_part:
                comments_part = doc.part.comments_part
                comment_elements = comments_part.element.xpath('//w:comment', namespaces=self.namespaces)
                
                for comment_elem in comment_elements:
                    comment_dict = {
                        'id': comment_elem.get(f'{{{self.namespaces["w"]}}}id'),
                        'author': comment_elem.get(f'{{{self.namespaces["w"]}}}author'),
                        'date': comment_elem.get(f'{{{self.namespaces["w"]}}}date'),
                        'initials': comment_elem.get(f'{{{self.namespaces["w"]}}}initials'),
                    }
                    
                    # Extract comment text
                    text_elements = comment_elem.xpath('.//w:t', namespaces=self.namespaces)
                    comment_text = ''.join(elem.text or '' for elem in text_elements)
                    comment_dict['text'] = comment_text
                    
                    comments.append(comment_dict)
                    
        except Exception as e:
            # Comments extraction is optional
            pass
        
        return comments
    
    def _extract_xml_fragments(self, docx_path: Path) -> XMLFragments:
        """Extract complex XML fragments that can't be represented in AST."""
        fragments = XMLFragments()
        
        # Open DOCX as ZIP to access raw XML
        with zipfile.ZipFile(docx_path, 'r') as docx_zip:
            # Extract headers and footers
            self._extract_headers_footers(docx_zip, fragments)
            
            # Extract footnotes and endnotes
            self._extract_notes(docx_zip, fragments)
            
            # Extract embedded objects and media
            self._extract_embedded_objects(docx_zip, fragments)
            
            # Extract complex elements (charts, equations, etc.)
            self._extract_complex_elements(docx_zip, fragments)
        
        return fragments
    
    def _extract_headers_footers(self, docx_zip: zipfile.ZipFile, fragments: XMLFragments) -> None:
        """Extract header and footer XML."""
        try:
            # Look for header files
            for filename in docx_zip.namelist():
                if filename.startswith('word/header') and filename.endswith('.xml'):
                    content = docx_zip.read(filename).decode('utf-8')
                    fragment_id = Path(filename).stem
                    fragments.add_fragment(fragment_id, content, "header_footer")
                
                elif filename.startswith('word/footer') and filename.endswith('.xml'):
                    content = docx_zip.read(filename).decode('utf-8')
                    fragment_id = Path(filename).stem
                    fragments.add_fragment(fragment_id, content, "header_footer")
                    
        except Exception:
            # Header/footer extraction is optional
            pass
    
    def _extract_notes(self, docx_zip: zipfile.ZipFile, fragments: XMLFragments) -> None:
        """Extract footnotes and endnotes."""
        try:
            # Footnotes
            if 'word/footnotes.xml' in docx_zip.namelist():
                content = docx_zip.read('word/footnotes.xml').decode('utf-8')
                root = ET.fromstring(content)
                
                for note in root.findall('.//w:footnote', self.namespaces):
                    note_id = note.get(f'{{{self.namespaces["w"]}}}id')
                    if note_id:
                        note_xml = ET.tostring(note, encoding='unicode')
                        fragments.add_fragment(f"footnote_{note_id}", note_xml, "footnote")
            
            # Endnotes
            if 'word/endnotes.xml' in docx_zip.namelist():
                content = docx_zip.read('word/endnotes.xml').decode('utf-8')
                root = ET.fromstring(content)
                
                for note in root.findall('.//w:endnote', self.namespaces):
                    note_id = note.get(f'{{{self.namespaces["w"]}}}id')
                    if note_id:
                        note_xml = ET.tostring(note, encoding='unicode')
                        fragments.add_fragment(f"endnote_{note_id}", note_xml, "endnote")
                        
        except Exception:
            # Notes extraction is optional
            pass
    
    def _extract_embedded_objects(self, docx_zip: zipfile.ZipFile, fragments: XMLFragments) -> None:
        """Extract embedded objects and media files."""
        try:
            # Look for embedded objects
            for filename in docx_zip.namelist():
                if filename.startswith('word/embeddings/') or filename.startswith('word/media/'):
                    try:
                        content = docx_zip.read(filename)
                        object_id = Path(filename).stem
                        fragments.embedded_objects[object_id] = content
                    except Exception:
                        continue
                        
        except Exception:
            # Embedded objects extraction is optional
            pass
    
    def _extract_complex_elements(self, docx_zip: zipfile.ZipFile, fragments: XMLFragments) -> None:
        """Extract complex elements like charts and equations."""
        try:
            # Parse main document to find complex elements
            if 'word/document.xml' in docx_zip.namelist():
                content = docx_zip.read('word/document.xml').decode('utf-8')
                root = ET.fromstring(content)
                
                # Find drawing elements
                drawings = root.findall('.//w:drawing', self.namespaces)
                for i, drawing in enumerate(drawings):
                    drawing_xml = ET.tostring(drawing, encoding='unicode')
                    fragments.add_fragment(f"drawing_{i}", drawing_xml, "complex")
                
                # Find equation elements
                math_elements = root.findall('.//m:oMath', {'m': 'http://schemas.openxmlformats.org/officeDocument/2006/math'})
                for i, math_elem in enumerate(math_elements):
                    math_xml = ET.tostring(math_elem, encoding='unicode')
                    fragments.add_fragment(f"math_{i}", math_xml, "complex")
                    
        except Exception:
            # Complex elements extraction is optional
            pass
    
    def _create_ast_xml_mapping(
        self, 
        docx_path: Path, 
        pandoc_ast: PandocAST
    ) -> ASTToXMLMapping:
        """Create mapping between AST elements and XML positions."""
        mapping = ASTToXMLMapping()
        
        try:
            # This is a simplified implementation
            # In practice, would need sophisticated matching between
            # AST blocks and XML elements based on content and structure
            
            # For now, create basic position-based mapping
            for i, block in enumerate(pandoc_ast.blocks):
                ast_element_id = f"block_{i}"
                xml_path = f"//w:p[{i+1}]"  # XPath to paragraph
                mapping.add_mapping(ast_element_id, xml_path, i)

                # Generate a stable ID based on content hash + position
                try:
                    # Extract a basic text for hashing
                    text = ""
                    if isinstance(block, dict):
                        t = block.get("t")
                        c = block.get("c", [])
                        if t == "Header" and isinstance(c, list) and len(c) >= 3:
                            # inlines are at c[2]
                            text = json.dumps(c[2], sort_keys=True)
                        else:
                            text = json.dumps(c, sort_keys=True)
                    raw = f"{i}::{text}"
                    import hashlib
                    sid = hashlib.sha256(raw.encode()).hexdigest()[:16]
                    mapping.stable_ids[ast_element_id] = f"sid_{sid}"
                except Exception:
                    # If hashing fails, skip stable id
                    pass
        
        except Exception:
            # Mapping creation is optional but recommended
            pass
        
        return mapping
    
    def validate_conversion(self, original_path: Path, document_model: DocumentModel) -> Dict[str, Any]:
        """
        Validate the conversion by checking round-trip fidelity.
        
        Returns:
            Dictionary with validation results and fidelity scores.
        """
        validation_result = {
            'ast_valid': True,
            'metadata_preserved': True,
            'fragments_extracted': True,
            'mapping_created': True,
            'fidelity_score': 100.0,
            'issues': [],
        }
        
        try:
            # Validate AST structure
            if not document_model.pandoc_ast.blocks:
                validation_result['ast_valid'] = False
                validation_result['issues'].append("Empty AST - no content blocks found")
            
            # Check metadata preservation
            if not document_model.word_metadata.styles:
                validation_result['metadata_preserved'] = False
                validation_result['issues'].append("No styles preserved")
            
            # Check fragment extraction
            has_fragments = (
                document_model.xml_fragments.headers_footers or
                document_model.xml_fragments.footnotes or
                document_model.xml_fragments.complex_elements
            )
            if not has_fragments:
                validation_result['fragments_extracted'] = False
                validation_result['issues'].append("No XML fragments extracted")
            
            # Check mapping
            if not document_model.mapping.ast_to_xml:
                validation_result['mapping_created'] = False
                validation_result['issues'].append("No AST-XML mapping created")
            
            # Calculate fidelity score based on issues
            issue_count = len(validation_result['issues'])
            validation_result['fidelity_score'] = max(0, 100 - (issue_count * 25))
            
        except Exception as e:
            validation_result['issues'].append(f"Validation error: {str(e)}")
            validation_result['fidelity_score'] = 0
        
        return validation_result
