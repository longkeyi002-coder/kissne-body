"""Use Hermes' existing platform picker persistence; never reset permissions on boot."""
from contextlib import nullcontext
from threading import RLock

_LOCK = RLock()


def platform_toolsets(profile='', change=None):
    from hermes_cli.config import load_config_readonly
    from hermes_cli.tools_config import _get_platform_tools, _save_platform_tools, _configurable_keys
    scope = nullcontext()
    if profile:
        from hermes_cli.web_server_profiles import _config_profile_scope
        scope = _config_profile_scope(profile)
    with _LOCK, scope:
        config = load_config_readonly()
        offered = _configurable_keys()
        enabled = _get_platform_tools(config, 'kissne_mobile')
        if change is not None:
            key = change.get('toolset')
            value = change.get('enabled')
            if key not in offered or not isinstance(value, bool):
                raise ValueError('invalid_toolset_change')
            if value:
                enabled.add(key)
            else:
                enabled.discard(key)
            _save_platform_tools(config, 'kissne_mobile', enabled)
            enabled = _get_platform_tools(config, 'kissne_mobile')
        return {'ok': True, 'toolsets': [{'key': key, 'enabled': key in enabled} for key in sorted(offered)],
                'applies': 'next_agent', 'notice': '设置已持久保存，下一次新对话或 agent 重建时生效。'}
