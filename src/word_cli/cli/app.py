"""
Main CLI application for Word CLI.

Provides a Typer-based command-line interface for editing Word documents
with Claude integration.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, List
import json

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

from ..core.document_model import DocumentModel
from ..converters.docx_to_ast import DocxToASTConverter
from ..converters.ast_to_docx import ASTToDocxConverter
from ..version.version_control import VersionController
from ..version.diff_engine import DiffEngine

# Initialize Typer app
app = typer.Typer(
    name="word-cli",
    help="Claude-powered CLI for editing Word documents",
    add_completion=False,
    rich_markup_mode="rich"
)

# Global console for rich output
console = Console()

# Global state
current_document: Optional[DocumentModel] = None
version_controller: Optional[VersionController] = None
document_path: Optional[Path] = None


def get_version_controller() -> VersionController:
    """Get or create version controller instance."""
    global version_controller
    if version_controller is None:
        version_controller = VersionController()
    return version_controller


@app.command()
def open(
    file_path: Path = typer.Argument(..., help="Path to the Word document to open"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
) -> None:
    """
    Open a Word document for editing.
    
    This loads the document into the Word CLI environment, converting it to our
    hybrid AST + metadata representation for editing.
    """
    global current_document, document_path
    
    if not file_path.exists():
        console.print(f"[red]Error: File not found: {file_path}[/red]")
        raise typer.Exit(1)
    
    if not file_path.suffix.lower() == '.docx':
        console.print("[red]Error: Only .docx files are supported[/red]")
        raise typer.Exit(1)
    
    console.print(f"[blue]Opening document: {file_path}[/blue]")
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Loading document...", total=None)
            
            # Convert DOCX to DocumentModel
            converter = DocxToASTConverter()
            current_document = converter.convert(file_path)
            document_path = file_path
            
            progress.update(task, description="Validating conversion...")
            
            # Validate conversion
            validation = converter.validate_conversion(file_path, current_document)
            
            progress.update(task, description="Creating initial version...")
            
            # Create initial version
            vc = get_version_controller()
            initial_version = vc.commit(
                current_document,
                f"Initial import of {file_path.name}",
                changes=[]
            )
        
        # Show document info
        stats = current_document.get_stats()
        
        info_table = Table(title="Document Information", show_header=False)
        info_table.add_column("Property", style="cyan")
        info_table.add_column("Value", style="green")
        
        info_table.add_row("File", str(file_path))
        info_table.add_row("Word Count", str(stats['word_count']))
        info_table.add_row("Paragraphs", str(stats['paragraph_count']))
        info_table.add_row("Headings", str(stats['heading_count']))
        info_table.add_row("Version", initial_version.version_id)
        info_table.add_row("Fidelity Score", f"{validation['fidelity_score']:.1f}%")
        
        console.print(info_table)
        
        if validation['issues'] and verbose:
            console.print("\n[yellow]Conversion Issues:[/yellow]")
            for issue in validation['issues']:
                console.print(f"  • {issue}")
        
        console.print(f"\n[green]Document opened successfully![/green]")
        console.print("Use [cyan]word-cli interactive[/cyan] to start editing.")
        
    except Exception as e:
        console.print(f"[red]Error opening document: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def save(
    output_path: Optional[Path] = typer.Option(None, "--output", "-o", help="Output path (default: overwrite original)"),
    commit_message: str = typer.Option("Save changes", "--message", "-m", help="Commit message"),
) -> None:
    """
    Save the current document to a Word file.
    
    This converts the current document state back to DOCX format and optionally
    creates a new version in the version history.
    """
    global current_document, document_path
    
    if current_document is None:
        console.print("[red]Error: No document is currently open[/red]")
        console.print("Use [cyan]word-cli open <file>[/cyan] to open a document first.")
        raise typer.Exit(1)
    
    # Determine output path
    if output_path is None:
        if document_path is None:
            console.print("[red]Error: No original file path available. Use --output to specify destination[/red]")
            raise typer.Exit(1)
        output_path = document_path
    
    console.print(f"[blue]Saving document to: {output_path}[/blue]")
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Converting to DOCX...", total=None)
            
            # Convert back to DOCX
            converter = ASTToDocxConverter()
            converter.convert(current_document, output_path)
            
            progress.update(task, description="Validating output...")
            
            # Validate output
            validation = converter.validate_output(output_path, current_document)
            
            progress.update(task, description="Creating version...")
            
            # Create new version if document was modified
            if current_document.is_modified:
                vc = get_version_controller()
                version = vc.commit(
                    current_document,
                    commit_message
                )
                console.print(f"[green]Saved and committed as version {version.version_id}[/green]")
            else:
                console.print("[yellow]No changes detected, file saved without creating new version[/yellow]")
        
        # Show save info
        if validation['file_created']:
            file_size = validation['size_bytes'] / 1024  # KB
            console.print(f"[green]Document saved successfully! ({file_size:.1f} KB)[/green]")
        
        if validation['issues']:
            console.print("\n[yellow]Save Issues:[/yellow]")
            for issue in validation['issues']:
                console.print(f"  • {issue}")
        
    except Exception as e:
        console.print(f"[red]Error saving document: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def status() -> None:
    """
    Show the current document status and version information.
    """
    global current_document
    
    if current_document is None:
        console.print("[yellow]No document is currently open[/yellow]")
        console.print("Use [cyan]word-cli open <file>[/cyan] to open a document first.")
        return
    
    # Document stats
    stats = current_document.get_stats()
    
    status_panel = Panel.fit(
        f"""[bold cyan]Current Document Status[/bold cyan]

