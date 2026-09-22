"""KB1-MOBILE-ADAPTER / RED — bundled plugin contract for ``plugins/platforms/kissne_mobile/``.

Contract frozen here (what GREEN must deliver):

* ``plugins/platforms/kissne_mobile/plugin.yaml``  — ``kind: platform`` + ``name``/``label``.
* ``plugins/platforms/kissne_mobile/__init__.py``  — ``register(ctx)`` entry point that calls
  ``ctx.register_platform(name="kissne_mobile", ...)`` (the plugin contract documented in
  ``gateway/platforms/ADDING_A_PLATFORM.md``; ``register_platform`` lives at
  ``hermes_cli/plugins.py:781``).
* ``plugins/platforms/kissne_mobile/adapter.py``   — ``KissneMobileAdapter`` subclassing
  ``gateway/platforms/base.py::BasePlatformAdapter`` (abstract methods ``connect`` /
  ``disconnect`` / ``send`` / ``get_chat_info``, base.py:2452-2463, 4319-4322).

RED reason: the plugin directory does not exist yet. Every assertion below fails as an explicit
``AssertionError`` — no ``importorskip``, no collection-time ImportError.
"""

import importlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
PLUGIN_DIR = PROJECT_ROOT / "plugins" / "platforms" / "kissne_mobile"
PLATFORM_NAME = "kissne_mobile"


def _manifest():
    """Parse the plugin manifest with the repo's own loader helper, or return (None, error)."""
    yaml_path = PLUGIN_DIR / "plugin.yaml"
    if not yaml_path.is_file():
        return None, f"missing manifest: {yaml_path}"
    try:
        from hermes_cli.config import _platform_plugin_manifests
    except Exception as exc:  # pragma: no cover - loader always importable in this repo
        return None, f"cannot import the repo's bundled-manifest loader: {exc}"
    try:
        found = dict(_platform_plugin_manifests())
    except Exception as exc:  # pragma: no cover
        return None, f"bundled-manifest scan raised: {exc}"
    manifest = found.get(PLATFORM_NAME)
    if manifest is None:
        return None, f"existing loader does not see {PLATFORM_NAME}; saw {sorted(found)}"
    return manifest, None


def _adapter_module():
    try:
        return importlib.import_module("plugins.platforms.kissne_mobile.adapter"), None
    except Exception as exc:
        return None, f"cannot import plugins.platforms.kissne_mobile.adapter: {exc!r}"


def test_plugin_manifest_present_and_declares_a_platform():
    manifest, error = _manifest()
    assert manifest is not None, f"kb1-mobile-adapter: {error}"
    assert str(manifest.get("kind") or "").strip() == "platform", (
        f"plugin.yaml must declare kind: platform, got {manifest.get('kind')!r}")
    assert str(manifest.get("label") or manifest.get("name") or "").strip(), (
        "plugin.yaml must declare a non-empty label or name")


def test_bundled_loader_recognises_the_plugin_and_the_entry_point():
    """The repo's own plugin discovery must see the package and its ``register(ctx)`` entry."""
    manifest, error = _manifest()
    assert manifest is not None, f"kb1-mobile-adapter: {error}"
    assert (PLUGIN_DIR / "__init__.py").is_file(), f"missing plugin entry point: {PLUGIN_DIR / '__init__.py'}"
    try:
        pkg = importlib.import_module("plugins.platforms.kissne_mobile")
    except Exception as exc:
        raise AssertionError(f"cannot import the plugin package: {exc!r}") from exc
    register = getattr(pkg, "register", None)
    assert callable(register), "plugins/platforms/kissne_mobile/__init__.py must expose register(ctx)"
    assert (PLUGIN_DIR / "adapter.py").is_file(), "plugin must ship adapter.py next to plugin.yaml"


def test_platform_name_resolves_through_the_existing_pseudo_member_path():
    """``Platform("kissne_mobile")`` must work with NO enum edit (gateway/config.py:196-232)."""
    manifest, error = _manifest()
    assert manifest is not None, f"kb1-mobile-adapter: {error}"
    from gateway.config import Platform
    try:
        pseudo = Platform(PLATFORM_NAME)
    except Exception as exc:
        raise AssertionError(
            f"Platform({PLATFORM_NAME!r}) is not accepted by the dynamic _missing_ path: {exc!r}") from exc
    assert getattr(pseudo, "value", None) == PLATFORM_NAME, f"unexpected platform value: {pseudo!r}"


def test_adapter_class_implements_the_base_platform_contract():
    module, error = _adapter_module()
    assert module is not None, f"kb1-mobile-adapter: {error}"
    from gateway.platforms.base import BasePlatformAdapter
    adapter_cls = getattr(module, "KissneMobileAdapter", None)
    assert adapter_cls is not None, "adapter.py must export KissneMobileAdapter"
    assert isinstance(adapter_cls, type) and issubclass(adapter_cls, BasePlatformAdapter), (
        "KissneMobileAdapter must inherit gateway/platforms/base.py::BasePlatformAdapter")
    for method in ("connect", "disconnect", "send"):
        assert method in vars(adapter_cls), f"KissneMobileAdapter must override {method}()"
    assert not adapter_cls.__abstractmethods__, (
        f"adapter is still abstract: {sorted(adapter_cls.__abstractmethods__)}")
    assert callable(getattr(module, "create_adapter", None)) or callable(
        getattr(adapter_cls, "__init__", None)), "adapter must be constructible for registration"


def test_mobile_chat_prefers_fifo_followups_without_busy_ack_bubbles():
    """Rapid human-style messages stay distinct and never interrupt the answer already in progress."""
    module, error = _adapter_module()
    assert module is not None, f"kb1-mobile-adapter: {error}"
    adapter_cls = module.KissneMobileAdapter
    assert adapter_cls.preferred_busy_input_mode == "queue"
    assert adapter_cls.preferred_busy_text_mode == "interrupt"
    assert adapter_cls.busy_ack_enabled is False
