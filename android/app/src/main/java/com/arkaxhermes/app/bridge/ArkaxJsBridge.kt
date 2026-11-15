package com.arkaxhermes.app.bridge

import android.os.Build
import android.webkit.JavascriptInterface
import com.arkaxhermes.app.BuildConfig
import com.arkaxhermes.app.MainActivity
import org.json.JSONObject

/**
 * Satu-satunya jembatan JS↔native untuk kemampuan murni Android.
 * Semua data Hermes lewat HTTP lokal (/api/…), bukan lewat interface ini.
 */
class ArkaxJsBridge(private val activity: MainActivity) {

    @JavascriptInterface
    fun ready(): String = JSONObject()
        .put("native", true)
        .put("app", "Arkaxhermes")
        .put("version", BuildConfig.VERSION_NAME)
        .put("upstreamTag", BuildConfig.ARKAX_UPSTREAM_TAG)
        .put("rootfs", BuildConfig.ARKAX_ROOTFS)
        .put("port", activity.serverPort)
        .put("token", activity.serverToken)
        .put("abi", Build.SUPPORTED_ABIS.firstOrNull() ?: "unknown")
        .put("sdk", Build.VERSION.SDK_INT)
        .toString()

    @JavascriptInterface fun port(): Int = activity.serverPort
    @JavascriptInterface fun token(): String = activity.serverToken
    @JavascriptInterface fun platform(): String = "android-${Build.VERSION.SDK_INT}"

    @JavascriptInterface fun setTheme(theme: String) = activity.applyUiTheme(theme)
    @JavascriptInterface fun haptic(kind: String) = activity.applyHaptic(kind)
    @JavascriptInterface fun pickFile(mime: String) = activity.launchFilePicker(mime)
    @JavascriptInterface fun dictate() = activity.startDictation()
    @JavascriptInterface fun copy(text: String) = activity.copyToClipboard(text)
    @JavascriptInterface fun shareText(title: String, text: String) = activity.sharePlainText(title, text)
    @JavascriptInterface fun openExternal(url: String) = activity.openExternalUrl(url)
    @JavascriptInterface fun requestPermissions(which: String) = activity.requestAppPermissions(which)
    @JavascriptInterface fun startService(name: String) = activity.controlService(name, "start")
    @JavascriptInterface fun stopService(name: String) = activity.controlService(name, "stop")
}
