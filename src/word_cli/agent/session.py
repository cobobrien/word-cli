"""
Interactive Session Manager for Word CLI.

Provides a Claude Code-like interactive experience for document editing,
with streaming responses, conversation management, and session state.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, AsyncGenerator
from pathlib import Path
import signal

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text

from .agent_core import WordAgent, AgentConfig, ConversationMessage, AgentState
from ..core.document_model import DocumentModel
from ..version.version_control import VersionController


@dataclass
class SessionConfig:
    """Configuration for interactive sessions."""
    
    auto_save: bool = True
    show_thinking: bool = True
    stream_output: bool = True
    max_history: int = 100
    session_timeout: int = 3600  # 1 hour
    
    # Display settings
    show_document_stats: bool = True
    show_tool_usage: bool = True
    show_timestamps: bool = False


@dataclass
class SessionState:
    """Current state of the interactive session."""
    
    session_id: str = ""
    is_active: bool = False
    current_document: Optional[DocumentModel] = None
    document_path: Optional[Path] = None
    version_controller: Optional[VersionController] = None
    
    # Statistics
    messages_exchanged: int = 0
    edits_made: int = 0
    tools_used: int = 0
    session_start_time: float = 0.0


class InteractiveSession:
    """
    Main interactive session manager for Word CLI.
    
    Provides a Claude Code-like experience with streaming responses,
    natural conversation, and document editing capabilities.
    """
    
    def __init__(
        self, 
        config: Optional[SessionConfig] = None,
        agent_config: Optional[AgentConfig] = None
    ):
        self.config = config or SessionConfig()
        self.console = Console()
        self.agent = WordAgent(agent_config)
        
        self.state = SessionState()
        self.is_running = False
        self._shutdown_requested = False
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)
    
    def _handle_interrupt(self, signum: int, frame: Any) -> None:
        """Handle interrupt signals gracefully."""
        self._shutdown_requested = True
        
        if self.is_running:
            self.console.print("\n[yellow]Interrupt received. Finishing current operation...[/yellow]")
            self.console.print("Press Ctrl+C again to force exit.")
    
    async def start_session(self, document_path: Optional[Path] = None) -> None:
        """
        Start an interactive editing session.
        
        Args:
            document_path: Optional path to document to open initially
        """
        import time
        import uuid
        
        self.state.session_id = f"session_{uuid.uuid4().hex[:8]}"
        self.state.session_start_time = time.time()
        self.state.is_active = True
        self.is_running = True
        
        # Show welcome message
        self._show_welcome()
        
        # Open document if provided
        if document_path:
            success = await self._open_document(document_path)
            if not success:
                self.console.print(f"[red]Failed to open {document_path}[/red]")
                return
        
        # Start the interaction loop
        try:
            await self._interaction_loop()
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Session interrupted by user[/yellow]")
        except Exception as e:
            self.console.print(f"\n[red]Session error: {e}[/red]")
        finally:
            await self._cleanup_session()
    
    def _show_welcome(self) -> None:
        """Show welcome message and instructions."""
        welcome_text = """
# Welcome to Word CLI Interactive Mode! 

I'm your AI assistant for editing Word documents. Here's what I can do:

**Document Operations:**
• Open and read any part of your document
• Edit paragraphs, sections, and content precisely  
• Find and replace text throughout the document
• Add, remove, and reorganize content

**Smart Features:**
• Understand requests in natural language
• Reference content from other documents
• Track all changes with version control
• Validate edits for safety and integrity

**Commands:**
• Type your editing requests naturally
• Use `/help` for more commands
• Use `/status` to see document info
• Use `/quit` to exit

