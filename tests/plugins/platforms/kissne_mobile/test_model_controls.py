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

    monkeypatch.setattr(inventory, "load_picker_context", lambda: Ctx())
    monkeypatch.setattr(
        inventory,
        "build_model_options_payload",
        lambda _ctx, **_kw: {
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