[bold]Document ID:[/bold] {stats['document_id']}
[bold]Word Count:[/bold] {stats['word_count']}
[bold]Character Count:[/bold] {stats['character_count']}
[bold]Paragraphs:[/bold] {stats['paragraph_count']}
[bold]Headings:[/bold] {stats['heading_count']}
[bold]Modified:[/bold] {'Yes' if stats['is_modified'] else 'No'}
[bold]Last Modified:[/bold] {stats['last_modified']}""",
        title="Document Status",
        border_style="blue"
    )
    
    console.print(status_panel)
    
    # Version info
    vc = get_version_controller()
    current_branch = vc.get_current_branch()
    head_version = vc.get_head_version()
    
    if head_version:
        history = vc.get_history(max_count=5)
        
        version_table = Table(title="Recent Versions", show_header=True)
        version_table.add_column("Version", style="cyan")
        version_table.add_column("Branch", style="green")
        version_table.add_column("Message", style="white")
        version_table.add_column("Author", style="yellow")
        version_table.add_column("Date", style="blue")
        
        for version in history:
            is_head = "→ " if version.version_id == head_version else "  "
            version_table.add_row(
                f"{is_head}{version.version_id}",
                version.branch,
                version.message[:50] + ("..." if len(version.message) > 50 else ""),
                version.author,
                version.timestamp.strftime("%Y-%m-%d %H:%M")
            )
        
        console.print("\n")
        console.print(version_table)
    
    # Branch info
    branches = vc.get_branches()
    if len(branches) > 1:
        branch_info = f"[bold]Branches:[/bold] {', '.join(branches)} (current: {current_branch})"
        console.print(f"\n{branch_info}")


@app.command()
def history(
    max_count: int = typer.Option(10, "--count", "-n", help="Maximum number of versions to show"),
    branch: Optional[str] = typer.Option(None, "--branch", "-b", help="Branch to show history for"),
) -> None:
    """
    Show document version history.
    """
    vc = get_version_controller()
    versions = vc.get_history(branch=branch, max_count=max_count)
    
    if not versions:
        console.print("[yellow]No version history available[/yellow]")
        return
    
    history_table = Table(title=f"Document History ({branch or vc.get_current_branch()})")
    history_table.add_column("Version", style="cyan")
    history_table.add_column("Message", style="white")
    history_table.add_column("Author", style="yellow")
    history_table.add_column("Date", style="blue")
    history_table.add_column("Changes", style="green")
    
    head_version = vc.get_head_version()
    
    for version in versions:
        marker = "→ " if version.version_id == head_version else "  "
        change_count = len(version.changes)
        
        history_table.add_row(
            f"{marker}{version.version_id}",
            version.message,
            version.author,
            version.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            str(change_count) if change_count else "-"
        )
    
    console.print(history_table)


@app.command()
def diff(
    version1: str = typer.Argument(..., help="First version ID"),
    version2: str = typer.Argument(..., help="Second version ID"),
    output_format: str = typer.Option("text", "--format", "-f", help="Output format: text, html, json"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Save diff to file"),
) -> None:
    """
    Show differences between two document versions.
    """
    vc = get_version_controller()
    
    # Load documents
    doc1 = vc.checkout(version1)
    if not doc1:
        console.print(f"[red]Error: Version {version1} not found[/red]")
        raise typer.Exit(1)
    
    doc2 = vc.checkout(version2)
    if not doc2:
        console.print(f"[red]Error: Version {version2} not found[/red]")
        raise typer.Exit(1)
    
    # Generate diff
    diff_engine = DiffEngine()
    document_diff = diff_engine.diff_documents(doc1, doc2, version1, version2)
    
    # Format output
    if output_format == "text":
        diff_text = diff_engine.generate_text_diff(doc1, doc2)
        
        if output_file:
            output_file.write_text(diff_text)
            console.print(f"[green]Diff saved to {output_file}[/green]")
        else:
            if diff_text.strip():
                console.print(Panel(
                    Syntax(diff_text, "diff", theme="monokai"),
                    title=f"Diff: {version1} → {version2}",
                    border_style="blue"
                ))
            else:
                console.print("[yellow]No differences found[/yellow]")
    
    elif output_format == "html":
        html_diff = diff_engine.generate_html_diff(doc1, doc2)
        
        if output_file:
            output_file.write_text(html_diff)
            console.print(f"[green]HTML diff saved to {output_file}[/green]")
        else:
            console.print("[yellow]HTML output requires --output flag[/yellow]")
    
    elif output_format == "json":
        json_diff = json.dumps(document_diff.to_dict(), indent=2)
        
        if output_file:
            output_file.write_text(json_diff)
            console.print(f"[green]JSON diff saved to {output_file}[/green]")
        else:
            console.print(json_diff)
    
    # Show summary
    summary = diff_engine.summarize_changes(document_diff)
    
    summary_panel = Panel.fit(
        f"""[bold]{summary['overview']}[/bold]

