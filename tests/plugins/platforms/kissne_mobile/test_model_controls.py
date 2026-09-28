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
        def __init__(self, adapter):
            self.adapter = adapter
            self._session_model_overrides = {}
            self._session_reasoning_overrides = {}

        def _resolve_session_reasoning_config(self, *, source, session_key, model):
            return self._session_reasoning_overrides.get(session_key)

        def _profile_name_for_source(self, _source, adapter_profile=None):
            return adapter_profile

        async def _handle_model_command(self, event):
            seen.append(("model", event.text))
            self._session_model_overrides[self.adapter.mobile_session_key(PAIRED_INSTALLATION)] = {
                "model": "anthropic/claude-sonnet-4.5", "provider": "openrouter",
            }
            return "switched"

        async def _handle_reasoning_command(self, event):
            seen.append(("reasoning", event.text))
            self._session_reasoning_overrides[self.adapter.mobile_session_key(PAIRED_INSTALLATION)] = {
                "enabled": True, "effort": "high",
            }
            return "reasoning set"

    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            conversation = preexisting_conversation(sessions)
            adapter.set_session_store(sessions)
            adapter.gateway_runner = Runner(adapter)
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


def test_set_model_refuses_uncommitted_command_ack(tmp_path):
    class Runner:
        _session_model_overrides = {}

        async def _handle_model_command(self, event):
            # A picker/confirmation may accept the request without committing it.
            return None

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
                response = await http(port, "POST", "/set-model", token=token,
                                      body={"model": "mimo-v2.6-flash", "provider": "opencode-go"})
                return response, sessions.get_model_override(adapter.mobile_session_key(PAIRED_INSTALLATION))
            finally:
                await stop(adapter)

    (status, payload, _), override = run(scenario())
    assert status == 409
    assert payload["error"] == "model_switch_not_applied"
    assert override is None


def test_model_options_reports_saved_session_route_not_global_default(tmp_path, monkeypatch):
    import hermes_cli.inventory as inventory

    context = inventory.ConfigContext("google", "old", "", {}, [])
    observed = []
    monkeypatch.setattr(inventory, "load_picker_context", lambda: context)

    def build(ctx, **kwargs):
        observed.append((ctx.current_provider, ctx.current_model))
        return {"providers": [{"slug": ctx.current_provider, "name": ctx.current_provider,
                               "models": [ctx.current_model], "is_current": True}],
                "provider": ctx.current_provider, "model": ctx.current_model}

    monkeypatch.setattr(inventory, "build_model_options_payload", build)

    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            conversation = preexisting_conversation(sessions)
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                sessions.set_model_override(adapter.mobile_session_key(PAIRED_INSTALLATION),
                                            {"provider": "opencode-go", "model": "mimo-v2.6-flash"})
                return await http(port, "GET", "/model-options", token=token)
            finally:
                await stop(adapter)

    status, payload, _ = run(scenario())
    assert status == 200
    assert observed == [("opencode-go", "mimo-v2.6-flash")]
    assert payload["model"] == "mimo-v2.6-flash"
    assert payload["provider"] == "opencode-go"


def test_real_gateway_model_command_reaches_next_mobile_turn(tmp_path, monkeypatch):
    """Exercise Mobile HTTP -> real /model handler -> the next turn's real override reader."""
    from gateway.config import GatewayConfig
    from gateway.run import GatewayRunner
    from hermes_cli.model_switch import ModelSwitchResult

    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            conversation = preexisting_conversation(sessions)
            adapter.set_session_store(sessions)
            runner = GatewayRunner(GatewayConfig())
            runner.session_store = sessions
            adapter.gateway_runner = runner

            async def resolve(_ctx, _model, _provider, _source):
                return ModelSwitchResult(
                    success=True, new_model="mimo-v2.6-flash", target_provider="opencode-go",
                    api_key="test-only", base_url="http://127.0.0.1/unused",
                    api_mode="chat_completions", provider_label="OpenCode Go",
                ), None

            async def no_guard(*_args):
                return False, None

            async def confirmation(*_args, **_kwargs):
                return "switched"

            monkeypatch.setattr(runner, "_perform_model_switch", resolve)
            monkeypatch.setattr(runner, "_model_selection_guard_reply", no_guard)
            monkeypatch.setattr(runner, "_model_switch_confirmation", confirmation)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                response = await http(port, "POST", "/set-model", token=token,
                                      body={"model": "mimo-v2.6-flash", "provider": "opencode-go"})
                source = adapter.source_for_installation(PAIRED_INSTALLATION)
                key = runner._session_key_for_source(source)
                selected = runner._apply_session_model_override(key, "old", {"provider": "google"})
                saved = sessions.get_model_override(key)
                return response, selected, saved
            finally:
                await stop(adapter)

    (status, payload, _), (actual_model, runtime), saved = run(scenario())
    assert status == 200, payload
    assert payload["model"] == actual_model == saved["model"] == "mimo-v2.6-flash"
    assert payload["provider"] == runtime["provider"] == saved["provider"] == "opencode-go"


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
