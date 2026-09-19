# Kissne Android Chat

Clean Android-only rebuild for KB1-ANDROID-CHAT. This project consumes the
existing `/pair`, `/bootstrap`, `/messages`, and `/cancel` Mobile Adapter
contracts. It does not modify the Adapter or add conversation logic.

Pairing requires only `pairing_code` and `installation_id`; the app never
asks the user for a Conversation `session_key`. On cold start, the adapter's
token-authenticated `/bootstrap` response identifies the already-bound
Conversation. An unbound installation is shown as a recoverable state instead
of creating a local or mobile-only conversation.

The device token is stored through Android Keystore-backed
`EncryptedSharedPreferences`. Bootstrap sends the persisted cursor and
acknowledges only server-proven `covered_event_seqs`; it never deduplicates by
text or timestamp. The production adapter URL is injected as
`BuildConfig.MOBILE_BASE_URL` from the Soul §0.3.16 HTTPS entrypoint.