[bold cyan]Content Changes:[/bold cyan]
{chr(10).join(f"• {change}" for change in summary['content_changes']) or "None"}

[bold yellow]Metadata Changes:[/bold yellow]
{chr(10).join(f"• {change}" for change in summary['metadata_changes']) or "None"}

[bold green]Style Changes:[/bold green]
{chr(10).join(f"• {change}" for change in summary['style_changes']) or "None"}""",
        title="Change Summary",
        border_style="green"
    )
    
    console.print("\n")
    console.print(summary_panel)


@app.command()
def checkout(
    version_id: str = typer.Argument(..., help="Version ID to checkout"),
) -> None:
    """
    Checkout a specific document version.
    """
    global current_document
    
    vc = get_version_controller()
    document = vc.checkout(version_id)
    
    if not document:
        console.print(f"[red]Error: Version {version_id} not found[/red]")
        raise typer.Exit(1)
    
    current_document = document
    console.print(f"[green]Checked out version {version_id}[/green]")
    
    # Show document stats
    stats = current_document.get_stats()
    console.print(f"Word count: {stats['word_count']}, Paragraphs: {stats['paragraph_count']}")


@app.command()
def interactive() -> None:
    """
    Start interactive editing mode with Claude AI integration.
    """
    global current_document, version_controller, document_path
    
    if current_document is None:
        console.print("[red]Error: No document is currently open[/red]")
        console.print("Use [cyan]word-cli open <file>[/cyan] to open a document first.")
        raise typer.Exit(1)
    
    console.print("[blue]Starting interactive mode with Claude AI...[/blue]")
    
    # Import and run the interactive session
    import asyncio
    from ..agent.session import InteractiveSession, SessionConfig
    from ..agent.agent_core import AgentConfig
    
    async def run_interactive():
        # Configure the session
        session_config = SessionConfig(
            auto_save=True,
            show_thinking=True,
            stream_output=True
        )
        
        agent_config = AgentConfig(
            model="claude-3-sonnet-20240229",
            temperature=0.3,
            auto_save=True
        )
        
        # Create and start session
        session = InteractiveSession(session_config, agent_config)
        
        # Set the current document in the session
        session.state.current_document = current_document
        session.state.document_path = document_path
        session.state.version_controller = get_version_controller()
        
        # Set document in agent
        session.agent.set_document(current_document, get_version_controller())
        
        # Start the interaction loop
        await session._interaction_loop()
    
    try:
        asyncio.run(run_interactive())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interactive session ended[/yellow]")
    except Exception as e:
        console.print(f"[red]Error in interactive mode: {e}[/red]")
        # Show more helpful error message
        if "anthropic" in str(e).lower():
            console.print("[yellow]Make sure you have set your ANTHROPIC_API_KEY environment variable[/yellow]")


@app.command() 
def chat(
    document_file: Optional[Path] = typer.Argument(None, help="Word document to open for editing"),
    model: str = typer.Option("claude-3-sonnet-20240229", "--model", "-m", help="Claude model to use"),
    temperature: float = typer.Option(0.3, "--temperature", "-t", help="Model temperature (0.0-1.0)"),
    auto_save: bool = typer.Option(True, "--auto-save/--no-auto-save", help="Auto-save changes"),
) -> None:
    """
    Start a new interactive chat session with Claude for document editing.
    
    This creates a fresh session without relying on global document state.
    """
    import asyncio
    from ..agent.session import InteractiveSession, SessionConfig
    from ..agent.agent_core import AgentConfig
    
    async def run_chat_session():
        # Configure the session
        session_config = SessionConfig(
            auto_save=auto_save,
            show_thinking=True,
            stream_output=True
        )
        
        agent_config = AgentConfig(
            model=model,
            temperature=temperature,
            auto_save=auto_save
        )
        
        # Create and start session
        session = InteractiveSession(session_config, agent_config)
        await session.start_session(document_file)
    
    try:
        console.print(f"[blue]Starting chat session with {model}...[/blue]")
        asyncio.run(run_chat_session())
    except KeyboardInterrupt:
        console.print("\n[yellow]Chat session ended[/yellow]")
    except Exception as e:
        console.print(f"[red]Error starting chat session: {e}[/red]")
        if "anthropic" in str(e).lower():
            console.print("[yellow]Make sure you have set your ANTHROPIC_API_KEY environment variable[/yellow]")


@app.command()
def info() -> None:
    """
    Show information about Word CLI.
    """
    from ..config import get_config_manager
    
    # Get configuration info
    config_manager = get_config_manager()
    config_info = config_manager.get_config_info()
    
    info_text = f"""[bold cyan]Word CLI - Claude-powered Document Editing[/bold cyan]

