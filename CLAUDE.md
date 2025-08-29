# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Word CLI is a Claude-powered command-line tool for editing Word documents using AI assistance. It implements a hybrid AST + metadata approach for full-fidelity Word document manipulation with git-like version control.

## Development Setup

This is a Python project using Poetry for dependency management.

### Prerequisites
- Python 3.9+
- Poetry installed
- Pandoc installed and available in PATH

### Common Commands
```bash
# Install dependencies
poetry install

# Run the CLI in development
poetry run python -m word_cli.cli.app

# Install in development mode
poetry shell && pip install -e .

# Run tests
poetry run pytest

# Code quality checks
poetry run black src/
poetry run isort src/
poetry run mypy src/
poetry run flake8 src/
```

### CLI Usage
```bash
# Basic commands
word-cli open document.docx
word-cli status
word-cli save --message "Changes"
word-cli history
word-cli diff v1 v2

# AI-powered editing
word-cli chat document.docx  # Interactive session
word-cli edit document.docx "Replace all instances of 'foo' with 'bar'"
word-cli edit document.docx "Update paragraph 3 to include reference to section 2.1"

# Batch operations with preview
word-cli edit document.docx "Preview: edit paragraph 1 and insert new content after paragraph 2"
```

## Architecture

### Core Design: Hybrid AST + Metadata

The architecture uses a three-layer approach:

1. **Pandoc AST Layer** - Content structure (paragraphs, headings, lists)
2. **Metadata Layer** - Word-specific features (styles, comments, track changes)  
3. **XML Fragments** - Complex elements (charts, equations, embedded objects)

### Key Components

- **`DocumentModel`** (`src/word_cli/core/document_model.py`) - Central document representation with stable ID tracking
- **`ASTHandler`** (`src/word_cli/core/ast_handler.py`) - AST navigation and manipulation
- **Converters** (`src/word_cli/converters/`) - Bidirectional DOCX ↔ AST conversion
- **Version Control** (`src/word_cli/version/`) - Git-like document versioning
- **AI Agent** (`src/word_cli/agent/`) - Claude-powered natural language interface
- **Tool Registry** (`src/word_cli/agent/tools.py`) - 15+ specialized document editing tools
- **CLI Interface** (`src/word_cli/cli/app.py`) - Typer-based command interface

### Conversion Pipeline

1. **DOCX → DocumentModel**: Use Pandoc for AST + python-docx for metadata
2. **Edit Operations**: Manipulate AST with position tracking
3. **DocumentModel → DOCX**: Reconstruct with metadata restoration

### Version Control System

- Git-like commits, branches, and merges for documents
- Content-aware diffing with multiple output formats
- Atomic transactions with rollback support
- Change tracking at content, metadata, and style levels

### AI Agent Architecture

The AI agent provides natural language document editing through:

- **Iterative Tool Execution** - Multi-turn conversations with tool result feedback
- **Specialized Tools** - 15+ tools for search, edit, validate, and batch operations
- **Preview/Apply Workflow** - Safe editing with preview before applying changes
- **Context Management** - Smart document context for better AI decisions
- **Stable ID Tracking** - Content-based IDs for reliable element tracking across edits
- **Transaction Support** - Atomic operations with rollback capability

## Development Notes

### Current Status 
- ✅ Core architecture implemented
- ✅ Basic CLI interface with file operations  
- ✅ Full version control system
- ✅ Rich diff visualization
- ✅ LLM integration with Claude API
- ✅ Interactive editing with AI agent
- ✅ Batch editing with preview/apply workflow
- ✅ Tool-based architecture with 15+ specialized document tools

### Key Design Decisions

- **Hybrid approach** balances clean LLM interface (AST) with Word fidelity (metadata)
- **Version control** enables safe AI-assisted editing with rollback capability  
- **Position tracking** allows precise editing operations
- **Transaction system** supports batch operations

### File Structure
```
src/word_cli/
├── core/                 # Document model and AST handling
├── converters/           # DOCX ↔ AST conversion
├── version/              # Version control and diffing
├── cli/                  # Command-line interface
├── tools/                # Edit operations (planned)
├── validation/           # Document validation (planned)
└── utils/                # Utilities
```

### Dependencies
- **typer[all]** - CLI framework with rich output
- **python-docx** - Word document metadata handling
- **anthropic** - Claude API client for AI agent functionality
- **rich** - Terminal UI and formatting
- **pydantic** - Data validation and settings

Note: Pandoc is used via subprocess calls, not through pypandoc library.