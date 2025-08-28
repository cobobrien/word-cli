# Word CLI

A Claude-powered command-line tool for editing Word documents using AI assistance.

## Overview

Word CLI provides a hybrid approach to Word document editing that combines the power of Pandoc's AST (Abstract Syntax Tree) for content manipulation with preservation of Word-specific metadata and formatting. This allows for precise, programmatic editing while maintaining full document fidelity.

## Architecture

### Hybrid AST + Metadata Approach

The core innovation is a three-layer document representation:

1. **Pandoc AST Layer** - Clean, semantic representation for content operations
2. **Metadata Preservation Layer** - Stores Word-specific features (styles, comments, track changes)  
3. **XML Fragment Layer** - Preserves complex elements that can't be represented in AST

### Key Components

- **Document Model** (`DocumentModel`) - Central hybrid representation
- **AST Handler** (`ASTHandler`) - Navigation and manipulation of document structure
- **Converters** - Bidirectional DOCX ↔ AST conversion with metadata preservation
- **Version Control** (`VersionController`) - Git-like versioning for documents
- **Diff Engine** (`DiffEngine`) - Detailed change detection and visualization

## Features

### Current (Phase 1)

- ✅ Open and save Word documents with full fidelity
- ✅ Hybrid AST + metadata document representation
- ✅ Git-like version control (commit, checkout, branch, merge)
- ✅ Rich diff visualization (text, HTML, JSON formats)
- ✅ Document statistics and status reporting
- ✅ CLI interface with Typer

### Current (Phase 2) - AI Agent Integration

- ✅ **Natural language editing** - "Edit paragraph 3 to say...", "Find and replace all instances..."
- ✅ **Interactive chat mode** - Claude Code-like experience for document editing  
- ✅ **Smart tool execution** - AI agent uses 15+ specialized tools for precise operations
- ✅ **Cross-document operations** - "Copy the payment terms from contract.docx"
- ✅ **Transaction-based editing** - Atomic operations with rollback support
- ✅ **Advanced validation pipeline** - Multi-stage validation with auto-fix capabilities
- ✅ **Context-aware conversations** - Agent understands document structure and history

### Future (Phase 3)

- 🔄 Advanced diff algorithms and semantic merging
- 🔄 Multi-document batch operations  
- 🔄 Template system and document generation
- 🔄 Plugin architecture for custom tools

## Installation

### Prerequisites

- Python 3.9 or higher
- [Pandoc](https://pandoc.org/installing.html) installed and available in PATH
- Poetry for dependency management
- [Anthropic API key](https://console.anthropic.com/) for Claude integration

### Setup

```bash
# Clone the repository
git clone <repository-url>
cd word-cli

# Install dependencies with Poetry
poetry install

# Install in development mode
poetry shell
pip install -e .

# Set your Anthropic API key
export ANTHROPIC_API_KEY="your-api-key-here"

# Create default configuration
word-cli config --create-default

# Test the installation
word-cli info
```

## Usage

### Basic Commands

```bash
# Open a Word document
word-cli open document.docx

# Start interactive AI editing (recommended)
word-cli chat document.docx

# Or start interactive mode with already opened document
word-cli interactive

# Show document status
word-cli status

# Show version history  
word-cli history

# Save changes
word-cli save --message "Updated introduction"

# Compare versions
word-cli diff v1 v2

# Manage configuration
word-cli config --show
word-cli config --set-model claude-3-opus-20240229
```

### Interactive AI Editing Examples

Once in chat mode, you can use natural language:

```
word-cli> Edit paragraph 3 to be more formal and professional

word-cli> Find all instances of "contract" and replace with "agreement"

word-cli> Add a new section about payment terms after the introduction

word-cli> Copy the liability clause from template.docx and insert it here

word-cli> Make the headings consistent - use sentence case throughout

word-cli> Summarize the document and show me its structure
```

### Version Control

```bash
# Show current status
word-cli status

# View history
word-cli history --count 10

# Create and switch branches
word-cli branch feature-editing
word-cli checkout feature-editing

# Compare versions
word-cli diff main feature-editing --format html --output diff.html
```

## Project Structure

```
word-cli/
├── src/word_cli/
│   ├── core/                 # Core document model and AST handling
│   │   ├── document_model.py # Hybrid document representation
│   │   └── ast_handler.py    # AST navigation and manipulation
│   ├── converters/           # Format conversion
│   │   ├── docx_to_ast.py   # DOCX → AST with metadata preservation
│   │   ├── ast_to_docx.py   # AST → DOCX with metadata restoration
│   │   └── xml_bridge.py    # Complex XML element handling
│   ├── version/              # Version control system
│   │   ├── version_control.py # Git-like versioning
│   │   └── diff_engine.py    # Change detection and visualization
│   ├── cli/                  # Command-line interface
│   │   └── app.py           # Main Typer application
│   ├── tools/               # Document editing operations (planned)
│   ├── validation/          # Document validation (planned)
│   └── utils/               # Utilities and helpers
├── pyproject.toml           # Project configuration
└── README.md
```

## Technical Details

### Document Representation

The `DocumentModel` class combines:
- `PandocAST` for content structure
- `WordMetadata` for document properties and styles  
- `XMLFragments` for complex elements (charts, equations)
- `ASTToXMLMapping` for round-trip fidelity

### Conversion Pipeline

1. **DOCX → AST**: Extract content structure via Pandoc, preserve metadata via python-docx
2. **Edit Operations**: Manipulate AST while tracking changes
3. **AST → DOCX**: Reconstruct Word format with metadata restoration

### Version Control

- Git-like model with commits, branches, and merges
- Diff-based change tracking
- Content-aware conflict detection
- Atomic transactions with rollback support

## Development

### Running Tests

```bash
poetry run pytest
```

### Code Quality

```bash
# Format code
poetry run black src/

# Sort imports  
poetry run isort src/

# Type checking
poetry run mypy src/

# Linting
poetry run flake8 src/
```

## Current Status

**Phase 2 Complete:** Full AI agent integration with Claude-powered natural language editing.

The system now provides:

- **Complete AI Agent Architecture** - Claude-powered document editing with natural language understanding
- **15+ Specialized Tools** - Navigation, reading, editing, validation, and cross-document operations
- **Interactive Chat Interface** - Claude Code-like experience for document editing
- **Smart Context Management** - Agent understands document structure and conversation history  
- **Transaction System** - Atomic operations with validation and rollback
- **Advanced Validation** - Multi-stage validation with auto-fix capabilities
- **Robust Version Control** - Git-like document versioning with rich diffs

## Future Phases

### Phase 2: LLM Integration
- Claude API integration for natural language commands
- Tool system for precise document operations  
- Interactive editing mode with real-time feedback

### Phase 3: Advanced Features
- Multi-document operations
- Template system
- Plugin architecture
- Web interface

## Contributing

This is currently a greenfield development project. The architecture is designed to be extensible and the codebase follows Python best practices with comprehensive type hints and documentation.

## Architecture Decisions

### Why Hybrid AST + Metadata?

1. **Clean Editing Interface** - Pandoc AST provides semantic structure that's easy for LLMs to understand and manipulate
2. **Full Fidelity** - Separate metadata layer preserves Word-specific features that would be lost in pure AST conversion
3. **Round-trip Integrity** - XML fragment preservation ensures complex elements survive the conversion process

### Why Version Control?

- Enables safe experimentation with document changes
- Provides familiar git-like workflow for developers
- Supports branching for different document versions
- Essential foundation for AI-assisted editing where changes may need to be rolled back

## License

[License to be determined]