A command-line tool for editing Word documents using AI assistance.

[bold]Current Configuration:[/bold]
• Model: {config_info['agent_model']}
• Validation Level: {config_info['validation_level']}
• API Key: {'✓ Set' if config_info['anthropic_api_key_set'] else '✗ Not Set'}
• Config File: {'✓ Exists' if config_info['config_exists'] else '✗ Not Found'}

[bold]Features:[/bold]
• Hybrid AST + metadata approach for full fidelity
• Git-like version control for document history  
• Natural language editing with Claude AI
• Batch operations and transaction support
• Rich diff visualization and validation

[bold]Commands:[/bold]
• [cyan]word-cli open <file>[/cyan] - Open a Word document
• [cyan]word-cli chat [file][/cyan] - Start interactive AI editing
• [cyan]word-cli save[/cyan] - Save current document
• [cyan]word-cli diff <v1> <v2>[/cyan] - Compare versions

[bold]Architecture:[/bold]
• Uses Pandoc for content structure extraction
• Preserves Word-specific metadata and formatting
• Provides precise position tracking for edits
• Supports branching and merging of document versions

[bold]Technology Stack:[/bold]
• Python with Typer CLI framework
• Claude AI for natural language understanding
• Pandoc for format conversion
• python-docx for metadata handling
• Rich for terminal UI
    """
    
    panel = Panel(info_text, border_style="blue")
    console.print(panel)
    
    # Show enabled features
    if config_info['features_enabled']:
        features_text = "**Enabled Features:** " + ", ".join(config_info['features_enabled'])
        console.print(f"\n[dim]{features_text}[/dim]")


@app.command()
def config(
    show: bool = typer.Option(False, "--show", help="Show current configuration"),
    create_default: bool = typer.Option(False, "--create-default", help="Create default config file"),
    set_model: Optional[str] = typer.Option(None, "--set-model", help="Set the Claude model to use"),
    set_temperature: Optional[float] = typer.Option(None, "--set-temperature", help="Set model temperature"),
) -> None:
    """
    Manage Word CLI configuration.
    """
    from ..config import get_config_manager, load_config
    
    config_manager = get_config_manager()
    
    if create_default:
        config_manager.create_default_config()
        return
    
    if show:
        config_info = config_manager.get_config_info()
        current_config = load_config()
        
        config_display = f"""[bold]Word CLI Configuration[/bold]

