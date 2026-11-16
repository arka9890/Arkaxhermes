# Install-time asset pack: browser bawaan

`chrome-headless-shell.zip` (Chrome for Testing 157.0.8103.78 linux-arm64) dibuat oleh
`./scripts/fetch-agent-browser.sh --stage-assets` tepat sebelum `build-apk.sh`.

Berkas ZIP ±128 MB sengaja TIDAK disimpan di Git/workspace agar repo tetap ringan,
tetapi ikut terpasang di APK/AAB melalui Play Asset Delivery `deliveryType = "install-time"`.
Saat runtime, `BrowserRuntime.kt` mengekstraknya ke `filesDir/browser/chrome` dan
`agent-browser` memakainya lewat `AGENT_BROWSER_EXECUTABLE_PATH`.
