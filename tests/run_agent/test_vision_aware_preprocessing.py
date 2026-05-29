"""Tests for the vision-aware image preprocessing in run_agent.py.

Covers:

* ``_prepare_anthropic_messages_for_api`` — passes image parts through
  unchanged when the active model reports ``supports_vision=True`` (the
  adapter handles them natively), and falls back to text-description
  replacement when the model lacks vision.

* ``_prepare_messages_for_non_vision_model`` — the mirror method for the
  chat.completions / codex_responses paths. Same contract.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from run_agent import AIAgent


def _make_agent() -> AIAgent:
    """Build a bare-bones AIAgent instance without running __init__.

    Avoids the heavy provider/credential setup for these pure-method tests.
    """
    agent = object.__new__(AIAgent)
    agent.provider = "anthropic"
    agent.model = "claude-sonnet-4"
    agent._anthropic_image_fallback_cache = {}
    return agent


def _make_chat_agent_for_kwargs() -> AIAgent:
    """Build a minimal chat_completions agent for _build_api_kwargs tests."""
    agent = object.__new__(AIAgent)
    agent.api_mode = "chat_completions"
    agent.provider = "custom"
    agent.model = "qwen3-coder-480b-a35b"
    agent.base_url = "http://127.0.0.1:8000/v1"
    agent._base_url_lower = agent.base_url.lower()
    agent._base_url_hostname = "127.0.0.1"
    agent.tools = []
    agent.max_tokens = 4096
    agent.reasoning_config = {}
    agent.request_overrides = {}
    agent.session_id = "sess_test"
    agent.providers_allowed = []
    agent.providers_ignored = []
    agent.providers_order = []
    agent.provider_sort = None
    agent.provider_require_parameters = False
    agent.provider_data_collection = None
    agent._ephemeral_max_output_tokens = None
    agent._ollama_num_ctx = None
    agent._max_tokens_param = lambda x: {"max_tokens": x}
    agent._is_qwen_portal = lambda: False
    agent._is_openrouter_url = lambda: False
    agent._resolved_api_call_timeout = lambda: 30.0
    agent._supports_reasoning_extra_body = lambda: False
    agent._github_models_reasoning_extra_body = lambda: None
    agent._lmstudio_reasoning_options_cached = lambda: None
    return agent


IMG_PARTS_USER_MSG = {
    "role": "user",
    "content": [
        {"type": "text", "text": "What's in this image?"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
    ],
}

PLAIN_USER_MSG = {"role": "user", "content": "hello, no images here"}


# ─── _prepare_anthropic_messages_for_api ─────────────────────────────────────


class TestPrepareAnthropicMessages:
    def test_no_images_passes_through(self):
        agent = _make_agent()
        msgs = [PLAIN_USER_MSG]
        out = agent._prepare_anthropic_messages_for_api(msgs)
        assert out is msgs  # unchanged reference

    def test_vision_capable_passes_images_through(self):
        """The Anthropic adapter handles image_url/input_image natively."""
        agent = _make_agent()
        with patch.object(agent, "_model_supports_vision", return_value=True):
            out = agent._prepare_anthropic_messages_for_api([IMG_PARTS_USER_MSG])
        # Passes through unchanged — image_url parts still present.
        assert out[0]["content"][1]["type"] == "image_url"

    def test_non_vision_replaces_images_with_text(self):
        agent = _make_agent()
        with patch.object(agent, "_model_supports_vision", return_value=False), \
             patch.object(
                 agent,
                 "_describe_image_for_anthropic_fallback",
                 return_value="[Image description: a cat]",
             ):
            out = agent._prepare_anthropic_messages_for_api([IMG_PARTS_USER_MSG])
        # Content collapsed to a string containing the description + user text.
        content = out[0]["content"]
        assert isinstance(content, str)
        assert "[Image description: a cat]" in content
        assert "What's in this image?" in content
        # No more image parts.
        assert "image_url" not in content


# ─── _prepare_messages_for_non_vision_model ──────────────────────────────────


class TestPrepareMessagesForNonVision:
    def test_no_images_passes_through(self):
        agent = _make_agent()
        msgs = [PLAIN_USER_MSG]
        out = agent._prepare_messages_for_non_vision_model(msgs)
        assert out is msgs

    def test_vision_capable_passes_through(self):
        """For vision-capable models on chat.completions path, provider handles pixels."""
        agent = _make_agent()
        agent.provider = "openrouter"
        agent.model = "anthropic/claude-sonnet-4"
        with patch.object(agent, "_model_supports_vision", return_value=True):
            out = agent._prepare_messages_for_non_vision_model([IMG_PARTS_USER_MSG])
        assert out[0]["content"][1]["type"] == "image_url"

    def test_non_vision_strips_images(self):
        agent = _make_agent()
        agent.provider = "openrouter"
        agent.model = "qwen/qwen3-235b-a22b"
        with patch.object(agent, "_model_supports_vision", return_value=False), \
             patch.object(
                 agent,
                 "_describe_image_for_anthropic_fallback",
                 return_value="[Image description: a dog]",
             ):
            out = agent._prepare_messages_for_non_vision_model([IMG_PARTS_USER_MSG])
        content = out[0]["content"]
        assert isinstance(content, str)
        assert "[Image description: a dog]" in content
        assert "image_url" not in content

    def test_multiple_messages_with_mixed_content(self):
        agent = _make_agent()
        agent.model = "qwen/qwen3-235b"
        msgs = [
            {"role": "user", "content": "first turn"},
            {"role": "assistant", "content": "ack"},
            IMG_PARTS_USER_MSG,
        ]
        with patch.object(agent, "_model_supports_vision", return_value=False), \
             patch.object(
                 agent,
                 "_describe_image_for_anthropic_fallback",
                 return_value="[Image: thing]",
             ):
            out = agent._prepare_messages_for_non_vision_model(msgs)
        # First two messages unchanged (no images), third stripped.
        assert out[0]["content"] == "first turn"
        assert out[1]["content"] == "ack"
        assert isinstance(out[2]["content"], str)
        assert "[Image: thing]" in out[2]["content"]


class TestBuildApiKwargsProfilePath:
    def test_profile_path_still_applies_non_vision_image_fallback(self):
        """Provider-profile chat_completions path must preserve image fallback."""
        agent = _make_chat_agent_for_kwargs()
        expected_msgs = [{"role": "user", "content": "[Image description: fallback]"}]
        transport = MagicMock()
        transport.build_kwargs.return_value = {"messages": expected_msgs}
        agent._get_transport = lambda: transport

        with patch("providers.get_provider_profile", return_value=object()), \
             patch.object(
                 agent,
                 "_prepare_messages_for_non_vision_model",
                 return_value=expected_msgs,
             ) as prep_mock:
            result = agent._build_api_kwargs([IMG_PARTS_USER_MSG])

        prep_mock.assert_called_once_with([IMG_PARTS_USER_MSG])
        assert transport.build_kwargs.call_count == 1
        assert transport.build_kwargs.call_args.kwargs["messages"] == expected_msgs
        assert result["messages"] == expected_msgs


# ─── _model_supports_vision ──────────────────────────────────────────────────


class TestModelSupportsVision:
    def test_missing_provider_or_model_returns_false(self):
        agent = _make_agent()
        agent.provider = ""
        agent.model = "claude-sonnet-4"
        assert agent._model_supports_vision() is False
        agent.provider = "anthropic"
        agent.model = ""
        assert agent._model_supports_vision() is False

    def test_uses_get_model_capabilities(self):
        agent = _make_agent()
        fake_caps = MagicMock()
        fake_caps.supports_vision = True
        with patch("agent.models_dev.get_model_capabilities", return_value=fake_caps):
            assert agent._model_supports_vision() is True
        fake_caps.supports_vision = False
        with patch("agent.models_dev.get_model_capabilities", return_value=fake_caps):
            assert agent._model_supports_vision() is False

    def test_none_caps_returns_false(self):
        agent = _make_agent()
        with patch("agent.models_dev.get_model_capabilities", return_value=None):
            assert agent._model_supports_vision() is False

    def test_exception_returns_false(self):
        agent = _make_agent()
        with patch("agent.models_dev.get_model_capabilities", side_effect=RuntimeError("boom")):
            assert agent._model_supports_vision() is False

    def test_top_level_model_override_wins(self):
        agent = _make_agent()
        agent.provider = "custom"
        agent.model = "my-llava"
        with patch("hermes_cli.config.load_config", return_value={"model": {"supports_vision": True}}), \
             patch("agent.models_dev.get_model_capabilities", return_value=None):
            assert agent._model_supports_vision() is True

    def test_per_provider_per_model_override_wins(self):
        agent = _make_agent()
        agent.provider = "custom"
        agent.model = "my-llava"
        cfg = {"providers": {"custom": {"models": {"my-llava": {"supports_vision": True}}}}}
        with patch("hermes_cli.config.load_config", return_value=cfg), \
             patch("agent.models_dev.get_model_capabilities", return_value=None):
            assert agent._model_supports_vision() is True

    def test_named_custom_provider_resolved_via_config_provider(self):
        # Named custom providers get runtime self.provider rewritten to
        # "custom" while the config keeps the original name under
        # model.provider. The override must still resolve.
        agent = _make_agent()
        agent.provider = "custom"
        agent.model = "my-llava"
        cfg = {
            "model": {"provider": "my-vllm", "default": "my-llava"},
            "providers": {"my-vllm": {"models": {"my-llava": {"supports_vision": True}}}},
        }
        with patch("hermes_cli.config.load_config", return_value=cfg), \
             patch("agent.models_dev.get_model_capabilities", return_value=None):
            assert agent._model_supports_vision() is True

    def test_override_false_disables_vision_for_models_dev_models(self):
        agent = _make_agent()
        fake_caps = MagicMock()
        fake_caps.supports_vision = True
        with patch("hermes_cli.config.load_config", return_value={"model": {"supports_vision": False}}), \
             patch("agent.models_dev.get_model_capabilities", return_value=fake_caps):
            assert agent._model_supports_vision() is False
