from _transport_harness import http, isolated_runtime, make_adapter, pair, run, start, stop


def _enable_lifemem(monkeypatch):
    import hermes_cli.config as config
    monkeypatch.setattr(config, "load_config_readonly", lambda: {})
    monkeypatch.setattr(
        config, "cfg_get",
        lambda _cfg, *_path, default=None: "lifemem"
        if tuple(_path) == ("memory", "provider") else default,
    )


def _seed(home):
    from plugins.memory.lifemem.store import MemoryStore

    db = home / "kissne-lifemem" / "memory.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    store = MemoryStore(str(db))
    try:
        store.add_memory(
            "喜欢蓝色狐狸", "用户明确说喜欢蓝色狐狸",
            memory_space="relationship", emotion="开心",
            confirmed=True, session_id="session-a", turn_id=7, event_time=300,
        )
        store.add_memory(
            "小机星房间", "小机星使用扁平绘本场景",
            memory_space="ai_world", emotion="平静",
            session_id="session-b", turn_id=9, event_time=200,
        )
        store.add_memory(
            "现实安排", "明天下午处理现实中的安排",
            memory_space="reality", event_time=100,
        )
    finally:
        store.close()


def test_memory_timeline_requires_device_auth(tmp_path, monkeypatch):
    async def scenario():
        with isolated_runtime(tmp_path):
            _enable_lifemem(monkeypatch)
            adapter = make_adapter()
            port = await start(adapter)
            try:
                return await http(port, "GET", "/memory/timeline")
            finally:
                await stop(adapter)

    status, payload, _ = run(scenario())
    assert status == 401
    assert payload.get("error") == "unauthorized"


def test_memory_timeline_rejects_when_lifemem_is_not_active(tmp_path, monkeypatch):
    async def scenario():
        with isolated_runtime(tmp_path):
            import hermes_cli.config as config
            monkeypatch.setattr(config, "load_config_readonly", lambda: {})
            monkeypatch.setattr(config, "cfg_get", lambda *_args, **_kwargs: "builtin")
            adapter = make_adapter()
            port = await start(adapter)
            try:
                token = await pair(port, adapter)
                return await http(port, "GET", "/memory/timeline", token=token)
            finally:
                await stop(adapter)

    status, payload, _ = run(scenario())
    assert status == 503
    assert payload.get("error") == "lifemem_not_active"


def test_memory_timeline_empty_store_is_a_valid_empty_page(tmp_path, monkeypatch):
    async def scenario():
        with isolated_runtime(tmp_path):
            _enable_lifemem(monkeypatch)
            adapter = make_adapter()
            port = await start(adapter)
            try:
                token = await pair(port, adapter)
                return await http(port, "GET", "/memory/timeline", token=token)
            finally:
                await stop(adapter)

    status, payload, _ = run(scenario())
    assert status == 200
    assert payload == {"ok": True, "items": [], "has_more": False, "next_before": None}


def test_memory_timeline_returns_real_lifemem_rows_and_filters(tmp_path, monkeypatch):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            _enable_lifemem(monkeypatch)
            _seed(home)
            adapter = make_adapter()
            port = await start(adapter)
            try:
                token = await pair(port, adapter)
                all_rows = await http(port, "GET", "/memory/timeline?limit=10", token=token)
                filtered = await http(
                    port, "GET", "/memory/timeline?space=relationship&q=%E8%93%9D%E8%89%B2",
                    token=token,
                )
                return all_rows, filtered
            finally:
                await stop(adapter)

    (status, payload, _), (filter_status, filtered, _) = run(scenario())
    assert status == 200
    assert [item["title"] for item in payload["items"]] == ["喜欢蓝色狐狸", "小机星房间", "现实安排"]
    first = payload["items"][0]
    assert first["memory_space"] == "relationship"
    assert first["confirmed"] is True
    assert first["source_ref"] == {"session_id": "session-a", "turn_id": 7}
    assert filter_status == 200
    assert [item["title"] for item in filtered["items"]] == ["喜欢蓝色狐狸"]


def test_memory_timeline_composite_cursor_pages_without_duplicates(tmp_path, monkeypatch):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            _enable_lifemem(monkeypatch)
            _seed(home)
            adapter = make_adapter()
            port = await start(adapter)
            try:
                token = await pair(port, adapter)
                first = await http(port, "GET", "/memory/timeline?limit=2", token=token)
                cursor = first[1].get("next_before")
                second = await http(
                    port, "GET", "/memory/timeline?limit=2&before=" + str(cursor),
                    token=token,
                )
                return first, second
            finally:
                await stop(adapter)

    (first_status, first, _), (second_status, second, _) = run(scenario())
    assert first_status == second_status == 200
    assert first["has_more"] is True
    assert "|" in first["next_before"]
    first_ids = {item["id"] for item in first["items"]}
    second_ids = {item["id"] for item in second["items"]}
    assert first_ids.isdisjoint(second_ids)
    assert [item["title"] for item in second["items"]] == ["现实安排"]


def test_memory_timeline_rejects_invalid_space_and_cursor(tmp_path, monkeypatch):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            _enable_lifemem(monkeypatch)
            _seed(home)
            adapter = make_adapter()
            port = await start(adapter)
            try:
                token = await pair(port, adapter)
                bad_space = await http(
                    port, "GET", "/memory/timeline?space=not-a-space", token=token)
                bad_cursor = await http(
                    port, "GET", "/memory/timeline?before=broken%7Ccursor", token=token)
                return bad_space, bad_cursor
            finally:
                await stop(adapter)

    (space_status, space_payload, _), (cursor_status, cursor_payload, _) = run(scenario())
    assert space_status == 400
    assert space_payload.get("error") == "invalid_memory_space"
    assert cursor_status == 400
    assert cursor_payload.get("error") == "invalid_memory_query"
