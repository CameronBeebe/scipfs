import unittest
from unittest.mock import MagicMock, patch, ANY
import json
from pathlib import Path
import sys

# Ensure scipfs modules are importable
try:
    from scipfs.llm_utils import (
        LLMClient,
        LLMError, LLMProviderNotFound, LLMAPIKeyError, 
        LLMClientInitializationError, LLMAPIError,
        LLMResponseFormatError, LLMRateLimitError, LLMAuthenticationError
    )
    from scipfs.llm_config import llm_config, LLMProviderConfig, GlobalLLMConfig
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scipfs.llm_utils import (
        LLMClient,
        LLMError, LLMProviderNotFound, LLMAPIKeyError, 
        LLMClientInitializationError, LLMAPIError,
        LLMResponseFormatError, LLMRateLimitError, LLMAuthenticationError
    )
    from scipfs.llm_config import llm_config, LLMProviderConfig, GlobalLLMConfig    

# Mock SDKs before they are potentially imported by llm_utils
# This is a common pattern: set up mocks for things that would be imported.
# We'll control their behavior within specific tests.

mock_openai = MagicMock()
mock_anthropic = MagicMock()
mock_groq = MagicMock()

# These are mock error classes that will be raised by the mocked SDKs
class MockOpenAIAPIError(Exception): pass
class MockOpenAIRateLimitError(MockOpenAIAPIError): pass
class MockOpenAIAuthError(MockOpenAIAPIError): pass
class MockOpenAIConnectionError(MockOpenAIAPIError): pass

class MockAnthropicAPIError(Exception): pass
class MockAnthropicRateLimitError(MockAnthropicAPIError): pass
class MockAnthropicAuthError(MockAnthropicAPIError): pass
class MockAnthropicConnectionError(MockAnthropicAPIError): pass

class MockGroqAPIError(Exception): pass
class MockGroqRateLimitError(MockGroqAPIError): pass
class MockGroqAuthError(MockGroqAPIError): pass
class MockGroqConnectionError(MockGroqAPIError): pass

# Apply mocks for SDKs if they are imported by name in llm_utils
# This needs to be aligned with how llm_utils imports them (e.g., from openai import OpenAI)
# We are mocking the top-level modules here.
sys.modules['openai'] = mock_openai
sys.modules['anthropic'] = mock_anthropic
sys.modules['groq'] = mock_groq

# Assign the mock error classes to the mocked SDK modules
mock_openai.APIError = MockOpenAIAPIError
mock_openai.RateLimitError = MockOpenAIRateLimitError
mock_openai.AuthenticationError = MockOpenAIAuthError
mock_openai.APIConnectionError = MockOpenAIConnectionError
mock_openai.OpenAI.return_value = MagicMock() # Mock the OpenAI() constructor call

mock_anthropic.APIError = MockAnthropicAPIError
mock_anthropic.RateLimitError = MockAnthropicRateLimitError
mock_anthropic.AuthenticationError = MockAnthropicAuthError
mock_anthropic.APIConnectionError = MockAnthropicConnectionError
mock_anthropic.Anthropic.return_value = MagicMock() # Mock the Anthropic() constructor call

mock_groq.APIError = MockGroqAPIError
mock_groq.RateLimitError = MockGroqRateLimitError
mock_groq.AuthenticationError = MockGroqAuthError
mock_groq.APIConnectionError = MockGroqConnectionError
mock_groq.Groq.return_value = MagicMock() # Mock the Groq() constructor call


