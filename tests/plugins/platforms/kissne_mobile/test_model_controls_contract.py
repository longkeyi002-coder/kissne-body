"""Mobile model/reasoning controls must be authenticated and use Hermes' canonical sources."""

from unittest.mock import AsyncMock, patch

from _transport_harness import http, isolated_runtime, make_adapter, pair, run, start, stop


def test_model_options_requires_device_auth(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path):
            adapter = make_adapter()
            port = await start(adapter)
            try:
                status, payload, _ = await http(port, "GET", "/model-options")
                assert status == 401
                assert payload["error"] == "unauthorized"
            finally:
                await stop(adapter)
    run(scenario())


def test_model_options_uses_canonical_reasoning_ladder(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path):
            adapter = make_adapter()
            port = await start(adapter)
            try:
                token = await pair(port, adapter)
                fake = [{"slug": "deepseek", "models": ["deepseek-v4.1-flash"]}]
                with patch("hermes_cli.model_switch.list_authenticated_providers", return_value=fake):
                    status, payload, _ = await http(port, "GET", "/model-options", token=token)
                assert status == 200
                assert payload["models"] == [{
                    "provider": "deepseek", "model": "deepseek-v4.1-flash",
                    "label": "deepseek-v4.1-flash",
                }]
                assert [item["value"] for item in payload["efforts"]] == [
                    "none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"
                ]
                assert payload["efforts"][0]["label"] == "关闭思考"
                assert next(x for x in payload["efforts"] if x["value"] == "xhigh")["label"] == "Extra High"
            finally:
                await stop(adapter)
    run(scenario())


def test_set_model_rejects_invalid_effort_before_gateway_control(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path):
            adapter = make_adapter()
            port = await start(adapter)
            try:
                token = await pair(port, adapter)
                status, payload, _ = await http(
                    port, "POST", "/set-model", token=token,
                    body={"model": "deepseek/deepseek-v4.1-flash", "effort": "impossible"},
                )
                assert status == 400
                assert payload["error"] == "invalid_reasoning_effort"
            finally:
                await stop(adapter)
    run(scenario())


def test_set_model_delegates_to_gateway_model_command(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path):
            adapter = make_adapter()
            port = await start(adapter)
            try:
                token = await pair(port, adapter)
                adapter._handle_model_command = AsyncMock(return_value="switched")
                status, payload, _ = await http(
                    port, "POST", "/set-model", token=token,
                    body={"model": "deepseek/deepseek-v4.1-flash", "effort": "high"},
                )
                assert status == 200
                assert payload["ok"] is True
                event = adapter._handle_model_command.await_args.args[0]
                assert event.text == "/model deepseek/deepseek-v4.1-flash --reasoning high"
                assert event.allow_gateway_control is True
            finally:
                await stop(adapter)
    run(scenario())
