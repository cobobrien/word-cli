"""
AI Agent system for Word CLI.

Provides Claude-powered document editing with natural language understanding.
"""

from .agent_core import WordAgent, AgentState
from .session import InteractiveSession
from .tools import DocumentTool, get_all_tools

__all__ = ["WordAgent", "AgentState", "InteractiveSession", "DocumentTool", "get_all_tools"]