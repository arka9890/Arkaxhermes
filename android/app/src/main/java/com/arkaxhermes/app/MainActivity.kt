package com.arkaxhermes.app

import android.Manifest
import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.speech.RecognizerIntent
import android.view.HapticFeedbackConstants
import android.view.Window
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebChromeClient.FileChooserParams
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import com.arkaxhermes.app.bridge.ArkaxHttpServer
import com.arkaxhermes.app.bridge.ArkaxJsBridge
import com.arkaxhermes.app.data.SettingsStore
import com.arkaxhermes.app.runtime.HermesRuntime
import com.arkaxhermes.app.runtime.RuntimePaths
import org.json.JSONObject
import java.io.File
import java.security.SecureRandom

class MainActivity : Activity() {

    private lateinit var webView: WebView
    private lateinit var runtime: HermesRuntime
    private lateinit var prefs: SettingsStore
    private var server: ArkaxHttpServer? = null
    private var filePathCallback: ValueCallback<Array<Uri>>? = null

    val serverToken: String = SecureRandom().let { r ->
        ByteArray(32).also { r.nextBytes(it) }.joinToString("") { "%02x".format(it) }
    }
    var serverPort: Int = 0
        private set

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestWindowFeature(Window.FEATURE_NO_TITLE)
        RuntimePaths.ensure(this)
        prefs = SettingsStore(this)
        runtime = HermesRuntime(this)

        server = ArkaxHttpServer(this, runtime, prefs, serverToken)
        serverPort = try {
            server!!.start()
        } catch (e: Exception) {
            Toast.makeText(this, "Gagal menyalakan server jembatan: ${e.message}", Toast.LENGTH_LONG).show()
            0
        }

        WebView.setWebContentsDebuggingEnabled(true)
        webView = WebView(this)
        setContentView(webView)
        configureWebView()
        applyUiTheme(prefs.theme)
        requestAppPermissions("startup")