[bold cyan]Agent Settings:[/bold cyan]
• Model: {current_config.agent.model}
• Temperature: {current_config.agent.temperature}
• Max Tokens: {current_config.agent.max_tokens}
• Auto Save: {current_config.agent.auto_save}

[bold yellow]Session Settings:[/bold yellow]  
• Auto Save: {current_config.session.auto_save}
• Show Thinking: {current_config.session.show_thinking}
• Stream Output: {current_config.session.stream_output}
• Max History: {current_config.session.max_history}

[bold green]Validation:[/bold green]
• Level: {current_config.validation_level.value}

[bold blue]Features:[/bold blue]"""
        
        for feature, enabled in current_config.features.items():
            status = "✓" if enabled else "✗"
            config_display += f"\n• {feature.replace('_', ' ').title()}: {status}"
        
        config_display += f"""

[bold magenta]Files:[/bold magenta]
• Config File: {config_info['config_file']}
• Exists: {'Yes' if config_info['config_exists'] else 'No'}
• API Key Set: {'Yes' if config_info['anthropic_api_key_set'] else 'No'}"""
        
        console.print(Panel(config_display, border_style="green"))
        return
    
    # Handle setting options
    if set_model or set_temperature is not None:
        current_config = load_config()
        
        if set_model:
            current_config.agent.model = set_model
            console.print(f"[green]Set model to {set_model}[/green]")
        
        if set_temperature is not None:
            if 0.0 <= set_temperature <= 1.0:
                current_config.agent.temperature = set_temperature
                console.print(f"[green]Set temperature to {set_temperature}[/green]")
            else:
                console.print("[red]Temperature must be between 0.0 and 1.0[/red]")
                return
        
        # Save updated config
        config_manager.save_config(current_config)
        console.print("[green]Configuration saved[/green]")
        return
    
    # Default: show basic info
    console.print("Use [cyan]word-cli config --show[/cyan] to see full configuration")
    console.print("Use [cyan]word-cli config --create-default[/cyan] to create a default config file")


if __name__ == "__main__":
    app()