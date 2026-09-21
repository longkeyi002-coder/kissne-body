# Kissne Android

Kissne Android is a thin native shell around the packaged mobile UI in
`kissne-prototype/prototype/`.

The native layer owns credentials, HTTP transport, update checks, WebView
security boundaries, Android system integration, and the per-process bootstrap
cache. The WebView owns presentation and user interaction.

## Runtime structure

- `MainActivity.kt` — creates the secured WebView, applies Android 15/16
  edge-to-edge insets, loads packaged assets, and wires the update manager.
- `PrototypeBridge.kt` — asynchronous JS/native bridge. Interactive chat,
  background reads, and control-plane work use separate executors so a slow
  poll/model request cannot block Send.
- `MobileTransportClient.kt` — HTTP client for the Mobile Adapter.
- `MobileSessionStore.kt` — Keystore-backed
  `EncryptedSharedPreferences` for installation id, device token, cursor,
  server base URL, and cached session metadata.
- `BridgeScheduling.kt` — bridge lane policy.
- `UpdateManager.kt` — release update discovery/download/install handoff.

There is no second native chat UI. The current product UI is the packaged
WebView UI only.

## Authentication and connection lifecycle

The app uses installation-only auto-pairing. There is no user-facing pairing
code or API-key form.

1. A stable `installation_id` is created once and persisted.
2. `POST /mobile/pair` returns a device token.
3. The token is kept only in the native encrypted store; JavaScript never
   receives the plaintext credential.
4. A successful `/mobile/bootstrap` with `bound=true` is cached for the
   lifetime of the Android process.
5. Navigating back to Home or Chat reuses that cache and does not flash
   "connecting" or issue another bootstrap request.
6. App process restart, explicit refresh, session switch, token rotation, or a
   real 401 invalidates the cache and triggers a fresh bootstrap.

The persisted bootstrap metadata contains only the active session id/key and
connection marker. The full bootstrap payload is intentionally memory-only, so
an actual app restart verifies the server again.

## Mobile API surface

Current app paths include:

- `/pair`
- `/bootstrap`
- `/messages`
- `/cancel`
- `/approval`
- `/model-options`
- `/set-model`
- `/admin/sessions`
- `/admin/memory`
- selected admin/status routes used by the app

## WebView security

- UI is served through `WebViewAssetLoader` at
  `https://appassets.androidplatform.net`.
- Arbitrary external navigation is blocked.
- File/content access is disabled.
- Mixed content is disabled.
- The device token stays native-side.

## Build and signing

Debug builds use the repository's dedicated stable **debug-only** key so debug
APKs can upgrade each other without signature conflicts. That key is not the
production release identity.

Release signing uses GitHub Actions secrets:

- `KISSNE_ANDROID_KEYSTORE_B64`
- `KISSNE_ANDROID_STORE_PASSWORD`
- `KISSNE_ANDROID_KEY_ALIAS`
- `KISSNE_ANDROID_KEY_PASSWORD`

On `kissne-main`, the Android workflow can publish/refresh
`kissne-android-latest` when release signing is configured. Release builds
check that channel after startup and hand APK installation to Android's package
installer.