Let's start editing! What would you like to do?
        """
        
        panel = Panel(
            Markdown(welcome_text.strip()),
            title="🤖 Word CLI Agent",
            border_style="blue",
            padding=(1, 2)
        )
        
        self.console.print(panel)
        
        if not self.state.current_document:
            self.console.print("\n[dim]💡 No document is open. Use '/open <filename>' to open a document first.[/dim]\n")
    
    async def _interaction_loop(self) -> None:
        """Main interaction loop."""
        while self.is_running and not self._shutdown_requested:
            try:
                # Get user input
                user_input = await self._get_user_input()
                
                if not user_input.strip():
                    continue
                
                # Handle special commands
                if user_input.startswith('/'):
                    await self._handle_command(user_input)
                    continue
                
                # Process with agent
                await self._process_user_message(user_input)
                
                self.state.messages_exchanged += 1
                
            except EOFError:
                # User pressed Ctrl+D
                break
            except KeyboardInterrupt:
                # User pressed Ctrl+C
                if self._shutdown_requested:
                    break
                self._shutdown_requested = True
                self.console.print("\n[yellow]Press Ctrl+C again to exit or continue typing...[/yellow]")
                await asyncio.sleep(1)
                self._shutdown_requested = False
    
    async def _get_user_input(self) -> str:
        """Get user input with proper prompt."""
        # Show status line
        if self.config.show_document_stats and self.state.current_document:
            stats = self.state.current_document.get_stats()
            status = f"📄 {stats['word_count']} words"
            if self.state.current_document.is_modified:
                status += " [yellow]●[/yellow]"  # Modified indicator
        else:
            status = "📄 No document"
        
        prompt_text = f"\n[dim]{status}[/dim]\n[bold cyan]word-cli>[/bold cyan] "
        
        # Use asyncio to make input non-blocking
        loop = asyncio.get_event_loop()
        user_input = await loop.run_in_executor(None, input, prompt_text)
        
        return user_input.strip()
    
    async def _handle_command(self, command: str) -> None:
        """Handle special slash commands."""
        parts = command[1:].split()  # Remove leading '/'
        cmd = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        if cmd == 'help':
            self._show_help()
        
        elif cmd == 'status':
            self._show_status()
        
        elif cmd == 'open':
            if args:
                doc_path = Path(' '.join(args))
                await self._open_document(doc_path)
            else:
                self.console.print("[red]Usage: /open <filename>[/red]")
        
        elif cmd == 'save':
            await self._save_document()
        
        elif cmd == 'history':
            self._show_conversation_history()
        
        elif cmd == 'clear':
            self.console.clear()
            self.agent.clear_conversation()
            self.console.print("[green]Conversation history cleared[/green]")
        
        elif cmd in ['quit', 'exit']:
            self.is_running = False
        
        else:
            self.console.print(f"[red]Unknown command: /{cmd}[/red]")
            self.console.print("Use [cyan]/help[/cyan] to see available commands")
    
    async def _process_user_message(self, user_input: str) -> None:
        """Process a user message with the agent."""
        if not self.state.current_document:
            self.console.print("[red]No document is open. Use '/open <filename>' to open a document first.[/red]")
            return
        
        # Show thinking indicator if enabled
        thinking_task = None
        if self.config.show_thinking:
            thinking_task = asyncio.create_task(self._show_thinking_spinner())
        
        try:
            # Stream response from agent
            response_parts = []
            
            async for chunk in self.agent.process_message(user_input):
                if thinking_task:
                    thinking_task.cancel()
                    thinking_task = None
                
                # Print chunk immediately for streaming effect
                if chunk.strip():
                    self.console.print(chunk, end='')
                    response_parts.append(chunk)
            
            # Update statistics
            if 'tool:' in ' '.join(response_parts).lower():
                self.state.tools_used += 1
            
            if self.state.current_document.is_modified:
                self.state.edits_made += 1
        
        finally:
            if thinking_task:
                thinking_task.cancel()
    
    async def _show_thinking_spinner(self) -> None:
        """Show a thinking spinner while the agent processes."""
        spinner = Spinner('dots', text="[dim]Thinking...[/dim]")
        
        with Live(spinner, console=self.console, transient=True) as live:
            try:
                while True:
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                pass
    
    async def _open_document(self, doc_path: Path) -> bool:
        """Open a document for editing."""
        try:
            from ..converters.docx_to_ast import DocxToASTConverter
            from ..version.version_control import VersionController
            
            if not doc_path.exists():
                self.console.print(f"[red]File not found: {doc_path}[/red]")
                return False
            
            if doc_path.suffix.lower() != '.docx':
                self.console.print("[red]Only .docx files are supported[/red]")
                return False
            
            # Show loading spinner
            with Live(Spinner('dots', text=f"[dim]Opening {doc_path.name}...[/dim]"), console=self.console, transient=True):
                converter = DocxToASTConverter()
                document = converter.convert(doc_path)
                
                # Setup version control
                vc = VersionController()
                initial_version = vc.commit(
                    document,
                    f"Initial load of {doc_path.name}",
                    author="word-cli-session"
                )
            
            # Update session state
            self.state.current_document = document
            self.state.document_path = doc_path
            self.state.version_controller = vc
            
            # Set document in agent
            self.agent.set_document(document, vc)
            
            # Show success message
            stats = document.get_stats()
            success_msg = f"[green]✓[/green] Opened [cyan]{doc_path.name}[/cyan] ({stats['word_count']} words, {stats['paragraph_count']} paragraphs)"
            self.console.print(success_msg)
            
            return True
            
        except Exception as e:
            self.console.print(f"[red]Error opening document: {e}[/red]")
            return False
    
    async def _save_document(self) -> None:
        """Save the current document."""
        if not self.state.current_document or not self.state.document_path:
            self.console.print("[red]No document to save[/red]")
            return
        
        try:
            from ..converters.ast_to_docx import ASTToDocxConverter
            
            with Live(Spinner('dots', text="[dim]Saving document...[/dim]"), console=self.console, transient=True):
                converter = ASTToDocxConverter()
                converter.convert(self.state.current_document, self.state.document_path)
                
                # Create version if modified
                if self.state.current_document.is_modified and self.state.version_controller:
                    version = self.state.version_controller.commit(
                        self.state.current_document,
                        "Manual save from interactive session"
                    )
            
            self.console.print(f"[green]✓[/green] Saved [cyan]{self.state.document_path.name}[/cyan]")
            
        except Exception as e:
            self.console.print(f"[red]Error saving document: {e}[/red]")
    
    def _show_help(self) -> None:
        """Show help information."""
        help_text = """
