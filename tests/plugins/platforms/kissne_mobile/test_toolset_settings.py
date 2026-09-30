"""Persistent real picker configuration, authenticated HTTP, isolated homes A→B→A."""
from pathlib import Path
import yaml
from _transport_harness import build_session_store, http, isolated_runtime, make_adapter, pair, preexisting_conversation, run, start, stop


def test_tool_permissions_survive_reopen_without_boot_writes_or_profile_leaks(tmp_path):
    async def visit(folder, enable=False):
        with isolated_runtime(folder) as home:
            path = Path(home) / 'config.yaml'
            if not path.exists():
                path.write_text(yaml.safe_dump({'platform_toolsets':{'kissne_mobile':['terminal'],'telegram':['terminal']},'agent':{'disabled_toolsets':['browser','cronjob']}}))
            adapter = make_adapter(); sessions = build_session_store(home)
            conversation = preexisting_conversation(sessions); adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                original = path.read_bytes()
                status, result, _ = await http(port, 'GET', '/toolsets', token=token)
                assert status == 200, result
                assert path.read_bytes() == original
                enabled = {row['key'] for row in result['toolsets'] if row['enabled']}
                if enable:
                    status, result, _ = await http(port, 'POST', '/toolsets', token=token, body={'toolset':'browser','enabled':True})
                    assert status == 200, result
                    saved = yaml.safe_load(path.read_text())
                    assert 'browser' not in saved['agent']['disabled_toolsets']
                    assert 'cronjob' in saved['agent']['disabled_toolsets']
                    assert saved['platform_toolsets']['telegram'] == ['terminal']
                    enabled = {row['key'] for row in result['toolsets'] if row['enabled']}
                status, _, _ = await http(port, 'POST', '/toolsets', body={'toolset':'browser','enabled':True})
                assert status == 401
                status, _, _ = await http(port, 'POST', '/toolsets', token=token, body={'toolset':'does_not_exist','enabled':True})
                assert status == 400
                return enabled
            finally:
                await stop(adapter)
    async def scenario():
        assert 'browser' in await visit(tmp_path/'a', True)
        assert 'browser' not in await visit(tmp_path/'b')
        assert 'browser' in await visit(tmp_path/'a')
    run(scenario())
