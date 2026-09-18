# Kissne Android Chat

Clean Android-only rebuild for KB1-ANDROID-CHAT. This project consumes the
existing `/pair`, `/bootstrap`, `/messages`, and `/cancel` Mobile Adapter
contracts. It does not modify the Adapter or add conversation logic.

Pairing requires `pairing_code`, `installation_id`, and the selected
`session_key`. The device token is stored through Android Keystore-backed
`EncryptedSharedPreferences`. Bootstrap sends the persisted cursor and
acknowledges only server-proven `covered_event_seqs`; it never deduplicates by
text or timestamp.
