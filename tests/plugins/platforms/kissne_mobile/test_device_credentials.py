"""KB1-MOBILE-ADAPTER / RED — device credential layer of ``plugins/platforms/kissne_mobile/``.

Contract frozen here (module ``plugins.platforms.kissne_mobile.device_store``):

* ``DeviceStore()`` — persistent device registry on the plugin's OWN storage layer
  (``plugins/plugin_storage.py::plugin_db("kissne_mobile")`` → ``<HERMES_HOME>/plugin-data/kissne_mobile/``);
  the no-arg constructor must be replayable so a "restart" is ``DeviceStore()`` again.
* ``issue_pairing_code(ttl_seconds: float = 300) -> str``   — one-time registration secret.
* ``redeem_pairing_code(code, installation_id) -> str``      — returns the PLAINTEXT device token
  once; raises ``PairingCodeInvalid`` / ``PairingCodeExpired`` / ``PairingCodeReplayed``
  (all ``PairingError`` subclasses) otherwise.
* ``authenticate(token) -> Optional[str]``                   — installation id, or None when the token
  is unknown OR revoked.
* ``revoke(token) -> bool``                                  — kills the token immediately.
* ``close()``                                                — release the handle (restart simulation).

Ticket constraints under test: single-use + short-lived + replay-rejected pairing codes; tokens
issuable and revocable; revocation survives a restart; only hash/derived values at rest (a raw-text
search over the plugin's SQLite files must not find the token); full token never logged.

RED reason: the plugin package does not exist yet — assertions fail explicitly, no ``importorskip``.
"""

import logging
from pathlib import Path

PLATFORM_NAME = "kissne_mobile"
MODULE = "plugins.platforms.kissne_mobile.device_store"


def _device_store_class():
    import importlib
    try:
        module = importlib.import_module(MODULE)
    except Exception as exc:
        return None, f"cannot import {MODULE}: {exc!r}", None
    cls = getattr(module, "DeviceStore", None)
    if cls is None:
        return None, f"{MODULE} must export DeviceStore", module
    return cls, None, module


def _new_store():
    cls, error, module = _device_store_class()
    assert cls is not None, f"kb1-mobile-adapter: {error}"
    return cls(), module


def _plugin_data_files():
    """Every file the plugin parked under ``<HERMES_HOME>/plugin-data/kissne_mobile/``."""
    from plugins.plugin_storage import plugin_data_dir
    root = plugin_data_dir(PLATFORM_NAME)
    return [p for p in Path(root).rglob("*") if p.is_file()]


def test_pairing_code_is_single_use_and_rejects_replay():
    store, module = _new_store()
    code = store.issue_pairing_code(ttl_seconds=300)
    assert isinstance(code, str) and code.strip(), "issue_pairing_code() must return a non-empty string"
    token = store.redeem_pairing_code(code, installation_id="inst-1")
    assert isinstance(token, str) and token.strip(), "redeem must return the plaintext device token"
    replay_error = getattr(module, "PairingCodeReplayed", None)
    assert replay_error is not None, f"{MODULE} must export PairingCodeReplayed"
    try:
        store.redeem_pairing_code(code, installation_id="inst-2")
    except replay_error:
        pass
    else:
        raise AssertionError("a redeemed pairing code was accepted a second time (replay not rejected)")
    store.close()


def test_pairing_code_expires():
    store, module = _new_store()
    expired_error = getattr(module, "PairingCodeExpired", None)
    assert expired_error is not None, f"{MODULE} must export PairingCodeExpired"
    code = store.issue_pairing_code(ttl_seconds=0.05)
    import time
    time.sleep(0.15)
    try:
        store.redeem_pairing_code(code, installation_id="inst-1")
    except expired_error:
        pass
    else:
        raise AssertionError("an expired pairing code was accepted (short-lived validity not enforced)")
    store.close()


def test_unknown_pairing_code_is_rejected():
    store, module = _new_store()
    invalid_error = getattr(module, "PairingCodeInvalid", None)
    assert invalid_error is not None, f"{MODULE} must export PairingCodeInvalid"
    try:
        store.redeem_pairing_code("not-a-real-code", installation_id="inst-1")
    except invalid_error:
        pass
    else:
        raise AssertionError("an unknown pairing code was accepted")
    store.close()


def test_token_is_revocable_and_revocation_is_immediate():
    store, _module = _new_store()
    token = store.redeem_pairing_code(store.issue_pairing_code(), installation_id="inst-1")
    assert store.authenticate(token) == "inst-1", "a freshly issued token must authenticate"
    assert store.revoke(token) is True, "revoke(token) must report success for a live token"
    assert store.authenticate(token) is None, "a revoked token was still accepted"
    store.close()


def test_revocation_and_registration_survive_a_restart():
    store, _module = _new_store()
    revoked = store.redeem_pairing_code(store.issue_pairing_code(), installation_id="inst-revoked")
    live = store.redeem_pairing_code(store.issue_pairing_code(), installation_id="inst-live")
    store.revoke(revoked)
    store.close()

    reopened, _module = _new_store()  # restart: brand new store object over the same HERMES_HOME
    assert reopened.authenticate(revoked) is None, (
        "revocation did not survive the restart — device store state must be persistent")
    assert reopened.authenticate(live) == "inst-live", (
        "a registered device did not survive the restart")
    reopened.close()


def test_plaintext_token_never_hits_disk():
    store, _module = _new_store()
    token = store.redeem_pairing_code(store.issue_pairing_code(), installation_id="inst-1")
    store.close()
    needle = token.encode("utf-8")
    files = _plugin_data_files()
    assert files, "the device store wrote nothing under <HERMES_HOME>/plugin-data/kissne_mobile/"
    offenders = [str(p) for p in files if needle in p.read_bytes()]
    assert not offenders, (
        f"plaintext device token is at rest in {offenders} — only a hash/derived value may be stored")


def test_full_token_is_never_logged(caplog):
    caplog.set_level(logging.DEBUG)
    store, _module = _new_store()
    token = store.redeem_pairing_code(store.issue_pairing_code(), installation_id="inst-1")
    store.authenticate(token)
    store.revoke(token)
    store.close()

    plugin_records = [r for r in caplog.records if r.name.startswith(MODULE) or PLATFORM_NAME in r.name]
    assert plugin_records, "the device store emitted no log records — logging must be reviewable"
    leaking = [r.getMessage() for r in plugin_records if token in str(r.getMessage())]
    assert not leaking, f"the full device token appears in log output: {leaking}"


def test_admin_scope_is_separate_from_auto_pair_device_scope():
    store, _module = _new_store()
    device = store.create_device_token("inst-scope")
    admin = store.redeem_pairing_code(
        store.issue_pairing_code(), installation_id="inst-scope", scope="admin"
    )

    assert store.authenticate(device) == "inst-scope"
    assert store.authenticate(device, required_scope="admin") is None
    assert store.authenticate(admin) == "inst-scope"
    assert store.authenticate(admin, required_scope="admin") == "inst-scope"
    store.close()
