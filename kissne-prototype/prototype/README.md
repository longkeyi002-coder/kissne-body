# Kissne Mobile UI

This directory contains the packaged UI used by the Android app. It began as a
low-fidelity prototype, but the Android build now ships these files directly,
so runtime behavior here must be treated as production app behavior rather than
demo behavior.

## File map

- `index.html` — asset entry point.
- `core.js` — shared rendering helpers, icons, reusable UI components.
- `assets.js` — packaged character/sticker asset mapping.
- `transport.js` — browser/native transport facade.
- `screens-a.js` — Home, Chat, AI World, call/share, stickers.
- `screens-b.js` — Memory, device/admin, sessions, settings, notifications.
- `app.js` — hash router, splash lifecycle, screen mount/unmount, shared
  session-index refresh.
- `styles.css` — responsive/mobile-native styling.
- `splash/` and `assets/` — packaged visual assets.

## Runtime rules

### Connection state

Home must not bootstrap on every mount.

- Android exposes a per-process bootstrap cache.
- Home reads `hasBootstrapCache()` first and immediately renders Online when
  available.
- Normal page navigation reuses cached bootstrap.
- Manual refresh forces a real bootstrap.
- 401 invalidates token/bootstrap state, obtains a fresh token, then performs a
  real bootstrap.
- Session switching invalidates the previous bootstrap before the selected
  conversation is loaded.

### Chat rendering

Assistant output is divided into separate presentation layers:

- final model text → assistant message body;
- tool/runtime progress → collapsible activity area;
- hidden/internal/reasoning-only events → not rendered as assistant prose;
- a "思考" section may exist only when a real thought/reasoning activity event
  exists.

Terminal commands, `Working — ...`, provider-wait messages, iteration counts,
and similar execution telemetry must never be mixed into the final assistant
body.

On Android, assistant text/activity width is deliberately narrower than the
full row so content stops before the opposite-side avatar region. Long tool
commands wrap instead of overflowing horizontally.

### Sessions

The sessions page uses the real Mobile admin session endpoint. Rows carry the
stable Hermes `session_id`; selecting a row switches the active conversation
instead of merely changing local UI state.

### Memory

The memory page has no sample/demo memories. It reads real curated
`MEMORY.md` / `USER.md` entries through the Mobile admin endpoint and
performs real deletion through the corresponding delete endpoint.

### Models and reasoning effort

Values come from Hermes. The UI accepts either string arrays or object-shaped
options so it remains compatible with the current dashboard-style inventory
payload.

## Native vs browser mode

When `?native=1` is present, the app hides the prototype workbench chrome and
uses the Android viewport directly. Browser mode remains useful for visual
inspection, but fake runtime data must not be introduced into native mode.
