import os
from typing import Optional, Dict, Any

# Environment variable names for API keys
# Example: SCIPFS_OPENAI_API_KEY, SCIPFS_ANTHROPIC_API_KEY
ENV_VAR_PREFIX = "SCIPFS_"
ENV_VAR_SUFFIX = "_API_KEY"

class LLMProviderConfig:
    """Configuration for a single LLM provider."""
    def __init__(self, provider_name: str, api_key_env_var: Optional[str] = None, default_model: Optional[str] = None):
        self.provider_name = provider_name.lower()
        self.api_key_env_var = api_key_env_var if api_key_env_var else f"{ENV_VAR_PREFIX}{self.provider_name.upper()}{ENV_VAR_SUFFIX}"
        self.api_key: Optional[str] = None
        self.default_model = default_model
        self._load_api_key()

    def _load_api_key(self) -> None:
        """Load API key from environment variable."""
        self.api_key = os.environ.get(self.api_key_env_var)
        if not self.api_key:
            print(f"Warning: Environment variable {self.api_key_env_var} for {self.provider_name} API key not set.")

    def get_api_key(self) -> Optional[str]:
        return self.api_key

class GlobalLLMConfig:
    """Manages global LLM settings and provider configurations."""
    def __init__(self):
        self.providers: Dict[str, LLMProviderConfig] = {}
        self.default_provider_name: Optional[str] = None
        self._initialize_providers()
        # Default settings for LLM interactions
        self.default_max_tokens_summary: int = 150
        self.default_max_tokens_tags: int = 50
        self.default_num_tags: int = 5
        self.default_temperature: float = 0.7
        # Add other global settings like context strategy, structured output requirements, etc.

    def _initialize_providers(self):
        """Initialize known LLM providers. This can be expanded or loaded from a config file."""
        # Example:
        self.add_provider("openai", default_model="gpt-4o-mini")
        self.add_provider("anthropic", default_model="claude-3-haiku-20240307")
        # A 'custom_url' provider might need different handling for API key/URL

    def add_provider(self, provider_name: str, api_key_env_var: Optional[str] = None, default_model: Optional[str] = None):
        provider_conf = LLMProviderConfig(provider_name, api_key_env_var, default_model)
        self.providers[provider_name.lower()] = provider_conf

    def get_provider_config(self, provider_name: str) -> Optional[LLMProviderConfig]:
        return self.providers.get(provider_name.lower())

    def get_api_key(self, provider_name: str) -> Optional[str]:
        provider = self.get_provider_config(provider_name)
        return provider.get_api_key() if provider else None

    def set_default_provider(self, provider_name: str):
        if provider_name.lower() in self.providers:
            self.default_provider_name = provider_name.lower()
        else:
            print(f"Warning: Provider {provider_name} not recognized. Cannot set as default.")

    def get_default_provider(self) -> Optional[LLMProviderConfig]:
        if self.default_provider_name:
            return self.get_provider_config(self.default_provider_name)
        # Fallback to the first available provider if no default is set
        if self.providers:
            return next(iter(self.providers.values()))
        return None

    def get_default_model(self, provider_name: Optional[str] = None) -> Optional[str]:
        target_provider_name = provider_name or self.default_provider_name
        if target_provider_name:
            provider = self.get_provider_config(target_provider_name)
            if provider:
                return provider.default_model
        return None # Or a global default model

# Instantiate a global LLM config object for use by other modules
llm_config = GlobalLLMConfig()

if __name__ == '__main__':
    # Example usage:
    print(f"OpenAI API Key configured: {'Yes' if llm_config.get_api_key('openai') else 'No'}")
    print(f"Anthropic API Key configured: {'Yes' if llm_config.get_api_key('anthropic') else 'No'}")
    
    llm_config.set_default_provider('openai')
    default_provider = llm_config.get_default_provider()
    if default_provider:
        print(f"Default provider: {default_provider.provider_name}")
        print(f"Default model for {default_provider.provider_name}: {default_provider.default_model}")
        print(f"API key for default provider: {'Yes' if default_provider.get_api_key() else 'No'}")

    print(f"Default summary tokens: {llm_config.default_max_tokens_summary}") 