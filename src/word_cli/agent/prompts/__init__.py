"""
Prompt engineering system for Word CLI agent.
"""

from .system_prompts import get_system_prompt, get_tool_selection_prompt
from .specialized_prompts import get_edit_analysis_prompt, get_validation_prompt

__all__ = [
    "get_system_prompt",
    "get_tool_selection_prompt", 
    "get_edit_analysis_prompt",
    "get_validation_prompt"
]