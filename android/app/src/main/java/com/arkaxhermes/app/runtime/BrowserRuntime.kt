package com.arkaxhermes.app.runtime

import android.content.Context
import android.util.Log
import com.arkaxhermes.app.bridge.jsonOf
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.util.zip.ZipInputStream

/**
 * Browser bawaan Arkaxhermes: agent-browser v0.43.0 + Chrome for Testing.
 *
 * `agent-browser` adalah Rust CLI yang menjalankan daemon CDP. Setiap session
 * otomatis membuka WebSocket stream (kita pin ke 9223) yang mengirim frame
 * JPEG + menerima input mouse/keyboard/touch. Tab Browser di WebView
 * menghubunginya langsung; dashboard bawaan tersedia di port 4848.
 */
class BrowserRuntime(
    private val context: Context,
    private val proot: ProotRuntime
) {
    data class EnsureResult(val ok: Boolean, val message: String, val path: String)

    fun ensureChrome(): EnsureResult {
        val zip = RuntimePaths.browserZip(context)
        val chromeDir = RuntimePaths.browserChrome(context)
        val marker = File(chromeDir, ".arkax-ready")
        if (marker.exists()) {
            return EnsureResult(true, "Chrome sudah diekstrak", chromeDir.absolutePath)
        }
        if (!zip.exists()) {
            val copied = AssetExtractor.extractBrowserAsset(context, zip)
            if (!copied) {
                return EnsureResult(false,
                    "Asset pack chrome-headless-shell.zip tidak ada. Jalankan ./scripts/fetch-agent-browser.sh --stage-assets lalu build ulang APK.",
                    zip.absolutePath)
            }
        }
        return try {
            chromeDir.mkdirs()
            unzip(zip, chromeDir)
            val binary = findChromeBinary(chromeDir)
                ?: return EnsureResult(false, "Biner chrome-headless-shell tidak ditemukan dalam ZIP", chromeDir.absolutePath)
            binary.setExecutable(true, false)

            // Chrome di proot Android tidak boleh memakai sandbox SUID / GPU.
            val wrapper = File(chromeDir, "chrome-wrapper.sh")
            wrapper.writeText(
                "#!/bin/sh\n" +
                    "exec \"${binary.absolutePath}\" " +
                    "--no-sandbox --disable-dev-shm-usage --disable-gpu " +
                    "--disable-software-rasterizer --hide-scrollbars \"$@\"\n"
            )
            wrapper.setExecutable(true, false)
            marker.writeText("agent-browser v0.43.0 · Chrome for Testing 157.0.8103.78\n")
            EnsureResult(true, "Chrome siap", wrapper.absolutePath)
        } catch (e: Exception) {
            Log.e(TAG, "ekstraksi Chrome gagal", e)
            EnsureResult(false, "Gagal mengekstrak Chrome: ${e.message}", chromeDir.absolutePath)
        }
    }

    private fun findChromeBinary(root: File): File? {
        val stack = ArrayDeque<File>()
        stack.add(root)
        while (stack.isNotEmpty()) {
            val f = stack.removeLast()
            if (f.isFile && (f.name == "chrome-headless-shell" || f.name == "headless_shell")) return f
            if (f.isDirectory) f.listFiles()?.forEach { stack.add(it) }
        }
        return null
    }

    private fun unzip(zip: File, dest: File) {
        ZipInputStream(zip.inputStream()).use { zis ->
            val buffer = ByteArray(128 * 1024)
            while (true) {
                val entry = zis.nextEntry ?: break
                val name = entry.name.replace('\\', '/')
                val target = File(dest, name).canonicalFile
                if (target != dest && !target.path.startsWith(dest.canonicalPath + File.separator)) {
                    zis.closeEntry()
                    continue
                }
                if (entry.isDirectory) {
                    target.mkdirs()
                } else {
                    target.parentFile?.mkdirs()
                    FileOutputStream(target).use { out ->
                        while (true) {
                            val n = zis.read(buffer)
                            if (n <= 0) break
                            out.write(buffer, 0, n)
                        }
                    }
                }
                zis.closeEntry()
            }
        }
    }

    private fun cli(argv: List<String>, timeoutMs: Long = 120_000): JSONObject {
        val ensured = ensureChrome()
        if (!ensured.ok) return jsonOf("ok" to false, "error" to "chrome_missing", "message" to ensured.message)
        val result = proot.exec(listOf("/usr/local/bin/agent-browser") + argv, timeoutMs = timeoutMs)
        val parsed = parseJson(result.stdout) ?: JSONObject()
        return jsonOf(
            "ok" to (result.exit == 0),
            "argv" to argv,
            "stdout" to result.stdout,
            "stderr" to result.stderr,
            "exit" to result.exit,
            "elapsedMs" to result.elapsedMs,
            "data" to parsed.optJSONObject("data"),
            "raw" to parsed
        )
    }

    private fun parseJson(stdout: String): JSONObject? {
        val lines = stdout.lines().map { it.trim() }.filter { it.startsWith("{") && it.endsWith("}") }
        for (line in lines.asReversed()) {
            try {
                val obj = JSONObject(line)
                if (obj.has("success") || obj.has("data") || obj.has("error")) return obj
            } catch (e: Exception) { /* baris log biasa */ }
        }
        return null
    }

    fun command(argv: List<String>): JSONObject {
        if (argv.isEmpty()) return jsonOf("ok" to false, "message" to "argv kosong")
        return cli(argv)
    }

    fun status(): JSONObject {
        val ensured = ensureChrome()
        val stream = cli(listOf("stream", "status"), 30_000)
        val url = cli(listOf("get", "url"), 30_000)
        val title = cli(listOf("get", "title"), 30_000)
        val cdp = cli(listOf("get", "cdp-url"), 30_000)
        val tabs = cli(listOf("tab", "list"), 30_000)
        return jsonOf(
            "ok" to true,
            "chrome" to ensured.ok,
            "chromeMessage" to ensured.message,
            "session" to SESSION,
            "streamPort" to STREAM_PORT,
            "streamUrl" to "ws://127.0.0.1:$STREAM_PORT/?pacing=ack&maxFps=8",
            "dashboardUrl" to "http://127.0.0.1:$DASHBOARD_PORT",
            "url" to (url.optJSONObject("data")?.optString("url") ?: ""),
            "title" to (title.optJSONObject("data")?.optString("title") ?: ""),
            "cdpUrl" to (cdp.optJSONObject("data")?.optString("cdpUrl") ?: ""),
            "stream" to stream,
            "tabs" to tabs
        )
    }

    fun start(): JSONObject {
        val dash = cli(listOf("dashboard", "start", "--port", DASHBOARD_PORT.toString()), 60_000)
        val open = cli(listOf("open", "about:blank"), 120_000)
        return jsonOf("ok" to (dash.optBoolean("ok", false) && open.optBoolean("ok", false)),
            "dashboard" to dash, "open" to open,
            "streamUrl" to "ws://127.0.0.1:$STREAM_PORT/?pacing=ack&maxFps=8",
            "dashboardUrl" to "http://127.0.0.1:$DASHBOARD_PORT")
    }

    fun stop(): JSONObject {
        val close = cli(listOf("close"), 60_000)
        val dash = cli(listOf("dashboard", "stop"), 60_000)
        return jsonOf("ok" to true, "close" to close, "dashboard" to dash)
    }

    fun snapshot(): JSONObject = cli(listOf("snapshot", "-i"), 60_000)

    fun screenshot(): JSONObject {
        val stamp = System.currentTimeMillis()
        val path = "/mnt/arkax/exports/browser-$stamp.jpg"
        return jsonOf("path" to path,
            "command" to cli(listOf("screenshot", path,
                "--screenshot-format", "jpeg", "--screenshot-quality", "80"), 120_000))
    }

    companion object {
        private const val TAG = "BrowserRuntime"
        const val SESSION = "arkaxhermes"
        const val STREAM_PORT = 9223
        const val DASHBOARD_PORT = 4848
    }
}
