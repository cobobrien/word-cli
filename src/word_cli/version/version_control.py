"""
Document version control system providing git-like functionality.

Implements versioning, branching, and change tracking for document models.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union
from dataclasses import dataclass, field
from enum import Enum
import pickle

from ..core.document_model import DocumentModel


class ChangeType(Enum):
    """Types of changes that can be made to a document."""
    CONTENT_INSERT = "content_insert"
    CONTENT_DELETE = "content_delete"
    CONTENT_MODIFY = "content_modify"
    STRUCTURE_CHANGE = "structure_change"
    STYLE_CHANGE = "style_change"
    METADATA_CHANGE = "metadata_change"


@dataclass
class DocumentChange:
    """Represents a single change to a document."""
    
    change_type: ChangeType
    target_path: str  # XPath or AST path to changed element
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    timestamp: datetime = field(default_factory=datetime.now)
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "change_type": self.change_type.value,
            "target_path": self.target_path,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "timestamp": self.timestamp.isoformat(),
            "description": self.description,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DocumentChange:
        """Create from dictionary."""
        return cls(
            change_type=ChangeType(data["change_type"]),
            target_path=data["target_path"],
            old_value=data.get("old_value"),
            new_value=data.get("new_value"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            description=data.get("description", ""),
        )


@dataclass
class DocumentVersion:
    """Represents a version of the document."""
    
    version_id: str
    parent_version: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    author: str = "word-cli"
    message: str = ""
    changes: List[DocumentChange] = field(default_factory=list)
    
    # Document state (stored as hash to save space)
    content_hash: str = ""
    
    # Branch information
    branch: str = "main"
    
    # Tags
    tags: Set[str] = field(default_factory=set)
    
    def __post_init__(self):
        """Generate version ID if not provided."""
        if not self.version_id:
            # Generate hash based on timestamp and content
            content = f"{self.timestamp.isoformat()}{self.message}{self.content_hash}"
            self.version_id = hashlib.sha256(content.encode()).hexdigest()[:12]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "version_id": self.version_id,
            "parent_version": self.parent_version,
            "timestamp": self.timestamp.isoformat(),
            "author": self.author,
            "message": self.message,
            "changes": [change.to_dict() for change in self.changes],
            "content_hash": self.content_hash,
            "branch": self.branch,
            "tags": list(self.tags),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DocumentVersion:
        """Create from dictionary."""
        return cls(
            version_id=data["version_id"],
            parent_version=data.get("parent_version"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            author=data.get("author", "word-cli"),
            message=data.get("message", ""),
            changes=[DocumentChange.from_dict(c) for c in data.get("changes", [])],
            content_hash=data.get("content_hash", ""),
            branch=data.get("branch", "main"),
            tags=set(data.get("tags", [])),
        )


@dataclass
class MergeResult:
    """Result of a merge operation."""
    
    success: bool
    merged_version: Optional[DocumentVersion] = None
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    message: str = ""


class VersionController:
    """
    Git-like version control system for documents.
    
    Provides branching, merging, and history management functionality.
    """
    
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path(".word_versions")
        self.storage_path.mkdir(exist_ok=True)
        
        # In-memory cache
        self._versions: Dict[str, DocumentVersion] = {}
        self._documents: Dict[str, DocumentModel] = {}
        self._current_branch = "main"
        self._head_version: Optional[str] = None
        
        # Load existing versions
        self._load_versions()
    
    def _load_versions(self) -> None:
        """Load versions from storage."""
        versions_file = self.storage_path / "versions.json"
        if versions_file.exists():
            try:
                with open(versions_file, 'r') as f:
                    data = json.load(f)
                    
                    for version_data in data.get("versions", []):
                        version = DocumentVersion.from_dict(version_data)
                        self._versions[version.version_id] = version
                    
                    self._current_branch = data.get("current_branch", "main")
                    self._head_version = data.get("head_version")
                    
            except (json.JSONDecodeError, KeyError) as e:
                # Start with empty state if loading fails
                self._versions = {}
    
    def _save_versions(self) -> None:
        """Save versions to storage."""
        versions_file = self.storage_path / "versions.json"
        
        data = {
            "versions": [v.to_dict() for v in self._versions.values()],
            "current_branch": self._current_branch,
            "head_version": self._head_version,
        }
        
        with open(versions_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _save_document_state(self, version_id: str, document: DocumentModel) -> str:
        """Save document state and return content hash."""
        # Create a serializable representation
        state_data = {
            "pandoc_ast": document.pandoc_ast.model_dump(),
            "word_metadata": document.word_metadata.to_dict(),
            "xml_fragments": {
                "headers_footers": document.xml_fragments.headers_footers,
                "footnotes": document.xml_fragments.footnotes,
                "endnotes": document.xml_fragments.endnotes,
                "complex_elements": document.xml_fragments.complex_elements,
            },
            "mapping": {
                "ast_to_xml": document.mapping.ast_to_xml,
                "xml_to_ast": document.mapping.xml_to_ast,
                "element_positions": document.mapping.element_positions,
            }
        }
        
        # Generate content hash
        content_str = json.dumps(state_data, sort_keys=True)
        content_hash = hashlib.sha256(content_str.encode()).hexdigest()
        
        # Save state to file
        state_file = self.storage_path / f"{content_hash}.pkl"
        if not state_file.exists():
            with open(state_file, 'wb') as f:
                pickle.dump(state_data, f)
        
        # Cache document in memory
        self._documents[version_id] = document
        
        return content_hash
    
    def _load_document_state(self, version_id: str) -> Optional[DocumentModel]:
        """Load document state for a version."""
        # Check memory cache first
        if version_id in self._documents:
            return self._documents[version_id]
        
        # Load from storage
        version = self._versions.get(version_id)
        if not version or not version.content_hash:
            return None
        
        state_file = self.storage_path / f"{version.content_hash}.pkl"
        if not state_file.exists():
            return None
        
        try:
            with open(state_file, 'rb') as f:
                state_data = pickle.load(f)
            
            # Reconstruct document model
            from ..core.document_model import PandocAST, WordMetadata, XMLFragments, ASTToXMLMapping
            
            document = DocumentModel(
                pandoc_ast=PandocAST.model_validate(state_data["pandoc_ast"]),
                word_metadata=WordMetadata.from_dict(state_data["word_metadata"]),
                xml_fragments=XMLFragments(**state_data["xml_fragments"]),
                mapping=ASTToXMLMapping(**state_data["mapping"]),
            )
            
            # Cache in memory
            self._documents[version_id] = document
            
            return document
            
        except (pickle.PickleError, KeyError, ValueError) as e:
            return None
    
    def commit(
        self, 
        document: DocumentModel, 
        message: str,
        author: str = "word-cli",
        changes: Optional[List[DocumentChange]] = None
    ) -> DocumentVersion:
        """
        Create a new version of the document.
        
        Args:
            document: Document to commit
            message: Commit message
            author: Author of the changes
            changes: List of changes made (optional)
            
        Returns:
            Created DocumentVersion
        """
        # Save document state and get content hash
        content_hash = self._save_document_state("temp", document)
        
        # Create version
        version = DocumentVersion(
            version_id="",  # Will be generated in __post_init__
            parent_version=self._head_version,
            timestamp=datetime.now(),
            author=author,
            message=message,
            changes=changes or [],
            content_hash=content_hash,
            branch=self._current_branch,
        )
        
        # Store version
        self._versions[version.version_id] = version
        self._documents[version.version_id] = document
        
        # Update head
        self._head_version = version.version_id
        
        # Save to disk
        self._save_versions()
        
        return version
    
    def checkout(self, version_id: str) -> Optional[DocumentModel]:
        """
        Checkout a specific version.
        
        Args:
            version_id: Version to checkout
            
        Returns:
            DocumentModel for the version, or None if not found
        """
        version = self._versions.get(version_id)
        if not version:
            return None
        
        document = self._load_document_state(version_id)
        if document:
            self._head_version = version_id
            self._current_branch = version.branch
            self._save_versions()
        
        return document
    
    def create_branch(self, branch_name: str, from_version: Optional[str] = None) -> bool:
        """
        Create a new branch.
        
        Args:
            branch_name: Name of the new branch
            from_version: Version to branch from (default: current head)
            
        Returns:
            True if successful, False otherwise
        """
        base_version = from_version or self._head_version
        if not base_version or base_version not in self._versions:
            return False
        
        # Switch to new branch
        self._current_branch = branch_name
        self._save_versions()
        
        return True
    
    def switch_branch(self, branch_name: str) -> Optional[DocumentModel]:
        """
        Switch to a different branch.
        
        Args:
            branch_name: Name of the branch to switch to
            
        Returns:
            DocumentModel at the head of the branch, or None if branch doesn't exist
        """
        # Find the latest version in the branch
        branch_versions = [
            v for v in self._versions.values() 
            if v.branch == branch_name
        ]
        
        if not branch_versions:
            return None
        
        # Get the latest version in the branch
        latest_version = max(branch_versions, key=lambda v: v.timestamp)
        
        self._current_branch = branch_name
        return self.checkout(latest_version.version_id)
    
    def merge(
        self, 
        source_branch: str, 
        target_branch: Optional[str] = None,
        strategy: str = "auto"
    ) -> MergeResult:
        """
        Merge one branch into another.
        
        Args:
            source_branch: Branch to merge from
            target_branch: Branch to merge into (default: current branch)
            strategy: Merge strategy ("auto", "ours", "theirs")
            
        Returns:
            MergeResult with success status and details
        """
        target_branch = target_branch or self._current_branch
        
        # Find head versions of both branches
        source_versions = [v for v in self._versions.values() if v.branch == source_branch]
        target_versions = [v for v in self._versions.values() if v.branch == target_branch]
        
        if not source_versions or not target_versions:
            return MergeResult(
                success=False,
                message=f"Branch not found: {source_branch if not source_versions else target_branch}"
            )
        
        source_head = max(source_versions, key=lambda v: v.timestamp)
        target_head = max(target_versions, key=lambda v: v.timestamp)
        
        # Load documents
        source_doc = self._load_document_state(source_head.version_id)
        target_doc = self._load_document_state(target_head.version_id)
        
        if not source_doc or not target_doc:
            return MergeResult(
                success=False,
                message="Could not load document states for merge"
            )
        
        # Detect conflicts (simplified implementation)
        conflicts = self._detect_merge_conflicts(source_doc, target_doc)
        
        if conflicts and strategy == "auto":
            return MergeResult(
                success=False,
                conflicts=conflicts,
                message=f"Merge conflicts detected. Use 'ours' or 'theirs' strategy to resolve."
            )
        
        # Perform merge based on strategy
        if strategy == "ours":
            merged_doc = target_doc.clone()
        elif strategy == "theirs":
            merged_doc = source_doc.clone()
        else:
            # Auto-merge (simplified - take target as base)
            merged_doc = target_doc.clone()
            # In a full implementation, would merge non-conflicting changes
        
        # Create merge commit
        merge_version = self.commit(
            merged_doc,
            f"Merge {source_branch} into {target_branch}",
            changes=[DocumentChange(
                change_type=ChangeType.STRUCTURE_CHANGE,
                target_path="/",
                description=f"Merged {source_branch} into {target_branch}"
            )]
        )
        
        return MergeResult(
            success=True,
            merged_version=merge_version,
            message=f"Successfully merged {source_branch} into {target_branch}"
        )
    
    def _detect_merge_conflicts(
        self, 
        source_doc: DocumentModel, 
        target_doc: DocumentModel
    ) -> List[Dict[str, Any]]:
        """Detect potential merge conflicts between two documents."""
        conflicts = []
        
        # Compare AST structures (simplified)
        if len(source_doc.pandoc_ast.blocks) != len(target_doc.pandoc_ast.blocks):
            conflicts.append({
                "type": "structure_conflict",
                "location": "document_blocks",
                "description": "Different number of blocks in documents",
                "source_value": len(source_doc.pandoc_ast.blocks),
                "target_value": len(target_doc.pandoc_ast.blocks),
            })
        
        # Compare metadata
        if source_doc.word_metadata.title != target_doc.word_metadata.title:
            conflicts.append({
                "type": "metadata_conflict",
                "location": "title",
                "description": "Document titles differ",
                "source_value": source_doc.word_metadata.title,
                "target_value": target_doc.word_metadata.title,
            })
        
        return conflicts
    
    def get_history(
        self, 
        branch: Optional[str] = None, 
        max_count: Optional[int] = None
    ) -> List[DocumentVersion]:
        """
        Get version history for a branch.
        
        Args:
            branch: Branch to get history for (default: current branch)
            max_count: Maximum number of versions to return
            
        Returns:
            List of DocumentVersions in reverse chronological order
        """
        branch = branch or self._current_branch
        
        branch_versions = [
            v for v in self._versions.values()
            if v.branch == branch
        ]
        
        # Sort by timestamp (newest first)
        branch_versions.sort(key=lambda v: v.timestamp, reverse=True)
        
        if max_count:
            branch_versions = branch_versions[:max_count]
        
        return branch_versions
    
    def get_diff(
        self, 
        version1_id: str, 
        version2_id: str
    ) -> Dict[str, Any]:
        """
        Get differences between two versions.
        
        Args:
            version1_id: First version ID
            version2_id: Second version ID
            
        Returns:
            Dictionary describing the differences
        """
        doc1 = self._load_document_state(version1_id)
        doc2 = self._load_document_state(version2_id)
        
        if not doc1 or not doc2:
            return {"error": "Could not load one or both document versions"}
        
        diff = {
            "version1": version1_id,
            "version2": version2_id,
            "changes": [],
        }
        
        # Compare AST content (simplified)
        if doc1.pandoc_ast.blocks != doc2.pandoc_ast.blocks:
            diff["changes"].append({
                "type": "content_change",
                "location": "blocks",
                "description": "Document content has changed",
            })
        
        # Compare metadata
        if doc1.word_metadata.to_dict() != doc2.word_metadata.to_dict():
            diff["changes"].append({
                "type": "metadata_change",
                "location": "metadata",
                "description": "Document metadata has changed",
            })
        
        return diff
    
    def rollback(self, version_id: str) -> Optional[DocumentModel]:
        """
        Rollback to a previous version.
        
        Args:
            version_id: Version to rollback to
            
        Returns:
            DocumentModel for the rollback version, or None if failed
        """
        return self.checkout(version_id)
    
    def tag_version(self, version_id: str, tag: str) -> bool:
        """
        Add a tag to a version.
        
        Args:
            version_id: Version to tag
            tag: Tag name
            
        Returns:
            True if successful, False otherwise
        """
        version = self._versions.get(version_id)
        if not version:
            return False
        
        version.tags.add(tag)
        self._save_versions()
        return True
    
    def get_branches(self) -> List[str]:
        """Get list of all branches."""
        branches = set()
        for version in self._versions.values():
            branches.add(version.branch)
        return sorted(list(branches))
    
    def get_current_branch(self) -> str:
        """Get current branch name."""
        return self._current_branch
    
    def get_head_version(self) -> Optional[str]:
        """Get current head version ID."""
        return self._head_version
    
    def cleanup_old_versions(self, keep_days: int = 30) -> int:
        """
        Clean up old versions to save space.
        
        Args:
            keep_days: Number of days of history to keep
            
        Returns:
            Number of versions cleaned up
        """
        cutoff_date = datetime.now().timestamp() - (keep_days * 24 * 60 * 60)
        
        to_remove = []
        for version in self._versions.values():
            if version.timestamp.timestamp() < cutoff_date and len(version.tags) == 0:
                to_remove.append(version.version_id)
        
        # Remove versions and associated documents
        removed_count = 0
        for version_id in to_remove:
            if version_id in self._versions:
                version = self._versions[version_id]
                
                # Remove document file if it exists
                state_file = self.storage_path / f"{version.content_hash}.pkl"
                if state_file.exists():
                    state_file.unlink()
                
                # Remove from caches
                self._versions.pop(version_id)
                self._documents.pop(version_id, None)
                
                removed_count += 1
        
        if removed_count > 0:
            self._save_versions()
        
        return removed_count