from typing import Optional, List, Dict, Any
import logging

# Import the global LLM config (and specific provider configs if needed)
from .llm_config import llm_config, LLMProviderConfig 

# Actual LLM client libraries will be imported in _initialize_sdk_client
# to handle potential ImportErrors gracefully.

logger = logging.getLogger(__name__)

# Custom LLM Exceptions
class LLMError(Exception):
    """Base class for LLM related errors."""
    pass

class LLMProviderNotFound(LLMError):
    """Raised when a specified LLM provider is not configured."""
    pass

class LLMAPIKeyError(LLMError):
    """Raised when an API key is missing or invalid."""
    pass

class LLMClientInitializationError(LLMError):
    """Raised when the SDK client cannot be initialized."""
    pass

class LLMAPIError(LLMError):
    """Raised for general errors during API calls."""
    pass

class LLMResponseFormatError(LLMError):
    """Raised when the LLM response is not in the expected format."""
    pass

class LLMRateLimitError(LLMAPIError):
    """Raised when an API rate limit is exceeded."""
    pass

class LLMAuthenticationError(LLMAPIKeyError):
    """Raised specifically for authentication failures (e.g., invalid API key)."""
    pass

class LLMClient:
    """Client for interacting with Large Language Models."""

    def __init__(self, provider_name: Optional[str] = None, model_name: Optional[str] = None):
        """Initialize the LLM client.

        Args:
            provider_name: Specific provider to use (e.g., 'openai', 'anthropic'). 
                           If None, uses default from llm_config.
            model_name: Specific model to use. If None, uses default for the provider.
        """
        self.provider_config: Optional[LLMProviderConfig] = None
        self.client_instance: Optional[Any] = None # Placeholder for the actual SDK client (e.g., openai.OpenAI())
        self.model_name: Optional[str] = model_name

        if provider_name:
            self.provider_config = llm_config.get_provider_config(provider_name)
            if not self.provider_config:
                logger.error(f"LLM provider '{provider_name}' not found in configuration.")
                raise LLMProviderNotFound(f"Provider '{provider_name}' not configured.")
        else:
            self.provider_config = llm_config.get_default_provider()
            if not self.provider_config:
                logger.error("No default LLM provider configured or no providers available.")
                raise LLMProviderNotFound("No LLM provider available.")
        
        logger.info(f"LLMClient initializing with provider: {self.provider_config.provider_name}")

        if not self.provider_config.get_api_key():
            logger.error(f"API key for LLM provider '{self.provider_config.provider_name}' is not set.")
            raise LLMAPIKeyError(f"API key for {self.provider_config.provider_name} not set.")

        if not self.model_name:
            self.model_name = self.provider_config.default_model
        
        if not self.model_name:
            logger.warning(f"No model specified and no default model for provider {self.provider_config.provider_name}")
            # Potentially raise error if model is essential for init

        self._initialize_sdk_client()

    def _initialize_sdk_client(self):
        """Initialize the actual LLM SDK client based on the provider."""
        # API key presence is already checked in __init__
        provider_name = self.provider_config.provider_name
        api_key = self.provider_config.get_api_key()

        try:
            if provider_name == "openai":
                try:
                    from openai import OpenAI, APIConnectionError as OpenAIAPIConnectionError, RateLimitError as OpenAIRateLimitError, AuthenticationError as OpenAIAuthenticationError, APIError as OpenAIAPIError
                    self.client_instance = OpenAI(api_key=api_key)
                    logger.info(f"OpenAI client initialized successfully for model {self.model_name}.")
                except ImportError:
                    logger.error("OpenAI SDK not found. Please install it: pip install openai")
                    raise LLMClientInitializationError("OpenAI SDK not installed.")
                except OpenAIAuthenticationError as e:
                    logger.error(f"OpenAI authentication failed: {e}")
                    raise LLMAuthenticationError(f"OpenAI authentication failed: {e}") from e
                except OpenAIRateLimitError as e:
                    logger.error(f"OpenAI rate limit exceeded during client initialization (or first call): {e}")
                    raise LLMRateLimitError(f"OpenAI rate limit hit: {e}") from e
                except OpenAIAPIConnectionError as e:
                    logger.error(f"OpenAI API connection error: {e}")
                    raise LLMAPIError(f"OpenAI API connection error: {e}") from e
                except OpenAIAPIError as e:
                    logger.error(f"OpenAI API error during client initialization: {e}")
                    raise LLMAPIError(f"OpenAI API error: {e}") from e

            elif provider_name == "anthropic":
                try:
                    from anthropic import Anthropic, APIConnectionError as AnthropicAPIConnectionError, RateLimitError as AnthropicRateLimitError, AuthenticationError as AnthropicAuthenticationError, APIError as AnthropicAPIError # type: ignore[import-not-found]
                    self.client_instance = Anthropic(api_key=api_key)
                    logger.info(f"Anthropic client initialized successfully for model {self.model_name}.")
                except ImportError:
                    logger.error("Anthropic SDK not found. Please install it: pip install anthropic")
                    raise LLMClientInitializationError("Anthropic SDK not installed.")
                except AnthropicAuthenticationError as e:
                    logger.error(f"Anthropic authentication failed: {e}")
                    raise LLMAuthenticationError(f"Anthropic authentication failed: {e}") from e
                except AnthropicRateLimitError as e:
                    logger.error(f"Anthropic rate limit exceeded during client initialization: {e}")
                    raise LLMRateLimitError(f"Anthropic rate limit hit: {e}") from e
                except AnthropicAPIConnectionError as e:
                    logger.error(f"Anthropic API connection error: {e}")
                    raise LLMAPIError(f"Anthropic API connection error: {e}") from e
                except AnthropicAPIError as e:
                    logger.error(f"Anthropic API error during client initialization: {e}")
                    raise LLMAPIError(f"Anthropic API error: {e}") from e
            elif provider_name == "groq":
                try:
                    from groq import Groq, APIConnectionError as GroqAPIConnectionError, RateLimitError as GroqRateLimitError, AuthenticationError as GroqAuthenticationError, APIError as GroqAPIError # type: ignore[import-not-found]
                    self.client_instance = Groq(api_key=api_key)
                    logger.info(f"Groq client initialized successfully for model {self.model_name}.")
                except ImportError:
                    logger.error("Groq SDK not found. Please install it: pip install groq")
                    raise LLMClientInitializationError("Groq SDK not installed.")
                except GroqAuthenticationError as e:
                    logger.error(f"Groq authentication failed: {e}")
                    raise LLMAuthenticationError(f"Groq authentication failed: {e}") from e
                except GroqRateLimitError as e:
                    logger.error(f"Groq rate limit exceeded during client initialization: {e}")
                    raise LLMRateLimitError(f"Groq rate limit hit: {e}") from e
                except GroqAPIConnectionError as e:
                    logger.error(f"Groq API connection error: {e}")
                    raise LLMAPIError(f"Groq API connection error: {e}") from e
                except GroqAPIError as e:
                    logger.error(f"Groq API error during client initialization: {e}")
                    raise LLMAPIError(f"Groq API error: {e}") from e
            else:
                logger.error(f"SDK client initialization not implemented for provider: {provider_name}")
                raise LLMClientInitializationError(f"SDK client for provider '{provider_name}' is not implemented.")
        
        except LLMError: # Re-raise our custom errors
            raise
        except Exception as e: # Catch any other unexpected errors during import or init
            logger.error(f"Failed to initialize SDK client for {provider_name} due to an unexpected error: {e}", exc_info=True)
            raise LLMClientInitializationError(f"Unexpected error initializing SDK for {provider_name}: {e}") from e

    def summarize(self, text: str, max_tokens: Optional[int] = None, temperature: Optional[float] = None) -> Optional[str]:
        """Generates a concise summary of the given text."""
        if not self.client_instance or not self.model_name:
            # This assertion helps mypy understand that provider_config is not None here.
            assert self.provider_config is not None, "Provider config should be set if client is initialized"
            logger.error(f"LLM client or model not properly initialized for summarization with provider {self.provider_config.provider_name}.")
            raise LLMClientInitializationError("Client or model not initialized before calling summarize.")
        
        # Additional assertion for clarity, though the one above should cover it.
        assert self.provider_config is not None, "Provider config must be set here."
        effective_max_tokens = max_tokens if max_tokens is not None else llm_config.default_max_tokens_summary
        effective_temperature = temperature if temperature is not None else llm_config.default_temperature
        
        provider_name = self.provider_config.provider_name
        prompt = f"Summarize the following text concisely and informatively:\n\n---\n{text}\n---"
        
        logger.info(f"Requesting summary from {provider_name} model {self.model_name} (max_tokens: {effective_max_tokens}, temp: {effective_temperature})")

        # Initialize summary to None or a default value
        summary: Optional[str] = None

        if provider_name == "openai":
            try:
                from openai import OpenAI, RateLimitError as OpenAIRateLimitError, APIConnectionError as OpenAIAPIConnectionError, AuthenticationError as OpenAIAuthenticationError, APIError as OpenAIAPIError
                response = self.client_instance.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant designed to summarize texts accurately and concisely."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=effective_max_tokens,
                    temperature=effective_temperature
                )
                raw_summary = response.choices[0].message.content
                if raw_summary:
                    summary = raw_summary.strip()
                    logger.info(f"OpenAI summary generated successfully. Length: {len(summary) if summary else 0}")
                else:
                    logger.warning("OpenAI summarization returned empty content.")
            except OpenAIAuthenticationError as e:
                logger.error(f"OpenAI authentication error during summarization: {e}")
                raise LLMAuthenticationError(f"Authentication failed with OpenAI: {e}") from e
            except OpenAIRateLimitError as e:
                logger.error(f"OpenAI rate limit exceeded during summarization: {e}")
                raise LLMRateLimitError(f"Rate limit exceeded with OpenAI: {e}") from e
            except OpenAIAPIConnectionError as e:
                logger.error(f"OpenAI API connection error during summarization: {e}")
                raise LLMAPIError(f"API connection error with OpenAI: {e}") from e
            except OpenAIAPIError as e:
                logger.error(f"OpenAI API error during summarization: {e}")
                raise LLMAPIError(f"API error with OpenAI: {e}") from e
            except Exception as e: # Catch any other unexpected errors from this provider's block
                logger.error(f"Unexpected error during OpenAI summarization: {e}", exc_info=True)
                raise LLMAPIError(f"Unexpected error with OpenAI summarization: {e}") from e
        
        elif provider_name == "anthropic":
            try:
                from anthropic import Anthropic, RateLimitError as AnthropicRateLimitError, APIConnectionError as AnthropicAPIConnectionError, AuthenticationError as AnthropicAuthenticationError, APIError as AnthropicAPIError # type: ignore[import-not-found]
                response = self.client_instance.messages.create(
                    model=self.model_name,
                    max_tokens=effective_max_tokens,
                    temperature=effective_temperature,
                    system="You are a helpful assistant designed to summarize texts accurately and concisely.",
                    messages=[{"role": "user", "content": prompt}]
                )
                raw_summary = response.content[0].text if response.content and response.content[0].text else None
                if raw_summary:
                    summary = raw_summary.strip()
                    logger.info(f"Anthropic summary generated successfully. Length: {len(summary) if summary else 0}")
                else:
                    logger.warning("Anthropic summarization returned empty content.")
            except AnthropicAuthenticationError as e:
                logger.error(f"Anthropic authentication error during summarization: {e}")
                raise LLMAuthenticationError(f"Authentication failed with Anthropic: {e}") from e
            except AnthropicRateLimitError as e:
                logger.error(f"Anthropic rate limit exceeded during summarization: {e}")
                raise LLMRateLimitError(f"Rate limit exceeded with Anthropic: {e}") from e
            except AnthropicAPIConnectionError as e:
                logger.error(f"Anthropic API connection error during summarization: {e}")
                raise LLMAPIError(f"API connection error with Anthropic: {e}") from e
            except AnthropicAPIError as e:
                logger.error(f"Anthropic API error during summarization: {e}")
                raise LLMAPIError(f"API error with Anthropic: {e}") from e
            except Exception as e:
                logger.error(f"Unexpected error during Anthropic summarization: {e}", exc_info=True)
                raise LLMAPIError(f"Unexpected error with Anthropic summarization: {e}") from e

        elif provider_name == "groq":
            try:
                from groq import Groq, RateLimitError as GroqRateLimitError, APIConnectionError as GroqAPIConnectionError, AuthenticationError as GroqAuthenticationError, APIError as GroqAPIError # type: ignore[import-not-found]
                response = self.client_instance.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant designed to summarize texts accurately and concisely."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=effective_max_tokens,
                    temperature=effective_temperature
                )
                raw_summary = response.choices[0].message.content
                if raw_summary:
                    summary = raw_summary.strip()
                    logger.info(f"Groq summary generated successfully. Length: {len(summary) if summary else 0}")
                else:
                    logger.warning("Groq summarization returned empty content.")
            except GroqAuthenticationError as e:
                logger.error(f"Groq authentication error during summarization: {e}")
                raise LLMAuthenticationError(f"Authentication failed with Groq: {e}") from e
            except GroqRateLimitError as e:
                logger.error(f"Groq rate limit exceeded during summarization: {e}")
                raise LLMRateLimitError(f"Rate limit exceeded with Groq: {e}") from e
            except GroqAPIConnectionError as e:
                logger.error(f"Groq API connection error during summarization: {e}")
                raise LLMAPIError(f"API connection error with Groq: {e}") from e
            except GroqAPIError as e:
                logger.error(f"Groq API error during summarization: {e}")
                raise LLMAPIError(f"API error with Groq: {e}") from e
            except Exception as e:
                logger.error(f"Unexpected error during Groq summarization: {e}", exc_info=True)
                raise LLMAPIError(f"Unexpected error with Groq summarization: {e}") from e
        else:
            logger.warning(f"Summarization not implemented for provider: {provider_name}")
            return f"Placeholder summary for provider {provider_name}. Text: {text[:100]}..." # Or return None / raise error

        return summary # Return the potentially None summary

    def generate_tags(self, text: str, num_tags: Optional[int] = None, max_tokens: Optional[int] = None, temperature: Optional[float] = None) -> Optional[List[str]]:
        """Generates a list of relevant keywords/tags for the given text."""
        if not self.client_instance or not self.model_name:
            # This assertion helps mypy understand that provider_config is not None here.
            assert self.provider_config is not None, "Provider config should be set if client is initialized"
            logger.error(f"LLM client or model not properly initialized for tag generation with provider {self.provider_config.provider_name}.")
            raise LLMClientInitializationError("Client or model not initialized before calling generate_tags.")
        
        # Additional assertion for clarity.
        assert self.provider_config is not None, "Provider config must be set here."
        effective_num_tags = num_tags if num_tags is not None else llm_config.default_num_tags
        effective_max_tokens = max_tokens if max_tokens is not None else llm_config.default_max_tokens_tags
        effective_temperature = temperature if temperature is not None else llm_config.default_temperature
        provider_name = self.provider_config.provider_name

        prompt = (
            f"Extract exactly {effective_num_tags} highly relevant and distinct keywords or short phrases (tags) from the following text. "
            f"Format the output STRICTLY as a JSON list of strings. For example: [\"keyword1\", \"short phrase tag\", \"concept3\"]. "
            f"Ensure the output is ONLY the JSON list and nothing else.\n\n---\nText: {text}\n---"
        )
        
        logger.info(f"Requesting tags from {provider_name} model {self.model_name} (num_tags: {effective_num_tags}, max_tokens: {effective_max_tokens}, temp: {effective_temperature})")
        
        import json # For parsing
        raw_content: Optional[str] = None
        tags_result: Optional[List[str]] = None

        if provider_name == "openai":
            try:
                from openai import OpenAI, RateLimitError as OpenAIRateLimitError, APIConnectionError as OpenAIAPIConnectionError, AuthenticationError as OpenAIAuthenticationError, APIError as OpenAIAPIError
                # For newer OpenAI models that support JSON mode explicitly:
                openai_response_format_arg: Optional[Dict[str, str]] = {"type": "json_object"}
                # Check if model might be older and not support json_object type, then don't pass it.
                # This is a simple check; a more robust solution might involve a config per model.
                if "gpt-3.5-turbo-0125" not in self.model_name and "gpt-4" not in self.model_name : # example check
                    logger.warning(f"Model {self.model_name} may not support strict JSON mode. Prompting for JSON without forcing response_format.")
                    openai_response_format_arg = None # Or don't include it in create()

                openai_api_params: Dict[str, Any] = {
                    "model": self.model_name,
                    "messages": [
                        {"role": "system", "content": "You are an expert at extracting keywords and tags. You always output a valid JSON list of strings, and nothing else."},
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": effective_max_tokens,
                    "temperature": effective_temperature
                }
                if openai_response_format_arg: # Only add if we decided to use it
                    openai_api_params["response_format"] = openai_response_format_arg
                
                response = self.client_instance.chat.completions.create(**openai_api_params)
                raw_content = response.choices[0].message.content
            except OpenAIAuthenticationError as e:
                logger.error(f"OpenAI authentication error during tag generation: {e}")
                raise LLMAuthenticationError(f"Authentication failed with OpenAI: {e}") from e
            except OpenAIRateLimitError as e:
                logger.error(f"OpenAI rate limit exceeded during tag generation: {e}")
                raise LLMRateLimitError(f"Rate limit exceeded with OpenAI: {e}") from e
            except OpenAIAPIConnectionError as e:
                logger.error(f"OpenAI API connection error during tag generation: {e}")
                raise LLMAPIError(f"API connection error with OpenAI: {e}") from e
            except OpenAIAPIError as e:
                logger.error(f"OpenAI API error during tag generation: {e}")
                raise LLMAPIError(f"API error with OpenAI: {e}") from e
            except Exception as e:
                logger.error(f"Unexpected error during OpenAI tag generation: {e}", exc_info=True)
                raise LLMAPIError(f"Unexpected error with OpenAI tag generation: {e}") from e

        elif provider_name == "anthropic":
            try:
                from anthropic import Anthropic, RateLimitError as AnthropicRateLimitError, APIConnectionError as AnthropicAPIConnectionError, AuthenticationError as AnthropicAuthenticationError, APIError as AnthropicAPIError # type: ignore[import-not-found]
                # Anthropic doesn't have a direct JSON mode like OpenAI's `response_format`.
                # Relies more heavily on the prompt for JSON structure.
                response = self.client_instance.messages.create(
                    model=self.model_name,
                    max_tokens=effective_max_tokens,
                    temperature=effective_temperature,
                    system="You are an expert at extracting keywords and tags. You always output a valid JSON list of strings, and nothing else. Your entire response should be ONLY the JSON list.",
                    messages=[{"role": "user", "content": prompt}]
                )
                raw_content = response.content[0].text if response.content and response.content[0].text else None
            except AnthropicAuthenticationError as e:
                logger.error(f"Anthropic authentication error during tag generation: {e}")
                raise LLMAuthenticationError(f"Authentication failed with Anthropic: {e}") from e
            except AnthropicRateLimitError as e:
                logger.error(f"Anthropic rate limit exceeded during tag generation: {e}")
                raise LLMRateLimitError(f"Rate limit exceeded with Anthropic: {e}") from e
            except AnthropicAPIConnectionError as e:
                logger.error(f"Anthropic API connection error during tag generation: {e}")
                raise LLMAPIError(f"API connection error with Anthropic: {e}") from e
            except AnthropicAPIError as e:
                logger.error(f"Anthropic API error during tag generation: {e}")
                raise LLMAPIError(f"API error with Anthropic: {e}") from e
            except Exception as e:
                logger.error(f"Unexpected error during Anthropic tag generation: {e}", exc_info=True)
                raise LLMAPIError(f"Unexpected error with Anthropic tag generation: {e}") from e

        elif provider_name == "groq":
            try:
                from groq import Groq, RateLimitError as GroqRateLimitError, APIConnectionError as GroqAPIConnectionError, AuthenticationError as GroqAuthenticationError, APIError as GroqAPIError # type: ignore[import-not-found]
                # Groq API is OpenAI compatible, including response_format for JSON
                groq_response_format_arg: Optional[Dict[str, str]] = {"type": "json_object"}
                # No complex model check needed here as Mixtral via Groq generally supports this.

                groq_api_params: Dict[str, Any] = {
                    "model": self.model_name,
                    "messages": [
                        {"role": "system", "content": "You are an expert at extracting keywords and tags. You always output a valid JSON list of strings, and nothing else."},
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": effective_max_tokens,
                    "temperature": effective_temperature,
                }
                if groq_response_format_arg: # Ensure this is correctly intended; Groq uses response_format directly in params usually
                    groq_api_params["response_format"] = groq_response_format_arg

                response = self.client_instance.chat.completions.create(**groq_api_params)
                raw_content = response.choices[0].message.content
            except GroqAuthenticationError as e:
                logger.error(f"Groq authentication error during tag generation: {e}")
                raise LLMAuthenticationError(f"Authentication failed with Groq: {e}") from e
            except GroqRateLimitError as e:
                logger.error(f"Groq rate limit exceeded during tag generation: {e}")
                raise LLMRateLimitError(f"Rate limit exceeded with Groq: {e}") from e
            except GroqAPIConnectionError as e:
                logger.error(f"Groq API connection error during tag generation: {e}")
                raise LLMAPIError(f"API connection error with Groq: {e}") from e
            except GroqAPIError as e:
                logger.error(f"Groq API error during tag generation: {e}")
                raise LLMAPIError(f"API error with Groq: {e}") from e
            except Exception as e:
                logger.error(f"Unexpected error during Groq tag generation: {e}", exc_info=True)
                raise LLMAPIError(f"Unexpected error with Groq tag generation: {e}") from e
        else:
            logger.warning(f"Tag generation not implemented for provider: {provider_name}")
            return [f"placeholder_tag_{i+1}_{provider_name}" for i in range(effective_num_tags)] # Or return None

        if not raw_content:
            logger.error(f"LLM ({provider_name}) returned empty content for tag generation.")
            # This specific error should be raised *after* the try-except for the API call
            # as an API error might be the cause of empty content, and should be caught first.
            raise LLMResponseFormatError(f"{provider_name} returned empty content for tags.")

        # Robust JSON parsing (common to all providers if they return raw_content)
        try:
            # Sometimes LLMs wrap JSON in ```json ... ```, try to strip it.
            if raw_content.strip().startswith("```json"):
                cleaned_content = raw_content.strip()[7:-3].strip() # Remove ```json and ```
            elif raw_content.strip().startswith("```"):
                 cleaned_content = raw_content.strip()[3:-3].strip() # Remove ```
            else:
                cleaned_content = raw_content.strip()

            parsed_json = json.loads(cleaned_content)
            if isinstance(parsed_json, list) and all(isinstance(tag, str) for tag in parsed_json):
                tags_result = parsed_json
                logger.info(f"{provider_name} tags generated and parsed successfully: {tags_result}")
            else:
                logger.error(f"LLM ({provider_name}) returned content that parsed to JSON but not a list of strings: {parsed_json}. Original content: '{raw_content}'")
                raise LLMResponseFormatError(f"{provider_name} did not return a JSON list of strings. Parsed: {type(parsed_json)}. Content: {raw_content[:200]}...")
        except json.JSONDecodeError as e_json:
            logger.error(f"Failed to parse JSON response for tags from {provider_name}. Error: {e_json}. Content: '{raw_content}'")
            raise LLMResponseFormatError(f"Failed to parse JSON from {provider_name} for tags. Error: {e_json}. Content: {raw_content[:200]}...") from e_json
        except LLMResponseFormatError: # Re-raise if it was one of our own from above
            raise
        except Exception as e: # Catch any other unexpected error during JSON parsing or validation
            logger.error(f"Unexpected error processing tags from {provider_name} after receiving content. Error: {e}. Content: '{raw_content}'", exc_info=True)
            raise LLMResponseFormatError(f"Unexpected error processing tags from {provider_name}. Original error: {e}. Content: {raw_content[:200]}...") from e
            
        return tags_result

def main():
    # Example usage of the LLMClient
    # Configure your API keys in a .env file or llm_config.yaml
    # For testing, ensure mocks are not active if you want to hit actual APIs.

    print("Testing LLMClient functionality...")

    # Test with default provider (usually OpenAI if key is set)
    try:
        print("\\n--- Testing Default Provider (OpenAI if configured) ---")
        default_provider_config = llm_config.get_default_provider()
        if default_provider_config and default_provider_config.get_api_key():
            client_default = LLMClient() 
            assert client_default.provider_config is not None # MyPy hint
            print(f"Initialized with: {client_default.provider_config.provider_name}, Model: {client_default.model_name}")
            
            summary = client_default.summarize("This is a test sentence for summarization. It is short but needs a summary.")
            print(f"Summary: {summary}")

            tags = client_default.generate_tags("This is a test sentence for tag generation. Keywords: test, tags, generation.")
            print(f"Tags: {tags}")
        else:
            print("Default provider or its API key not configured. Skipping default provider test.")

    except LLMError as e:
        print(f"LLMError with default provider: {e}")
    except Exception as e:
        logger.error(f"Unexpected error with default provider: {e}", exc_info=True)


    # Test with a specific provider, e.g., Groq (if key is set)
    # Replace \'groq\' and model with another provider if you have its key.
    TEST_PROVIDER = "groq" 
    test_provider_config = llm_config.get_provider_config(TEST_PROVIDER)

    if test_provider_config and test_provider_config.get_api_key():
        try:
            print(f"\\n--- Testing Specific Provider: {TEST_PROVIDER} ---")
            client_groq = LLMClient(provider_name=TEST_PROVIDER, model_name=test_provider_config.default_model or "mixtral-8x7b-32768") # Fallback model
            assert client_groq.provider_config is not None # MyPy hint
            print(f"Initialized with: {client_groq.provider_config.provider_name}, Model: {client_groq.model_name}")

            summary_groq = client_groq.summarize("Exploring the capabilities of Groq\'s inference engine with a sample text.")
            print(f"Groq Summary: {summary_groq}")

            tags_groq = client_groq.generate_tags("Groq offers fast LLM inference. Tags might include: Groq, LLM, inference, speed.")
            print(f"Groq Tags: {tags_groq}")

        except LLMError as e:
            print(f"LLMError with {TEST_PROVIDER}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error with {TEST_PROVIDER} test: {e}", exc_info=True)
    else:
        print(f"{TEST_PROVIDER} provider or its API key not configured. Skipping {TEST_PROVIDER} test.")

    # Test error handling: Provider not found
    try:
        print("\\n--- Testing Provider Not Found ---")
        LLMClient(provider_name="non_existent_provider")
    except LLMProviderNotFound as e:
        print(f"Caught expected error: {e}")
    except Exception as e:
        logger.error(f"Caught unexpected error for non_existent_provider: {e}", exc_info=True)

    # Test error handling: API key error (if a provider is configured without a key)
    # This requires a provider in llm_config.yaml that has no API_KEY_ENV set or env var missing
    # Example: Add a dummy provider \'test_no_key\' to config with no API key details for this to be effective.
    test_provider_no_key_name = "test_no_key_provider_for_testing_llm_utils_main_func" 
    no_key_provider_config = llm_config.get_provider_config(test_provider_no_key_name) 
    if no_key_provider_config: # Check if such a config exists
        # We expect get_api_key() to be None or the key itself to be false-ish (e.g. empty string)
        # if not no_key_provider_config.get_api_key(): 
        # The LLMClient constructor should raise LLMAPIKeyError if the key is missing for a configured provider.
        try:
            print(f"\\n--- Testing API Key Error ({test_provider_no_key_name}) ---")
            LLMClient(provider_name=test_provider_no_key_name)
            print(f"ERROR: LLMClient did not raise an error for {test_provider_no_key_name} which should have a missing key.")
        except LLMAPIKeyError as e:
            print(f"Caught expected API Key error for {test_provider_no_key_name}: {e}")
        except LLMProviderNotFound as e: # Should not happen if no_key_provider_config is True
             print(f"LLMProviderNotFound (unexpected here) for {test_provider_no_key_name}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error for {test_provider_no_key_name} API key test: {e}", exc_info=True)
    else:
        print(f"Provider \'{test_provider_no_key_name}\' not configured for API key error test. Skipping.")

if __name__ == "__main__":
    # Setup basic logging for seeing messages from the LLMClient
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # You might want to set to DEBUG for more verbose output from the client
    # logging.getLogger("scipfs.llm_utils").setLevel(logging.DEBUG) 
    
    main() 