        if (serverPort > 0) {
            webView.loadUrl("http://127.0.0.1:$serverPort/")
        } else {
            // Fallback offline: UI tetap tampil dalam mode demo.
            webView.loadUrl("file:///android_asset/www/index.html")
        }
    }

    private fun configureWebView() {
        webView.apply {
            val ws = settings
            ws.javaScriptEnabled = true
            ws.domStorageEnabled = true
            ws.databaseEnabled = true
            ws.allowFileAccess = true
            ws.allowContentAccess = true
            ws.setAllowFileAccessFromFileURLs(false)
            ws.setAllowUniversalAccessFromFileURLs(false)
            @Suppress("SetJavaScriptEnabled")
            ws.mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            ws.cacheMode = WebSettings.LOAD_NO_CACHE
            ws.setSupportZoom(false)
            ws.userAgentString = "${ws.userAgentString} Arkaxhermes/${BuildConfig.VERSION_NAME}"

            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView?, url: String?): Boolean {
                    if (url == null) return false
                    if (url.startsWith("http://127.0.0.1:") || url.startsWith("file:///android_asset/")) return false
                    if (url.startsWith("https://")) { openExternalUrl(url); return true }
                    return true
                }
            }
            webChromeClient = object : WebChromeClient() {
                override fun onShowFileChooser(
                    view: WebView?,
                    callback: ValueCallback<Array<Uri>>?,
                    params: FileChooserParams?
                ): Boolean {
                    filePathCallback?.onReceiveValue(null)
                    filePathCallback = callback
                    val mime = params?.acceptTypes?.firstOrNull { it.isNotBlank() } ?: "*/*"
                    launchFilePicker(mime)
                    return true
                }
            }
            addJavascriptInterface(ArkaxJsBridge(this@MainActivity), "ArkaxBridge")
        }
    }

    fun applyUiTheme(theme: String) {
        val dark = when (theme) {
            "dark" -> true
            "light" -> false
            else -> (resources.configuration.uiMode and android.content.res.Configuration.UI_MODE_NIGHT_MASK) ==
                android.content.res.Configuration.UI_MODE_NIGHT_YES
        }
        val color = Color.parseColor(if (dark) "#0B1326" else "#F0F4FC")
        window.statusBarColor = color
        window.navigationBarColor = color
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val appearance = if (dark) 0 else
                android.view.WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS or
                    android.view.WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS
            window.insetsController?.setSystemBarsAppearance(appearance,
                android.view.WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS or
                    android.view.WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS)
        }
    }

    fun applyHaptic(kind: String) {
        runOnUiThread {
            val constant = when (kind) {
                "heavy" -> HapticFeedbackConstants.LONG_PRESS
                "medium" -> HapticFeedbackConstants.KEYBOARD_TAP
                else -> HapticFeedbackConstants.VIRTUAL_KEY
            }
            webView.performHapticFeedback(constant)
        }
    }

    fun launchFilePicker(mime: String) {
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = if (mime == "*") "*/*" else mime
            putExtra(Intent.EXTRA_ALLOW_MULTIPLE, false)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        try { startActivityForResult(intent, REQ_FILE) }
        catch (e: Exception) { Toast.makeText(this, "Tidak ada pengelola berkas", Toast.LENGTH_SHORT).show() }
    }

    fun startDictation() {
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "id-ID")
            putExtra(RecognizerIntent.EXTRA_PROMPT, "Dikte untuk Hermes Agent")
        }
        try { startActivityForResult(intent, REQ_DICTATION) }
        catch (e: Exception) {
            Toast.makeText(this, "Pengenalan suara tidak tersedia di perangkat ini", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQ_FILE) {
            val uris: Array<Uri>? = if (resultCode == RESULT_OK) {
                data?.data?.let { arrayOf(it) } ?: data?.clipData?.let { clip ->
                    Array(clip.itemCount) { clip.getItemAt(it).uri }
                }
            } else null
            filePathCallback?.onReceiveValue(uris)
            filePathCallback = null
            uris?.firstOrNull()?.let { uri -> copyAttachment(uri) }
            return
        }
        if (requestCode == REQ_DICTATION && resultCode == RESULT_OK) {
            val text = data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull().orEmpty()
            callJs("window.__arkax.onDictation", JSONObject().put("text", text).toString())
        }
    }

    private fun copyAttachment(uri: Uri) {
        try {
            val name = uri.lastPathSegment?.substringAfterLast('/')?.take(80) ?: "lampiran"
            val dest = File(RuntimePaths.inbox(this), name.replace(Regex("[^a-zA-Z0-9._-]"), "_"))
            contentResolver.openInputStream(uri)?.use { input ->
                dest.outputStream().use { output -> input.copyTo(output) }
            }
            callJs("window.__arkax.onFilePicked", JSONObject()
                .put("name", dest.name)
                .put("path", "${RuntimePaths.SHARED_IN_ROOTFS}/inbox/${dest.name}")
                .put("size", dest.length()).toString())
        } catch (e: Exception) {
            Toast.makeText(this, "Gagal menyalin lampiran: ${e.message}", Toast.LENGTH_SHORT).show()
        }
    }

    private fun callJs(fn: String, json: String) {
        runOnUiThread {
            webView.evaluateJavascript("$fn($json);", null)
        }
    }

    fun copyToClipboard(text: String) {
        val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        cm.setPrimaryClip(ClipData.newPlainText("Arkaxhermes", text))
    }

    /** Penyimpanan terenkripsi AES-GCM untuk state UI (mis. riwayat obrolan). */
    fun securePut(name: String, value: String) {
        runtime.vault.put("arkax_secure_$name", value)
    }

    fun secureGet(name: String): String =
        runtime.vault.get("arkax_secure_$name") ?: ""

    fun openBrowserDashboard() {
        // Dashboard bawaan agent-browser; dibuka di browser sistem karena
        // dashboard Next.js tidak ramah di-iframe. Tab Browser tetap live di aplikasi.
        try { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("http://127.0.0.1:4848"))) }
        catch (e: Exception) { Toast.makeText(this, "Dashboard browser tidak tersedia", Toast.LENGTH_SHORT).show() }
    }

    fun secureDelete(name: String) {
        runtime.vault.delete("arkax_secure_$name")
        runtime.vault.delete(name)
    }

    fun sharePlainText(title: String, text: String) {
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_SUBJECT, title)
            putExtra(Intent.EXTRA_TEXT, text)
        }
        startActivity(Intent.createChooser(intent, title))
    }

    fun openExternalUrl(url: String) {
        if (!url.startsWith("https://")) return
        try { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }
        catch (e: Exception) { Toast.makeText(this, "Tidak ada browser", Toast.LENGTH_SHORT).show() }
    }

    fun requestAppPermissions(which: String) {
        val needed = mutableListOf<String>()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) needed += Manifest.permission.POST_NOTIFICATIONS
        if (which == "mic" || which == "startup") needed += Manifest.permission.RECORD_AUDIO
        if (needed.isNotEmpty()) requestPermissions(needed.toTypedArray(), REQ_PERMISSIONS)
        if (which == "battery" && !prefs.batteryExemptionAsked) {
            prefs.batteryExemptionAsked = true
            try {
                startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                    data = Uri.parse("package:$packageName")
                })
            } catch (e: Exception) { /* OEM tidak menyediakan intent ini */ }
        }
    }

    fun controlService(name: String, action: String) {
        val result = runtime.service(name, action)
        Toast.makeText(this, result.optString("message", "Layanan: $action $name"), Toast.LENGTH_SHORT).show()
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (::webView.isInitialized && webView.canGoBack()) webView.goBack()
        else super.onBackPressed()
    }

    override fun onDestroy() {
        server?.stop()
        server = null
        if (::webView.isInitialized) webView.destroy()
        super.onDestroy()
    }

    companion object {
        private const val REQ_FILE = 1001
        private const val REQ_DICTATION = 1002
        private const val REQ_PERMISSIONS = 1003
    }
}
