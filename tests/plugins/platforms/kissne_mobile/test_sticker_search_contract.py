"""KB1-STICKER-INDEX / GREEN — ``kissne_sticker_search`` over the app-pushed sticker index.

Contract frozen here:

* ``POST /sticker-index`` is the authoritative index push: paired device token only (401
  otherwise), replaces the whole index, answers ``{"ok": true, "count": N}``.
  Malformed payloads fail closed with 400 and a named reason.
* Inbound ``[表情包：X]`` markers are observed into the same index so the tool works
  before the app ships the push; observation must never break message ingestion.
* ``kissne_sticker_search`` registers under ``toolset="kissne_mobile"`` with a ``check_fn``
  that hides it while the index is empty (zero schema tokens before first use).
* The gate confines the toolset to kissne_mobile sessions: default-off + platform
  restriction, so weixin/cron/api/cli pay nothing for it.
* The manifest declares ``provides_tools`` so the deferred (CLI/TUI) loader finds tools.py.
"""

from _transport_harness import (
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

from hermes_cli.toolset_scope import toolset_allowed_for_platform
from hermes_cli.tools_config import _DEFAULT_OFF_TOOLSETS
from plugins.platforms.kissne_mobile.tools import (
    _search_sticker,
    _sticker_index_available,
    load_sticker_index,
    register_tools,
    write_sticker_index,
)

PUSHED = ["开心", "疑惑", "叶青栩 · 疑惑"]


def test_push_requires_a_paired_device_token(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path):
            adapter = make_adapter()
            store = build_session_store(tmp_path)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                status, payload, _ = await http(
                    port, "POST", "/sticker-index", body={"keywords": PUSHED})
            finally:
                await stop(adapter)
        return status, payload

    status, payload = run(scenario())
    assert status == 401, (
        "the sticker index is device state: pushing without a paired token must be 401, "
        f"got {status}: {payload}")


def test_push_replaces_the_index_and_answers_the_count(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                first_status, first_payload, _ = await http(
                    port, "POST", "/sticker-index", token=token, body={"keywords": PUSHED})
                second_status, second_payload, _ = await http(
                    port, "POST", "/sticker-index", token=token, body={"keywords": ["新表情"]})
                stored = load_sticker_index()
            finally:
                await stop(adapter)
        return first_status, first_payload, second_status, second_payload, stored

    first_status, first_payload, second_status, second_payload, stored = run(scenario())
    assert first_status == 200, f"a valid push must be 200, got {first_status}: {first_payload}"
    assert first_payload.get("ok") is True and first_payload.get("count") == len(PUSHED), (
        f"the push must answer ok + stored count, got {first_payload}")
    assert second_status == 200 and second_payload.get("count") == 1, (
        f"the second push must replace, not merge: {second_payload}")
    assert stored.get("keywords") == ["新表情"], (
        f"a push is an authoritative replace, the index must hold only the latest push: {stored}")


def test_malformed_pushes_fail_closed_with_named_reasons(tmp_path):
    bad_bodies = [
        ({}, "keywords_must_be_a_list"),
        ({"keywords": "nope"}, "keywords_must_be_a_list"),
        ({"keywords": [42]}, "keywords_must_be_strings"),
        ({"keywords": ["   "]}, "keyword_invalid"),
        ({"keywords": ["x" * 129]}, "keyword_invalid"),
        ({"keywords": ["k"] * 5001}, "too_many_keywords"),
    ]

    async def scenario():
        results = []
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                for body, _expected in bad_bodies:
                    status, payload, _ = await http(
                        port, "POST", "/sticker-index", token=token, body=body)
                    results.append((status, payload.get("error")))
                stored = load_sticker_index()
            finally:
                await stop(adapter)
        return results, stored

    results, stored = run(scenario())
    for (status, error), (_, expected) in zip(results, bad_bodies):
        assert status == 400, f"malformed push {expected!r} must be 400, got {status}"
        assert error == expected, f"the refusal must name its reason ({expected}), got {error!r}"
    assert not stored.get("keywords"), f"no malformed push may write the index: {stored}"


def test_inbound_marker_observation_lands_in_the_index(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                status, _, _ = await http(port, "POST", "/messages", token=token,
                                          body={"text": "看这个 [表情包：未收录词] 很像你",
                                                "message_id": "m-observe-1"})
                stored = load_sticker_index()
            finally:
                await stop(adapter)
        return status, stored

    status, stored = run(scenario())
    assert status == 202, f"the observation message must be accepted, got {status}"
    keywords = stored.get("keywords") or []
    assert "未收录词" in keywords, (
        f"an inbound [表情包：X] marker must be observed into the searchable index: {keywords}")


def test_tool_hides_until_index_exists_then_searches(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            empty_available = _sticker_index_available()
            empty_result = _search_sticker({"query": "开心"})
            from plugins.platforms.kissne_mobile import tools as tools_mod
            tools_mod.write_sticker_index(PUSHED + ["晚安小羊"])
            full_available = _sticker_index_available()
            hit = _search_sticker({"query": "疑惑"})
            miss = _search_sticker({"query": "完全不存在"})
            browse = _search_sticker({"query": ""})
        return empty_available, empty_result, full_available, hit, miss, browse

    empty_available, empty_result, full_available, hit, miss, browse = run(scenario())
    assert empty_available is False, "check_fn must hide the tool while the index is empty"
    assert empty_result.get("error") == "sticker_index_empty" and empty_result.get("hint"), (
        f"an empty index must refuse with a hint to reply as text: {empty_result}")
    assert full_available is True, "check_fn must surface the tool once an index exists"
    assert hit.get("ok") is True and "疑惑" in hit.get("matches", []), (
        f"search must return the matching keyword strings: {hit}")
    assert miss.get("ok") is True and not miss.get("matches"), (
        f"a query outside the library must return zero matches, not a guess: {miss}")
    assert browse.get("ok") is True and browse.get("library_size") == 4, (
        f"an empty query must browse the library size: {browse}")


def test_register_tools_pins_the_kissne_toolset():
    class _Ctx:
        def __init__(self):
            self.tools = []

        def register_tool(self, **kwargs):
            self.tools.append(kwargs)

    ctx = _Ctx()
    register_tools(ctx)
    assert len(ctx.tools) == 1, f"exactly one client tool must register, got {ctx.tools}"
    tool = ctx.tools[0]
    assert tool.get("name") == "kissne_sticker_search", f"tool name drifted: {tool.get('name')}"
    assert tool.get("toolset") == "kissne_mobile", (
        f"the tool must live in the kissne toolset (the gate keys off it): {tool.get('toolset')}")
    assert callable(tool.get("handler")) and callable(tool.get("check_fn")), (
        "the tool must ship a handler and a check_fn")
    assert str(tool.get("description") or "").strip(), "the tool must carry a description"


def test_gate_confines_the_toolset_to_kissne_sessions():
    assert "kissne_mobile" in _DEFAULT_OFF_TOOLSETS, (
        "the kissne toolset must be default-off (new installs pay nothing until a kissne "
        "session proves the need)")
    assert toolset_allowed_for_platform("kissne_mobile", "kissne_mobile") is True, (
        "kissne sessions must resolve their own toolset")
    for other in ("weixin", "cli", "api_server", "cron"):
        assert toolset_allowed_for_platform("kissne_mobile", other) is False, (
            f"{other} must not see the kissne sticker tool — it would spend tokens on a "
            "library it cannot render")


def test_manifest_declares_provides_tools():
    from hermes_cli.config import _platform_plugin_manifests

    manifest = dict(_platform_plugin_manifests()).get("kissne_mobile")
    assert manifest is not None, "the bundled loader must see the kissne_mobile plugin"
    assert "kissne_sticker_search" in (manifest.get("provides_tools") or []), (
        f"plugin.yaml must declare provides_tools so the deferred loader finds tools.py: "
        f"{manifest.get('provides_tools')}")


def test_handler_absorbs_dispatch_context_kwargs(tmp_path):
    """``model_tools.dispatch`` hands EVERY tool ``task_id``/``session_id``/``user_task``. A
    handler that accepts only the args dict dies before reading the query (live bug: the search
    errored on dispatch and the model got no answer at all)."""
    with isolated_runtime(tmp_path):
        write_sticker_index(PUSHED)
        result = _search_sticker(
            {"query": "疑惑"}, task_id="t-1", session_id="s-1", user_task="find a sticker")

    assert result.get("ok") is True, f"the query must still run: {result}"
    assert "疑惑" in (result.get("matches") or []), (
        f"the search must return matches despite the extra kwargs: {result}")