## Available Commands

**Document Operations:**
• `/open <filename>` - Open a Word document
• `/save` - Save the current document
• `/status` - Show document status and statistics

**Session Management:**
• `/history` - Show conversation history
• `/clear` - Clear conversation history  
• `/quit` or `/exit` - Exit the session

**Natural Language Editing:**
Just type what you want to do! Examples:
• "Edit paragraph 3 to say..."
• "Find all instances of 'contract' and replace with 'agreement'"
• "Add a new section about payment terms"
• "Copy the liability clause from contract_template.docx"

**Tips:**
• Be specific about what you want to change
• I can reference other documents for copying content
• All changes are tracked with version control
• Use `/status` to see if your document has unsaved changes
        """
        
        panel = Panel(
            Markdown(help_text.strip()),
            title="Help",
            border_style="green"
        )
        
        self.console.print(panel)
    
    def _show_status(self) -> None:
        """Show current session and document status."""
        # Agent status
        agent_info = self.agent.get_state_info()
        
        status_parts = [
            f"**Session:** {self.state.session_id}",
            f"**Agent State:** {agent_info['state']}",
            f"**Model:** {agent_info['model']}",
            f"**Messages:** {self.state.messages_exchanged}",
            f"**Tools Used:** {self.state.tools_used}",
            f"**Edits Made:** {self.state.edits_made}",
        ]
        
        # Document status
        if self.state.current_document:
            stats = self.state.current_document.get_stats()
            status_parts.extend([
                "",
                f"**Document:** {self.state.document_path.name if self.state.document_path else 'Unknown'}",
                f"**Word Count:** {stats['word_count']}",
                f"**Paragraphs:** {stats['paragraph_count']}",
                f"**Headings:** {stats['heading_count']}",
                f"**Modified:** {'Yes' if stats['is_modified'] else 'No'}",
                f"**Last Modified:** {stats['last_modified']}"
            ])
            
            # Version info
            if self.state.version_controller:
                current_branch = self.state.version_controller.get_current_branch()
                head_version = self.state.version_controller.get_head_version()
                status_parts.extend([
                    "",
                    f"**Current Branch:** {current_branch}",
                    f"**Head Version:** {head_version[:8] if head_version else 'None'}"
                ])
        else:
            status_parts.append("\n**Document:** None (use `/open <filename>` to open)")
        
        status_text = "\n".join(status_parts)
        
        panel = Panel(
            Markdown(status_text),
            title="Session Status",
            border_style="blue"
        )
        
        self.console.print(panel)
    
    def _show_conversation_history(self) -> None:
        """Show recent conversation history."""
        summary = self.agent.get_conversation_summary()
        
        panel = Panel(
            Text(summary),
            title="Conversation History",
            border_style="yellow"
        )
        
        self.console.print(panel)
    
    async def _cleanup_session(self) -> None:
        """Clean up session resources."""
        self.is_running = False
        self.state.is_active = False
        
        # Save document if modified
        if (self.state.current_document and 
            self.state.current_document.is_modified and 
            self.config.auto_save):
            self.console.print("[yellow]Auto-saving modified document...[/yellow]")
            await self._save_document()
        
        # Show session summary
        session_duration = time.time() - self.state.session_start_time
        
        summary_text = f"""
**Session Summary:**
• Duration: {session_duration:.1f} seconds
• Messages: {self.state.messages_exchanged}
• Edits: {self.state.edits_made}  
• Tools Used: {self.state.tools_used}

Thank you for using Word CLI! 👋
        """
        
        panel = Panel(
            Markdown(summary_text.strip()),
            title="Session Complete",
            border_style="green"
        )
        
        self.console.print(panel)


# Utility function for easy session creation
async def start_interactive_session(
    document_path: Optional[Path] = None,
    config: Optional[SessionConfig] = None
) -> None:
    """
    Start an interactive Word CLI session.
    
    Args:
        document_path: Optional document to open initially
        config: Session configuration
    """
    session = InteractiveSession(config)
    await session.start_session(document_path)