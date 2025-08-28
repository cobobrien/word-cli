"""
Example usage of Word CLI agent system.

This demonstrates how to use the Word CLI agent programmatically
for document editing tasks.
"""

import asyncio
from pathlib import Path

from src.word_cli.core.document_model import DocumentModel
from src.word_cli.converters.docx_to_ast import DocxToASTConverter
from src.word_cli.agent.agent_core import WordAgent, AgentConfig
from src.word_cli.version.version_control import VersionController


async def example_document_editing():
    """Example of programmatic document editing with the AI agent."""
    
    # Create a simple example document (in practice, you'd load a real .docx file)
    print("Setting up example document...")
    
    # For this example, we'll create a mock document
    # In real usage, you would load from a .docx file:
    # converter = DocxToASTConverter()
    # document = converter.convert(Path("example.docx"))
    
    from src.word_cli.core.ast_handler import ASTHandler
    from src.word_cli.core.document_model import PandocAST, WordMetadata, XMLFragments, ASTToXMLMapping
    
    # Create a simple document with a few paragraphs
    document = DocumentModel(
        pandoc_ast=PandocAST(
            blocks=[
                {
                    "t": "Header",
                    "c": [1, ["", [], []], [{"t": "Str", "c": "Introduction"}]]
                },
                {
                    "t": "Para", 
                    "c": [
                        {"t": "Str", "c": "This"},
                        {"t": "Space"},
                        {"t": "Str", "c": "is"},
                        {"t": "Space"},
                        {"t": "Str", "c": "a"},
                        {"t": "Space"},
                        {"t": "Str", "c": "sample"},
                        {"t": "Space"},
                        {"t": "Str", "c": "document"},
                        {"t": "Space"},
                        {"t": "Str", "c": "for"},
                        {"t": "Space"},
                        {"t": "Str", "c": "testing."}
                    ]
                },
                {
                    "t": "Para",
                    "c": [
                        {"t": "Str", "c": "It"},
                        {"t": "Space"},
                        {"t": "Str", "c": "has"},
                        {"t": "Space"},
                        {"t": "Str", "c": "multiple"},
                        {"t": "Space"},
                        {"t": "Str", "c": "paragraphs"},
                        {"t": "Space"},
                        {"t": "Str", "c": "to"},
                        {"t": "Space"},
                        {"t": "Str", "c": "demonstrate"},
                        {"t": "Space"},
                        {"t": "Str", "c": "editing."}
                    ]
                }
            ]
        ),
        word_metadata=WordMetadata(
            title="Example Document",
            author="Word CLI"
        )
    )
    
    # Set up version control
    version_controller = VersionController()
    initial_version = version_controller.commit(
        document,
        "Initial document creation",
        author="example-script"
    )
    
    print(f"✓ Created document with version {initial_version.version_id}")
    
    # Set up the AI agent
    agent_config = AgentConfig(
        model="claude-3-sonnet-20240229",
        temperature=0.3,
        auto_save=False  # We'll handle saving manually for this example
    )
    
    agent = WordAgent(agent_config)
    agent.set_document(document, version_controller)
    
    print("✓ Initialized AI agent")
    
    # Example 1: Get document summary
    print("\n=== Example 1: Document Analysis ===")
    async for chunk in agent.process_message("Summarize this document and tell me its structure"):
        print(chunk, end='')
    
    # Example 2: Edit content
    print("\n\n=== Example 2: Content Editing ===")
    async for chunk in agent.process_message("Edit paragraph 2 to say 'This is an improved sample document for comprehensive testing of Word CLI features.'"):
        print(chunk, end='')
    
    # Example 3: Add new content
    print("\n\n=== Example 3: Adding Content ===")  
    async for chunk in agent.process_message("Add a new paragraph after paragraph 2 that says 'The Word CLI system provides powerful document editing capabilities.'"):
        print(chunk, end='')
    
    # Example 4: Find and analyze
    print("\n\n=== Example 4: Search and Analysis ===")
    async for chunk in agent.process_message("Find all instances of the word 'document' in the text"):
        print(chunk, end='')
    
    # Show final document state
    print("\n\n=== Final Document State ===")
    final_content = document.get_text_content()
    print("Document content:")
    print(final_content)
    
    # Show version history
    print("\n=== Version History ===")
    history = version_controller.get_history(max_count=5)
    for version in history:
        print(f"• {version.version_id}: {version.message} ({version.timestamp.strftime('%H:%M:%S')})")
    
    print("\n✓ Example complete!")


async def example_cross_document_operation():
    """Example of cross-document operations."""
    
    print("\n=== Cross-Document Example ===")
    print("This would demonstrate copying content from one document to another.")
    print("In a real implementation, you could do:")
    print("  'Copy the payment terms from contract_template.docx'")
    print("  'Reference clause 3.2 from the main agreement'")
    

def example_tool_usage():
    """Example of using tools directly."""
    
    print("\n=== Direct Tool Usage Example ===")
    
    from src.word_cli.agent.tools import FindTextTool, EditParagraphTool, ToolRegistry
    
    # Get tool registry
    registry = ToolRegistry()
    
    print("Available tools:")
    for tool_name in registry.list_tools():
        tool = registry.get_tool(tool_name)
        print(f"• {tool_name}: {tool.description} ({tool.category.value})")
    
    print(f"\nTotal: {len(registry.list_tools())} tools available")


if __name__ == "__main__":
    print("Word CLI Agent Example")
    print("====================")
    
    # Show available tools
    example_tool_usage()
    
    # Run async examples
    try:
        asyncio.run(example_document_editing())
        asyncio.run(example_cross_document_operation())
    except Exception as e:
        print(f"\nNote: Full example requires ANTHROPIC_API_KEY environment variable")
        print(f"Error: {e}")
        
    print("\nTo run the full interactive experience:")
    print("1. Set your ANTHROPIC_API_KEY environment variable")
    print("2. Run: word-cli chat")
    print("3. Try natural language commands like:")
    print("   • 'Edit paragraph 2 to be more formal'")
    print("   • 'Add a conclusion section'")
    print("   • 'Find and replace all instances of X with Y'")