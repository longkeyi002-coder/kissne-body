# Kissne Android

Android shell for the current Kissne mobile prototype. The UI is packaged from
`kissne-prototype/prototype/`; networking and credentials stay in the native
Android layer.

The app consumes the existing Mobile Adapter contracts:

- `/pair`
- `/bootstrap`
- `/messages`
- `/cancel`

The device token is stored with Android Keystore-backed
`EncryptedSharedPreferences`. The WebView never receives the real token and is
confined to `appassets.androidplatform.net`.

## Connection state

A device token and an actually usable conversation are separate states. After
pairing, the native layer marks the connection ready only after
`/bootstrap` returns `bound=true`. A temporarily unbound conversation no
longer causes the UI to bounce repeatedly back to the connection page.

## Stable signing and updates

User-facing APKs must use one stable release key. Do **not** commit a keystore
or private key to this repository.

Configure these GitHub Actions secrets once:

- `KISSNE_ANDROID_KEYSTORE_B64` — base64 of the release keystore
- `KISSNE_ANDROID_STORE_PASSWORD`
- `KISSNE_ANDROID_KEY_ALIAS`
- `KISSNE_ANDROID_KEY_PASSWORD`

On pushes to `kissne-main`, the Android workflow builds a signed release only
when all four secrets are present. It publishes/refreshes the
`kissne-android-latest` GitHub Release and uploads the asset as
`kissne-android.apk`.

Release builds check that channel after the UI loads. When a newer
`versionCode` is available, Kissne shows an update dialog. Choosing
**立即更新** downloads the APK through Android `DownloadManager`, then opens
the system package installer. Android still requires the user to confirm the
installation and, on first use, may ask for permission to install updates from
Kissne.

Debug builds deliberately do not consume the release update channel because a
temporary debug signature cannot safely overwrite a release-signed app.
