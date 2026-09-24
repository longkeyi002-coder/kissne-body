"""Kissne Mobile model-picker parity with the Hermes Dashboard."""

from _transport_harness import (
    PAIRED_INSTALLATION,
    build_session_store,
    http,
    isolated_runtime,
    make_adapter,
    pair,
    preexisting_conversation,
    run,
    start,
    stop,
)


def test_model_options_reuses_dashboard_inventory_shape(tmp_path, monkeypatch):
    import hermes_cli.inventory as inventory

    class Ctx:
        def with_overrides(self, **kwargs):
            return self

    class Runner:
        _session_model_overrides = {}

        def _resolve_session_reasoning_config(self, *, source, session_key, model):
            return {"enabled": True, "effort": "high"}

    monkeypatch.setattr(inventory, "load_picker_context", lambda: Ctx())
    monkeypatch.setattr(
        inventory,
        "build_model_options_payload",
        lambda _ctx, **_kwargs: {
            "providers": [
                {
                    "slug": "openrouter",
                    "name": "OpenRouter",
                    "models": ["anthropic/claude-sonnet-4.5", "openai/gpt-5.6"],
                },
                {"slug": "nous", "name": "Nous", "models": ["hermes-4-405b"]},
            ],
            "model": "anthropic/claude-sonnet-4.5",
            "provider": "openrouter",
        },
    )

    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            adapter.gateway_runner = Runner()
            sessions = build_session_store(home)
            conversation = preexisting_conversation(sessions)
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                return await http(port, "GET", "/model-options", token=token)
            finally:
                await stop(adapter)

    status, payload, _ = run(scenario())
    assert status == 200, payload
    assert [row["slug"] for row in payload["providers"]] == ["openrouter", "nous"]
    assert payload["providers"][0]["models"][0] == "anthropic/claude-sonnet-4.5"
    assert payload.get("efforts"), payload
    assert payload["effort"] == "high"
    assert payload["current_effort"] == "high"


def test_set_model_keeps_provider_separate_from_slashful_model_id(tmp_path):
    seen = []

    class Runner:
        _session_model_overrides = {}

        def _profile_name_for_source(self, _source, adapter_profile=None):
            return adapter_profile

        async def _handle_model_command(self, event):
            seen.append(("model", event.text))
            return "switched"

        async def _handle_reasoning_command(self, event):
            seen.append(("reasoning", event.text))
            return "reasoning set"

    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            conversation = preexisting_conversation(sessions)
            adapter.set_session_store(sessions)
            adapter.gateway_runner = Runner()
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                return await http(
                    port,
                    "POST",
                    "/set-model",
                    token=token,
                    body={
                        "provider": "openrouter",
                        "model": "anthropic/claude-sonnet-4.5",
                        "effort": "high",
                    },
                )
            finally:
                await stop(adapter)

    status, payload, _ = run(scenario())
    assert status == 200, payload
    assert seen[0] == (
        "model",
        "/model anthropic/claude-sonnet-4.5 --provider openrouter --session",
    )
    assert seen[1] == ("reasoning", "/reasoning high")
    assert payload["provider"] == "openrouter"
    assert payload["model"] == "anthropic/claude-sonnet-4.5"


def test_real_gateway_runner_wires_canonical_reasoning_resolver(tmp_path):
    """Integration contract: the production GatewayRunner, not a fake, is attached to Mobile."""
    from gateway.run import GatewayRunner
    from gateway.config import GatewayConfig

    with isolated_runtime(tmp_path):
        runner = GatewayRunner(GatewayConfig())
        adapter = make_adapter()
        runner._wire_adapter_handlers(adapter)
        adapter.gateway_runner = runner
        assert adapter.gateway_runner is runner
        resolver = getattr(adapter.gateway_runner, "_resolve_session_reasoning_config", None)
        assert callable(resolver), "production GatewayRunner must expose canonical reasoning resolver"



def test_real_gateway_reasoning_effort_default_session_override_and_fallback(tmp_path, monkeypatch):
    """Mobile reads the same production resolver used by the next Gateway turn."""
    from gateway.config import GatewayConfig
    from gateway.run import GatewayRunner

    with isolated_runtime(tmp_path):
        runner = GatewayRunner(GatewayConfig())
        adapter = make_adapter()
        runner._wire_adapter_handlers(adapter)
        adapter.gateway_runner = runner

        installation = PAIRED_INSTALLATION
        session_key = adapter.mobile_session_key(installation)

        # No session override and no configured reasoning value: Gateway's canonical
        # resolver returns None, which Mobile intentionally renders as the default medium.
        monkeypatch.setattr(runner, "_load_reasoning_config", lambda _model="": None)
        assert runner._resolve_session_reasoning_config(
            source=adapter.source_for_installation(installation),
            session_key=session_key,
            model="",
        ) is None
        assert adapter._live_reasoning_effort(installation) == "medium"

        # An explicit session override must beat the configured/default value.
        runner._set_session_reasoning_override(
            session_key, {"enabled": True, "effort": "high"}
        )
        resolved = runner._resolve_session_reasoning_config(
            source=adapter.source_for_installation(installation),
            session_key=session_key,
            model="",
        )
        assert resolved == {"enabled": True, "effort": "high"}
        assert adapter._live_reasoning_effort(installation) == "high"

        # Clearing the session override must expose the normal configured fallback again;
        # Mobile must not keep a stale session effort.
        runner._set_session_reasoning_override(session_key, None)
        monkeypatch.setattr(
            runner,
            "_load_reasoning_config",
            lambda _model="": {"enabled": True, "effort": "low"},
        )
        resolved = runner._resolve_session_reasoning_config(
            source=adapter.source_for_installation(installation),
            session_key=session_key,
            model="",
        )
        assert resolved == {"enabled": True, "effort": "low"}
        assert adapter._live_reasoning_effort(installation) == "low"