class TestLLMClient(unittest.TestCase):

    def setUp(self):
        # Reset mocks for each test to avoid interference
        mock_openai.reset_mock()
        mock_anthropic.reset_mock()
        mock_groq.reset_mock()

        # Crucially, reset side_effects on the constructor mocks if they were set by a test
        mock_openai.OpenAI.side_effect = None
        mock_anthropic.Anthropic.side_effect = None
        mock_groq.Groq.side_effect = None

        # Ensure the return_value (the mock instance) is also reset if needed, 
        # or re-assigned if it's always a new MagicMock
        mock_openai.OpenAI.return_value = MagicMock() 
        mock_anthropic.Anthropic.return_value = MagicMock()
        mock_groq.Groq.return_value = MagicMock()

        # Mock the global llm_config. We'll often override specific provider configs per test.
        self.mock_llm_config_patcher = patch('scipfs.llm_utils.llm_config', spec=GlobalLLMConfig)
        self.mock_llm_config = self.mock_llm_config_patcher.start()
        
        # Setup some default behavior for the mocked llm_config
        self.mock_openai_provider_config = MagicMock(spec=LLMProviderConfig)
        self.mock_openai_provider_config.provider_name = "openai"
        self.mock_openai_provider_config.get_api_key.return_value = "fake_openai_key"
        self.mock_openai_provider_config.default_model = "gpt-4o-mini"

        self.mock_anthropic_provider_config = MagicMock(spec=LLMProviderConfig)
        self.mock_anthropic_provider_config.provider_name = "anthropic"
        self.mock_anthropic_provider_config.get_api_key.return_value = "fake_anthropic_key"
        self.mock_anthropic_provider_config.default_model = "claude-3-haiku"

        self.mock_groq_provider_config = MagicMock(spec=LLMProviderConfig)
        self.mock_groq_provider_config.provider_name = "groq"
        self.mock_groq_provider_config.get_api_key.return_value = "fake_groq_key"
        self.mock_groq_provider_config.default_model = "mixtral-8x7b-32768"

        # Default provider for llm_config mock
        self.mock_llm_config.get_default_provider.return_value = self.mock_openai_provider_config
        self.mock_llm_config.get_provider_config.side_effect = lambda name: {
            "openai": self.mock_openai_provider_config,
            "anthropic": self.mock_anthropic_provider_config,
            "groq": self.mock_groq_provider_config
        }.get(name)
        self.mock_llm_config.default_max_tokens_summary = 150
        self.mock_llm_config.default_max_tokens_tags = 50
        self.mock_llm_config.default_num_tags = 5
        self.mock_llm_config.default_temperature = 0.7

    def tearDown(self):
        self.mock_llm_config_patcher.stop()

    def test_init_success_default_provider(self):
        # Uses OpenAI as default from setUp
        client = LLMClient()
        self.assertEqual(client.provider_config.provider_name, "openai")
        self.assertEqual(client.model_name, "gpt-4o-mini")
        mock_openai.OpenAI.assert_called_once_with(api_key="fake_openai_key")

    def test_init_success_specific_provider_anthropic(self):
        client = LLMClient(provider_name="anthropic")
        self.assertEqual(client.provider_config.provider_name, "anthropic")
        self.assertEqual(client.model_name, "claude-3-haiku")
        mock_anthropic.Anthropic.assert_called_once_with(api_key="fake_anthropic_key")

    def test_init_success_specific_provider_groq_with_model(self):
        client = LLMClient(provider_name="groq", model_name="llama3-70b-8192")
        self.assertEqual(client.provider_config.provider_name, "groq")
        self.assertEqual(client.model_name, "llama3-70b-8192")
        mock_groq.Groq.assert_called_once_with(api_key="fake_groq_key")

    def test_init_provider_not_found(self):
        self.mock_llm_config.get_provider_config.return_value = None
        with self.assertRaisesRegex(LLMProviderNotFound, "Provider 'unknown_provider' not configured."):
            LLMClient(provider_name="unknown_provider")

    def test_init_no_api_key(self):
        self.mock_openai_provider_config.get_api_key.return_value = None
        with self.assertRaisesRegex(LLMAPIKeyError, "API key for openai not set."):
            LLMClient(provider_name="openai")

    def test_init_sdk_import_error_openai(self):
        # Temporarily make the import fail
        original_openai_import = mock_openai.OpenAI
        mock_openai.OpenAI = MagicMock(side_effect=ImportError("cannot import OpenAI SDK"))
        with self.assertRaisesRegex(LLMClientInitializationError, "OpenAI SDK not installed."):
            LLMClient(provider_name="openai")
        mock_openai.OpenAI = original_openai_import # Restore

    def test_init_sdk_auth_error_anthropic(self):
        # Ensure Anthropic mock is configured to raise auth error for *this test only*
        mock_anthropic.Anthropic.side_effect = MockAnthropicAuthError("Invalid Anthropic Key")
        with self.assertRaisesRegex(LLMAuthenticationError, "Anthropic authentication failed: Invalid Anthropic Key"):
            LLMClient(provider_name="anthropic")
        # It might be good practice to reset the side_effect here if not done in setUp/tearDown thoroughly
        # For now, relying on setUp to clear it for the next test.

    # --- Summarize Tests --- 
    def test_summarize_openai_success(self):
        client = LLMClient(provider_name="openai")
        mock_sdk_instance = mock_openai.OpenAI.return_value
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=" OpenAI summary. "))]
        mock_sdk_instance.chat.completions.create.return_value = mock_response

        summary = client.summarize("Some text for OpenAI.")
        self.assertEqual(summary, "OpenAI summary.")
        mock_sdk_instance.chat.completions.create.assert_called_once()
        call_args = mock_sdk_instance.chat.completions.create.call_args
        self.assertEqual(call_args[1]['model'], "gpt-4o-mini")
        self.assertIn("Summarize the following text", call_args[1]['messages'][1]['content'])

    def test_summarize_anthropic_rate_limit(self):
        # Ensure Anthropic mock is configured for successful init for this test
        # The rate limit error is on the messages.create call, not init
        mock_anthropic.Anthropic.side_effect = None # Explicitly clear side effect for init
        mock_anthropic.Anthropic.return_value = MagicMock() # Ensure a fresh instance

        client = LLMClient(provider_name="anthropic")
        mock_sdk_instance = mock_anthropic.Anthropic.return_value
        mock_sdk_instance.messages.create.side_effect = MockAnthropicRateLimitError("Rate limit hit")
        with self.assertRaisesRegex(LLMRateLimitError, "Rate limit exceeded with Anthropic: Rate limit hit"):
            client.summarize("Text for Anthropic.")

    # --- Generate Tags Tests ---
    def test_generate_tags_groq_success_json(self):
        client = LLMClient(provider_name="groq")
        mock_sdk_instance = mock_groq.Groq.return_value
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json.dumps(["tag1", "tag2"])))]
        mock_sdk_instance.chat.completions.create.return_value = mock_response

        tags = client.generate_tags("Text for Groq tags.")
        self.assertEqual(tags, ["tag1", "tag2"])
        mock_sdk_instance.chat.completions.create.assert_called_once()
        call_args = mock_sdk_instance.chat.completions.create.call_args
        self.assertEqual(call_args[1]['model'], "mixtral-8x7b-32768")
        self.assertEqual(call_args[1]['response_format'], {"type": "json_object"})
        self.assertIn("Extract exactly 5 highly relevant", call_args[1]['messages'][1]['content'])

    def test_generate_tags_openai_json_fenced(self):
        client = LLMClient(provider_name="openai")
        mock_sdk_instance = mock_openai.OpenAI.return_value
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content='```json\n["fenced_tag"]\n```'))]
        mock_sdk_instance.chat.completions.create.return_value = mock_response
        tags = client.generate_tags("Text for fenced JSON.")
        self.assertEqual(tags, ["fenced_tag"])

    def test_generate_tags_anthropic_invalid_json_response(self):
        client = LLMClient(provider_name="anthropic")
        mock_sdk_instance = mock_anthropic.Anthropic.return_value
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="not a json list")]
        mock_sdk_instance.messages.create.return_value = mock_response

        with self.assertRaisesRegex(LLMResponseFormatError, "Failed to parse JSON from anthropic for tags"):
            client.generate_tags("Text for Anthropic bad JSON.")

    def test_generate_tags_openai_not_list_of_strings(self):
        client = LLMClient(provider_name="openai")
        mock_sdk_instance = mock_openai.OpenAI.return_value
        mock_response = MagicMock()
        # Valid JSON, but not the expected format (list of strings)
        mock_response.choices = [MagicMock(message=MagicMock(content=json.dumps({"tag": "value"})))]
        mock_sdk_instance.chat.completions.create.return_value = mock_response

        with self.assertRaisesRegex(LLMResponseFormatError, "openai did not return a JSON list of strings"):
            client.generate_tags("Text for OpenAI wrong JSON type.")

if __name__ == '__main__':
    unittest.main() 