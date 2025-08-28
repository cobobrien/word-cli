"""
Configuration management for Word CLI.

Handles loading and managing configuration from files, environment variables,
and command-line options.
"""

from __future__ import annotations

import os
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Union

from .agent.agent_core import AgentConfig
from .agent.session import SessionConfig
from .agent.sub_agents.validation_agent import ValidationLevel


@dataclass
class WordCLIConfig:
    """Main configuration for Word CLI."""
    
    # Agent configuration
    agent: AgentConfig = field(default_factory=AgentConfig)
    
    # Session configuration
    session: SessionConfig = field(default_factory=SessionConfig)
    
    # Tool configuration
    tools: Dict[str, Any] = field(default_factory=dict)
    
    # Validation configuration
    validation_level: ValidationLevel = ValidationLevel.NORMAL
    
    # File paths
    default_output_dir: Optional[Path] = None
    template_dir: Optional[Path] = None
    
    # Feature flags
    features: Dict[str, bool] = field(default_factory=lambda: {
        'cross_document_references': True,
        'advanced_validation': True,
        'batch_operations': True,
        'version_control': True,
        'streaming_responses': True
    })


class ConfigManager:
    """Manages Word CLI configuration from multiple sources."""
    
    def __init__(self):
        self.config_dir = Path.home() / '.word-cli'
        self.config_file = self.config_dir / 'config.yaml'
        self._config: Optional[WordCLIConfig] = None
    
    def load_config(self) -> WordCLIConfig:
        """Load configuration from all sources."""
        if self._config:
            return self._config
        
        # Start with defaults
        config = WordCLIConfig()
        
        # Load from file if it exists
        if self.config_file.exists():
            file_config = self._load_from_file()
            config = self._merge_configs(config, file_config)
        
        # Override with environment variables
        env_config = self._load_from_env()
        config = self._merge_configs(config, env_config)
        
        self._config = config
        return config
    
    def _load_from_file(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(self.config_file, 'r') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Warning: Could not load config file: {e}")
            return {}
    
    def _load_from_env(self) -> Dict[str, Any]:
        """Load configuration from environment variables."""
        env_config = {}
        
        # Anthropic API key
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if api_key:
            env_config['anthropic_api_key'] = api_key
        
        # Model configuration
        model = os.getenv('WORD_CLI_MODEL')
        if model:
            env_config.setdefault('agent', {})['model'] = model
        
        temperature = os.getenv('WORD_CLI_TEMPERATURE')
        if temperature:
            try:
                env_config.setdefault('agent', {})['temperature'] = float(temperature)
            except ValueError:
                pass
        
        # Validation level
        validation_level = os.getenv('WORD_CLI_VALIDATION')
        if validation_level:
            try:
                env_config['validation_level'] = ValidationLevel(validation_level.lower())
            except ValueError:
                pass
        
        # Feature flags
        for feature in ['cross_document_references', 'advanced_validation', 'batch_operations']:
            env_var = f'WORD_CLI_{feature.upper()}'
            value = os.getenv(env_var)
            if value:
                env_config.setdefault('features', {})[feature] = value.lower() in ('true', '1', 'yes', 'on')
        
        return env_config
    
    def _merge_configs(self, base: WordCLIConfig, override: Dict[str, Any]) -> WordCLIConfig:
        """Merge configuration dictionaries."""
        # This is a simplified merge - in a full implementation would handle nested merging
        
        # Agent config
        if 'agent' in override:
            agent_overrides = override['agent']
            if 'model' in agent_overrides:
                base.agent.model = agent_overrides['model']
            if 'temperature' in agent_overrides:
                base.agent.temperature = agent_overrides['temperature']
            if 'max_tokens' in agent_overrides:
                base.agent.max_tokens = agent_overrides['max_tokens']
            if 'auto_save' in agent_overrides:
                base.agent.auto_save = agent_overrides['auto_save']
        
        # Session config
        if 'session' in override:
            session_overrides = override['session']
            if 'auto_save' in session_overrides:
                base.session.auto_save = session_overrides['auto_save']
            if 'show_thinking' in session_overrides:
                base.session.show_thinking = session_overrides['show_thinking']
            if 'stream_output' in session_overrides:
                base.session.stream_output = session_overrides['stream_output']
        
        # Tools config
        if 'tools' in override:
            base.tools.update(override['tools'])
        
        # Validation level
        if 'validation_level' in override:
            if isinstance(override['validation_level'], str):
                base.validation_level = ValidationLevel(override['validation_level'])
            else:
                base.validation_level = override['validation_level']
        
        # Features
        if 'features' in override:
            base.features.update(override['features'])
        
        return base
    
    def save_config(self, config: WordCLIConfig) -> None:
        """Save configuration to file."""
        # Ensure config directory exists
        self.config_dir.mkdir(exist_ok=True)
        
        # Convert config to dict
        config_dict = {
            'agent': {
                'model': config.agent.model,
                'temperature': config.agent.temperature,
                'max_tokens': config.agent.max_tokens,
                'auto_save': config.agent.auto_save,
                'validation_level': config.agent.validation_level
            },
            'session': {
                'auto_save': config.session.auto_save,
                'show_thinking': config.session.show_thinking,
                'stream_output': config.session.stream_output,
                'max_history': config.session.max_history,
                'session_timeout': config.session.session_timeout
            },
            'tools': config.tools,
            'validation_level': config.validation_level.value,
            'features': config.features
        }
        
        if config.default_output_dir:
            config_dict['default_output_dir'] = str(config.default_output_dir)
        if config.template_dir:
            config_dict['template_dir'] = str(config.template_dir)
        
        # Save to YAML
        try:
            with open(self.config_file, 'w') as f:
                yaml.dump(config_dict, f, default_flow_style=False, indent=2)
        except Exception as e:
            print(f"Warning: Could not save config file: {e}")
    
    def create_default_config(self) -> None:
        """Create a default configuration file."""
        config = WordCLIConfig()
        self.save_config(config)
        print(f"Created default configuration at {self.config_file}")
    
    def get_config_info(self) -> Dict[str, Any]:
        """Get information about current configuration."""
        config = self.load_config()
        
        return {
            'config_file': str(self.config_file),
            'config_exists': self.config_file.exists(),
            'agent_model': config.agent.model,
            'validation_level': config.validation_level.value,
            'features_enabled': [k for k, v in config.features.items() if v],
            'anthropic_api_key_set': bool(os.getenv('ANTHROPIC_API_KEY'))
        }


# Global config manager instance
_config_manager: Optional[ConfigManager] = None

def get_config_manager() -> ConfigManager:
    """Get the global config manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager

def load_config() -> WordCLIConfig:
    """Load the current configuration."""
    return get_config_manager().load_config()