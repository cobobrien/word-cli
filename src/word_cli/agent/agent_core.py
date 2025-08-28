"""
Core AI agent system for Word CLI.

This is the main agent that orchestrates document editing operations,
similar to how Claude Code works but specialized for Word documents.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, AsyncGenerator, Union
from enum import Enum
import logging

from anthropic import Anthropic
from anthropic.types import Message, MessageParam

from ..core.document_model import DocumentModel
from ..version.version_control import VersionController, DocumentChange, ChangeType
from .tools import ToolRegistry, ToolCall, ToolResult
from .context import ContextManager, DocumentContext
from .prompts.system_prompts import get_system_prompt, get_tool_selection_prompt
from .executor import ToolExecutor, Transaction


class AgentState(Enum):
    """Current state of the agent."""
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    ERROR = "error"
    WAITING_CONFIRMATION = "waiting_confirmation"


@dataclass
class AgentConfig:
    """Configuration for the Word agent."""
    
    model: str = "claude-3-sonnet-20240229"
    temperature: float = 0.3
    max_tokens: int = 4096
    max_tool_calls: int = 10
    stream_response: bool = True
    auto_save: bool = True
    validation_level: str = "strict"  # strict, normal, permissive


@dataclass
class ConversationMessage:
    """A message in the conversation history."""
    
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    tool_calls: List[ToolCall] = field(default_factory=list)
    tool_results: List[ToolResult] = field(default_factory=list)
    
    def to_anthropic_message(self) -> MessageParam:
        """Convert to Anthropic message format."""
        if self.role == "system":
            # System messages are handled separately in Anthropic
            return None
        
        message_content = []
        
        # Add text content
        if self.content:
            message_content.append({
                "type": "text",
                "text": self.content
            })
        
        # Add tool calls if present
        if self.tool_calls and self.role == "assistant":
            for tool_call in self.tool_calls:
                message_content.append({
                    "type": "tool_use",
                    "id": tool_call.id,
                    "name": tool_call.name,
                    "input": tool_call.parameters
                })
        
        # Add tool results if present  
        if self.tool_results and self.role == "user":
            for result in self.tool_results:
                message_content.append({
                    "type": "tool_result",
                    "tool_use_id": result.tool_call_id,
                    "content": result.content if result.success else f"Error: {result.error}"
                })
        
        return {
            "role": self.role,
            "content": message_content
        }


class WordAgent:
    """
    Main AI agent for Word document editing.
    
    This agent provides Claude-like functionality specifically for Word documents,
    with access to document manipulation tools and conversation context.
    """
    
    def __init__(
        self, 
        config: Optional[AgentConfig] = None,
        anthropic_client: Optional[Anthropic] = None
    ):
        self.config = config or AgentConfig()
        self.client = anthropic_client or Anthropic()
        
        # Core components
        self.tool_registry = ToolRegistry()
        self.tool_executor = ToolExecutor()
        self.context_manager = ContextManager()
        
        # State management
        self.state = AgentState.IDLE
        self.conversation_history: List[ConversationMessage] = []
        self.current_document: Optional[DocumentModel] = None
        self.version_controller: Optional[VersionController] = None
        self.pending_transaction: Optional[Transaction] = None
        
        # Logging
        self.logger = logging.getLogger(__name__)
        
    def set_document(self, document: DocumentModel, version_controller: VersionController) -> None:
        """Set the current document and version controller."""
        self.current_document = document
        self.version_controller = version_controller
        self.context_manager.set_document(document)
        
        # Add system message about document
        doc_info = document.get_stats()
        system_msg = ConversationMessage(
            role="system",
            content=f"Document loaded: {doc_info['word_count']} words, {doc_info['paragraph_count']} paragraphs"
        )
        self.conversation_history.append(system_msg)
    
    async def process_message(self, user_input: str) -> AsyncGenerator[str, None]:
        """
        Process a user message and stream the response.
        
        Args:
            user_input: The user's message/request
            
        Yields:
            Response chunks as they're generated
        """
        if not self.current_document:
            yield "Error: No document is currently loaded. Use 'word-cli open <file>' first.\n"
            return
        
        self.state = AgentState.THINKING

        # Add user message to history
        user_msg = ConversationMessage(role="user", content=user_input)
        self.conversation_history.append(user_msg)

        try:
            # Iteratively call the model until no further tool calls are requested
            while True:
                # Get current context for better responses
                context = self.context_manager.get_relevant_context(user_input)

                # Build messages for Claude from conversation history
                messages = self._build_messages_for_claude(context)

                # Stream response from Claude for this step
                assistant_msg = ConversationMessage(role="assistant", content="")
                executed_tool_results: List[ToolResult] = []

                async for chunk in self._stream_claude_response(messages):
                    if chunk.get("type") == "text":
                        text = chunk.get("text", "")
                        assistant_msg.content += text
                        if text:
                            yield text

                    elif chunk.get("type") == "tool_use":
                        # Handle tool calls
                        self.state = AgentState.EXECUTING
                        tool_call = ToolCall(
                            id=chunk.get("id"),
                            name=chunk.get("name"),
                            parameters=chunk.get("input", {})
                        )
                        assistant_msg.tool_calls.append(tool_call)

                        # Execute tool
                        yield f"\n🔧 Using tool: {tool_call.name}\n"
                        tool_result = await self._execute_tool(tool_call)

                        # Present result to the user
                        if tool_result.success:
                            if tool_result.content:
                                yield f"✅ {tool_result.content}\n"
                        else:
                            yield f"❌ Error: {tool_result.error}\n"

                        # Queue tool result to feed back to the model in a follow-up turn
                        executed_tool_results.append(tool_result)

                # Record assistant turn
                self.conversation_history.append(assistant_msg)

                # If any tools were used, append a synthetic 'user' message with tool_result blocks
                if executed_tool_results:
                    tool_result_msg = ConversationMessage(
                        role="user",
                        content="",
                        tool_results=executed_tool_results
                    )
                    self.conversation_history.append(tool_result_msg)

                    # Continue loop so the model can incorporate tool results
                    self.state = AgentState.THINKING
                    continue

                # No tool calls in this step -> we're done
                break

            # Auto-save if configured and changes were made
            if self.config.auto_save and self.current_document.is_modified:
                await self._auto_save()
                yield "\n💾 Changes auto-saved\n"

            self.state = AgentState.IDLE

        except Exception as e:
            self.state = AgentState.ERROR
            self.logger.error(f"Error processing message: {e}", exc_info=True)
            yield f"\n❌ An error occurred: {str(e)}\n"
    
    def _build_messages_for_claude(self, context: DocumentContext) -> List[MessageParam]:
        """Build message list for Claude API call."""
        messages = []
        
        # Convert conversation history to Claude format
        for msg in self.conversation_history[-10:]:  # Keep recent history
            claude_msg = msg.to_anthropic_message()
            if claude_msg:
                messages.append(claude_msg)
        
        return messages
    
    async def _stream_claude_response(self, messages: List[MessageParam]) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream response from Claude."""
        system_prompt = get_system_prompt(
            document_name=getattr(self.current_document.source_path, 'name', 'document'),
            document_stats=self.current_document.get_stats() if self.current_document else {},
            available_tools=self.tool_registry.get_tool_schemas()
        )
        
        try:
            async with self.client.messages.stream(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                system=system_prompt,
                messages=messages,
                tools=self.tool_registry.get_tool_schemas()
            ) as stream:
                async for event in stream:
                    if event.type == "content_block_start":
                        if event.content_block.type == "text":
                            yield {"type": "text", "text": ""}
                        elif event.content_block.type == "tool_use":
                            yield {
                                "type": "tool_use",
                                "id": event.content_block.id,
                                "name": event.content_block.name,
                                "input": event.content_block.input
                            }
                    
                    elif event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            yield {"type": "text", "text": event.delta.text}
                            
        except Exception as e:
            self.logger.error(f"Error streaming from Claude: {e}")
            yield {"type": "error", "error": str(e)}
    
    async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute a tool call."""
        try:
            # Get the tool
            tool = self.tool_registry.get_tool(tool_call.name)
            if not tool:
                return ToolResult(
                    tool_call_id=tool_call.id,
                    success=False,
                    error=f"Tool {tool_call.name} not found"
                )
            
            # Execute with context
            result = await self.tool_executor.execute_tool(
                tool=tool,
                parameters=tool_call.parameters,
                document=self.current_document,
                version_controller=self.version_controller
            )
            
            # Update context if document was modified
            if result.document_modified:
                self.context_manager.update_context()
            
            return ToolResult(
                tool_call_id=tool_call.id,
                success=result.success,
                content=result.content,
                error=result.error
            )
            
        except Exception as e:
            self.logger.error(f"Error executing tool {tool_call.name}: {e}")
            return ToolResult(
                tool_call_id=tool_call.id,
                success=False,
                error=str(e)
            )
    
    async def _auto_save(self) -> None:
        """Auto-save the document."""
        if self.version_controller and self.current_document:
            self.version_controller.commit(
                self.current_document,
                "Auto-save from AI agent",
                author="word-cli-agent"
            )
    
    def get_conversation_summary(self) -> str:
        """Get a summary of the current conversation."""
        if not self.conversation_history:
            return "No conversation history"
        
        # Count messages by role
        user_msgs = len([m for m in self.conversation_history if m.role == "user"])
        assistant_msgs = len([m for m in self.conversation_history if m.role == "assistant"])
        
        # Get recent activity
        recent_msgs = self.conversation_history[-3:]
        recent_summary = []
        
        for msg in recent_msgs:
            if msg.role == "user":
                recent_summary.append(f"User: {msg.content[:50]}...")
            elif msg.role == "assistant":
                recent_summary.append(f"Assistant: {msg.content[:50]}...")
        
        return f"Conversation: {user_msgs} user messages, {assistant_msgs} responses\nRecent:\n" + "\n".join(recent_summary)
    
    def clear_conversation(self) -> None:
        """Clear conversation history."""
        self.conversation_history = []
        self.state = AgentState.IDLE
    
    def get_state_info(self) -> Dict[str, Any]:
        """Get current agent state information."""
        return {
            "state": self.state.value,
            "model": self.config.model,
            "conversation_length": len(self.conversation_history),
            "has_document": self.current_document is not None,
            "document_modified": self.current_document.is_modified if self.current_document else False,
            "available_tools": len(self.tool_registry.tools),
        }
