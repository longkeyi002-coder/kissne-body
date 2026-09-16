"""KB1-MOBILE-ADAPTER / regression — enablement scoping + plugin-handler wiring.

Two defects this file pins down (both found by CI, not by the plugin's own directory):

1. **Enablement leak.** ``kissne_mobile`` has no external credential, so the platform enablement probe
   (``gateway/config_env.py::_plugin_is_configured``) is the only gate. That probe calls
   ``entry.is_connected(PlatformConfig(enabled=True, extra=<real extra>))`` — ``enabled`` is FORGED, the
   question is "if the user enabled it, is it configured?". Reading ``config.enabled`` back therefore
   reports "configured" in EVERY profile, the listener is auto-enabled gateway-wide, and unrelated
   adapters/tests see an extra platform (Discord-only profiles grew a ``kissne_mobile`` adapter).
   The real opt-in is per-profile: ``KISSNE_MOBILE_ENABLED`` in that profile's own env, or
   ``platforms.kissne_mobile.enabled: true`` in that profile's own ``config.yaml`` (bridged into
   ``extra`` — where ``_is_connected`` looks).

2. **Plugin-handler wiring.** Every connectable adapter must call ``_wire_plugin_handlers`` from
   ``connect()`` so ``ctx.register_platform_handler`` factories run; for an aiohttp platform the native
   client is the ``web.Application`` and the wiring must happen BEFORE ``AppRunner.setup()`` freezes the
   router (same lifecycle point as ``plugins/platforms/line/adapter.py``).
"""

import asyncio
import importlib

MODULE_NAME = "plugins.platforms.kissne_mobile.adapter"
PLATFORM = "kissne_mobile"
OPT_IN_ENV = "KISSNE_MOBILE_ENABLED"


def _module():
    return importlib.import_module(MODULE_NAME)


# ── 1. The enablement probe must not be fooled by the forged ``enabled`` ────────────────────────────

def test_is_connected_ignores_the_forged_enablement_probe():
    """Exactly the object ``_plugin_is_configured`` builds: ``enabled=True``, real ``extra`` = {}."""
    from gateway.config import PlatformConfig

    module = _module()
    probe = PlatformConfig(enabled=True, extra={})
    assert module._is_connected(probe) is False, (
        "is_connected() must not read PlatformConfig.enabled: the enablement probe forges it to True, "
        "so echoing it enables this platform in every profile on the box"
    )
    assert module._is_connected(PlatformConfig(enabled=True, extra={"enabled": True})) is True
    assert module._is_connected(PlatformConfig(enabled=False, extra={"enabled": True})) is True, (
        "a real opt-in stays 'connected' even though the probe/status view passes enabled=False"
    )


def test_env_enablement_follows_this_profiles_flag(monkeypatch):
    module = _module()
    monkeypatch.delenv(OPT_IN_ENV, raising=False)
    assert module._env_enablement() is None, "no opt-in flag → no seed → platform stays disabled"
    monkeypatch.setenv(OPT_IN_ENV, "1")
    assert module._env_enablement() == {"enabled": True}


def test_yaml_bridge_seeds_extra_only_for_an_explicit_enable():
    module = _module()
    assert module._apply_yaml_config({}, {"enabled": True}) == {"enabled": True}
    assert module._apply_yaml_config({}, {"enabled": False}) == {}, (
        "an explicit disable must not seed the opt-in (the loader's _enabled_explicit marker rules)"
    )
    assert module._apply_yaml_config({}, {}) == {}
    assert module._apply_yaml_config({}, {"host": "127.0.0.1"}) == {}


# ── 2. Profile isolation, driven through the real config loader ────────────────────────────────────

def _write_profile(home, name, config_yaml):
    profile = home / "profiles" / name
    profile.mkdir(parents=True, exist_ok=True)
    (profile / "config.yaml").write_text(config_yaml, encoding="utf-8")
    return profile


def _in_profile_scope(profile_home, fn):
    """Load that profile's config and answer ``fn(cfg)`` INSIDE its runtime scope.

    Plugin registrations are scope-keyed, so ``get_connected_platforms()`` only sees this plugin while
    the profile's own scope is active — which is exactly the isolation we want to pin down.
    """
    from hermes_cli.plugins import discover_plugins
    from gateway.config import load_gateway_config
    from gateway.run import _profile_runtime_scope

    discover_plugins()  # idempotent: registers this plugin so the enablement pass can see it
    with _profile_runtime_scope(profile_home, hydrate_secrets=False):
        return fn(load_gateway_config())


def _enabled_and_connected(cfg):
    from gateway.config import Platform
    listed = {p.value for p in cfg.get_connected_platforms()}
    mobile = cfg.platforms.get(Platform(PLATFORM))
    return (mobile is not None and mobile.enabled), PLATFORM in listed


_DISCORD_ONLY = "model: {default: test}\nplatforms:\n  discord:\n    enabled: true\n    token: discord-test\n"
_DISCORD_PLUS_MOBILE = _DISCORD_ONLY + "  kissne_mobile:\n    enabled: true\n"


def test_discord_only_profile_never_enlists_the_mobile_listener(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv(OPT_IN_ENV, raising=False)
    profile = _write_profile(home, "worker", _DISCORD_ONLY)

    enabled, connected = _in_profile_scope(profile, _enabled_and_connected)

    assert enabled is False, (
        "a profile that never opted in must not get the Mobile listener (CI saw it connect anyway)"
    )
    assert connected is False


def test_only_the_profile_that_opts_in_gets_the_mobile_listener(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv(OPT_IN_ENV, raising=False)
    opted_in = _write_profile(home, "phone", _DISCORD_PLUS_MOBILE)
    untouched = _write_profile(home, "worker", _DISCORD_ONLY)

    assert _in_profile_scope(opted_in, _enabled_and_connected) == (True, True)
    assert _in_profile_scope(untouched, _enabled_and_connected)[0] is False, (
        "profile opt-in must never leak into another profile"
    )


# ── 3. Plugin-handler wiring happens in connect(), before the router freezes ───────────────────────

def test_connect_wires_plugin_handlers_with_the_aiohttp_app(monkeypatch):
    module = _module()
    from gateway.config import Platform, PlatformConfig

    wired = []

    class _Manager:
        def get_platform_handler_factories(self, name):
            assert name == PLATFORM, f"factories are looked up per platform, got {name!r}"

            def factory(native, adapter):
                # Raises if the router was already frozen by AppRunner.setup() — that is the
                # lifecycle contract (plugins/platforms/line/adapter.py wires for the same reason).
                native.router.add_get("/plugin-probe", lambda _request: None)
                wired.append((native, adapter))

            return [(factory, "unit-test-plugin")]

    monkeypatch.setattr("hermes_cli.plugins.get_plugin_manager", lambda: _Manager())
    monkeypatch.setattr(module, "check_kissne_mobile_requirements", lambda: True)

    adapter = module.KissneMobileAdapter(
        PlatformConfig(enabled=True, extra={"enabled": True}), Platform(PLATFORM)
    )

    async def _run():
        try:
            assert await adapter.connect() is True
        finally:
            await adapter.disconnect()

    asyncio.run(_run())

    assert len(wired) == 1, "connect() must invoke ctx.register_platform_handler factories exactly once"
    from aiohttp import web
    assert isinstance(wired[0][0], web.Application), (
        "the aiohttp application is this platform's native client — factories receive it, not None"
    )
    assert wired[0][1] is adapter
