package com.arkaxhermes.app.bridge

import android.content.Context
import android.util.Log
import com.arkaxhermes.app.data.SettingsStore
import com.arkaxhermes.app.runtime.HermesRuntime
import org.json.JSONObject
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.net.SocketException
import java.net.URLDecoder
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Server jembatan loopback. Hanya bind 127.0.0.1, port 18789–18799, dan
 * memeriksa token acak per proses. UI dimuat dari sini pula supaya fetch/SSE
 * tidak terkena pembatasan origin file://.
 */
class ArkaxHttpServer(
    private val context: Context,
    private val runtime: HermesRuntime,
    private val settings: SettingsStore,
    private val token: String
) {
    private var serverSocket: ServerSocket? = null
    private val executor = Executors.newCachedThreadPool()
    private val alive = AtomicBoolean(false)
    @Volatile var port: Int = 0
        private set

    fun start(): Int {
        var lastError: Exception? = null
        for (candidate in 18789..18799) {
            try {
                serverSocket = ServerSocket(candidate, 50, InetAddress.getByName("127.0.0.1"))
                port = candidate
                break
            } catch (e: IOException) {
                lastError = e
            }
        }
        val socket = serverSocket ?: throw (lastError ?: IOException("tidak ada port loopback kosong"))
        alive.set(true)
        executor.submit { acceptLoop(socket) }
        Log.i(TAG, "ArkaxHttpServer aktif di http://127.0.0.1:$port/")
        return port
    }

    fun stop() {
        alive.set(false)
        try { serverSocket?.close() } catch (e: Exception) { /* sudah tertutup */ }
        serverSocket = null
        executor.shutdownNow()
        Log.i(TAG, "ArkaxHttpServer dihentikan")
    }

    private fun acceptLoop(socket: ServerSocket) {
        while (alive.get()) {
            try {
                val client = socket.accept()
                executor.submit { handle(client) }
            } catch (e: SocketException) {
                if (alive.get()) Log.w(TAG, "accept: ${e.message}")
                break
            } catch (e: Exception) {
                Log.w(TAG, "accept: ${e.message}")
            }
        }
    }

    private data class Request(
        val method: String, val path: String, val query: String,
        val headers: Map<String, String>, val body: String
    )

    private fun readAsciiLine(input: InputStream): String? {
        val sb = StringBuilder()
        while (true) {
            val c = input.read()
            if (c < 0) return if (sb.isEmpty()) null else sb.toString()
            if (c == 10) return sb.toString()
            if (c != 13) sb.append(c.toChar())
        }
    }

    private fun readExactly(input: InputStream, size: Int): ByteArray {
        val buf = ByteArray(size)
        var off = 0
        while (off < size) {
            val n = input.read(buf, off, size - off)
            if (n < 0) return buf.copyOf(off)
            off += n
        }
        return buf
    }

    private fun readRequest(input: InputStream): Request? {
        val line = readAsciiLine(input) ?: return null
        val parts = line.split(' ', limit = 3)
        if (parts.size < 2) return null
        val full = parts[1]
        val headers = mutableMapOf<String, String>()
        while (true) {
            val h = readAsciiLine(input) ?: break
            if (h.isEmpty()) break
            val idx = h.indexOf(':')
            if (idx > 0) headers[h.substring(0, idx).trim().lowercase()] = h.substring(idx + 1).trim()
        }
        val len = headers["content-length"]?.toIntOrNull()?.coerceIn(0, 8 * 1024 * 1024) ?: 0
        val body = if (len > 0) String(readExactly(input, len), Charsets.UTF_8) else ""
        return Request(parts[0].uppercase(), full.substringBefore('?'),
            full.substringAfter('?', ""), headers, body)
    }

    private fun writeResponse(out: OutputStream, code: Int, contentType: String,
                              body: ByteArray, extra: String = "") {
        val reason = when (code) {
            200 -> "OK"; 400 -> "Bad Request"; 403 -> "Forbidden"; 404 -> "Not Found"
            409 -> "Conflict"; 424 -> "Failed Dependency"; 500 -> "Internal Server Error"
            504 -> "Gateway Timeout"; else -> "OK"
        }
        val head = "HTTP/1.1 $code $reason\r\n" +
            "Content-Type: $contentType\r\n" +
            "Content-Length: ${body.size}\r\n" +
            "Access-Control-Allow-Origin: *\r\n" +
            "Access-Control-Allow-Headers: Content-Type, X-Arkax-Token\r\n" +
            "Cache-Control: no-store\r\n" +
            "X-Content-Type-Options: nosniff\r\n" +
            "Connection: close\r\n" + extra + "\r\n"
        out.write(head.toByteArray(Charsets.ISO_8859_1))
        out.write(body)
        out.flush()
    }

    private fun respondJson(out: OutputStream, code: Int, obj: JSONObject) =
        writeResponse(out, code, "application/json; charset=utf-8",
            obj.toString().toByteArray(Charsets.UTF_8))

    private fun sseHeaders(out: OutputStream) {
        out.write(("HTTP/1.1 200 OK\r\n" +
            "Content-Type: text/event-stream; charset=utf-8\r\n" +
            "Cache-Control: no-cache\r\n" +
            "Access-Control-Allow-Origin: *\r\n" +
            "Connection: keep-alive\r\n\r\n").toByteArray(Charsets.ISO_8859_1))
        out.flush()
    }

    private fun sse(out: OutputStream, event: String, data: JSONObject) {
        out.write("event: $event\ndata: ${data.toString()}\n\n".toByteArray(Charsets.UTF_8))
        out.flush()
    }

    private fun sseText(out: OutputStream, event: String, text: String) =
        sse(out, event, jsonOf("line" to text, "text" to text))

    private fun authorized(req: Request, socket: Socket): Boolean {
        if (req.headers["x-arkax-token"] != token) return false
        if (!socket.inetAddress.isLoopbackAddress) return false
        val origin = req.headers["origin"]
        return origin.isNullOrBlank() || origin == "null" || origin.startsWith("http://127.0.0.1:$port")
    }

    private fun queryValue(query: String, key: String): String? = query.split('&')
        .firstOrNull { it.substringBefore('=') == key }
        ?.substringAfter('=', "")
        ?.let { URLDecoder.decode(it, "UTF-8") }

    private fun serveIndex(out: OutputStream) {
        val bytes = assetBytes(context, "www/index.html")
            ?: "<h1>Arkaxhermes</h1><p>UI tidak ditemukan.</p>".toByteArray(Charsets.UTF_8)
        writeResponse(out, 200, "text/html; charset=utf-8", bytes)
    }

    private fun serveFavicon(out: OutputStream) {
        val svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="16" fill="#2346D5"/><text x="32" y="44" font-size="38" text-anchor="middle" fill="#fff">☤</text></svg>"""
        writeResponse(out, 200, "image/svg+xml", svg.toByteArray(Charsets.UTF_8))
    }

    private fun parseBody(body: String): JSONObject = try {
        if (body.isBlank()) JSONObject() else JSONObject(body)
    } catch (e: Exception) {
        throw IllegalArgumentException("body bukan JSON: ${e.message}")
    }

    private fun holdEventStream(out: OutputStream, hello: JSONObject) {
        sse(out, "hello", hello)
        // Menulis ping akan melempar IOException saat klien memutus; itu dipakai
        // sebagai sinyal berhenti (tidak perlu membaca ulang socket).
        while (alive.get()) {
            Thread.sleep(15_000)
            sse(out, "ping", jsonOf("ts" to System.currentTimeMillis()))
        }
    }

    private fun handle(socket: Socket) {
        var headersSent = false
        socket.use { sock ->
            val input = sock.getInputStream()
            val out = sock.getOutputStream()
            val req = try { readRequest(input) } catch (e: Exception) { null }
            if (req == null) { writeResponse(out, 400, "text/plain", "Bad request".toByteArray()); return }

            try {
                // ---- Statis / health: tanpa token agar halaman pertama bisa dimuat ----
                if (req.method == "GET" && (req.path == "/" || req.path == "/index.html")) {
                    serveIndex(out); headersSent = true; return
                }
                if (req.path == "/favicon.svg") { serveFavicon(out); headersSent = true; return }
                if (req.path == "/health") {
                    respondJson(out, 200, jsonOf("ok" to true, "app" to "Arkaxhermes",
                        "version" to "0.1.0", "port" to port)); headersSent = true; return
                }

                if (!req.path.startsWith("/api/")) {
                    respondJson(out, 404, errorJson("not_found", "Endpoint tidak ada")); headersSent = true; return
                }
                if (!authorized(req, sock)) {
                    respondJson(out, 403, errorJson("forbidden", "Token atau origin tidak valid"))
                    headersSent = true; return
                }

                // ---- Status ----
                if (req.method == "GET" && req.path == "/api/status") {
                    respondJson(out, 200, runtime.status()); headersSent = true; return
                }

                // ---- Instalasi ----
                if (req.method == "POST" && req.path == "/api/install") {
                    runtime.install { _, _ -> /* runtime.install sudah publish ke EventBus */ }
                    respondJson(out, 200, jsonOf("ok" to true, "started" to true))
                    headersSent = true; return
                }
                if (req.method == "GET" &&
                    (req.path == "/api/install/stream" || req.path == "/api/events")) {
                    sseHeaders(out); headersSent = true
                    val unsubscribe = EventBus.subscribe { event, data ->
                        try { sse(out, event, data) } catch (e: IOException) { throw e }
                    }
                    try {
                        holdEventStream(out, jsonOf("state" to runtime.state,
                            "message" to "Terhubung ke Arkaxhermes bridge"))
                    } finally { unsubscribe() }
                    return
                }

                // ---- Chat streaming ----
                if (req.method == "POST" && req.path == "/api/chat") {
                    val body = parseBody(req.body)
                    sseHeaders(out); headersSent = true
                    runtime.streamChat(body) { event, data ->
                        try { sse(out, event, data) } catch (e: IOException) { Log.w(TAG, "SSE chat putus") }
                    }
                    return
                }
                if (req.method == "POST" && req.path == "/api/chat/stop") {
                    runtime.stopChat()
                    respondJson(out, 200, jsonOf("ok" to true, "stopped" to true))
                    headersSent = true; return
                }

                // ---- Eksekusi perintah (Terminal) ----
                if (req.method == "POST" && req.path == "/api/exec") {
                    respondJson(out, 200, runtime.execRequest(parseBody(req.body)))
                    headersSent = true; return
                }
                if (req.method == "POST" && req.path == "/api/exec/stream") {
                    val body = parseBody(req.body)
                    val array = body.optJSONArray("argv")
                        ?: throw IllegalArgumentException("argv wajib diisi")
                    val argv = (0 until array.length()).map { array.getString(it) }
                    sseHeaders(out); headersSent = true
                    val result = runtime.proot.exec(argv,
                        stdin = body.optString("stdin", "").takeIf { it.isNotEmpty() },
                        timeoutMs = body.optLong("timeoutMs", 180_000),
                        onStdout = { sseText(out, "stdout", it) },
                        onStderr = { sseText(out, "stderr", it) })
                    sse(out, "exit", jsonOf("exit" to result.exit, "elapsedMs" to result.elapsedMs))
                    return
                }

                // ---- Fitur Hermes (hermes_bridge.py atau CLI) ----
                if (req.method == "POST" && req.path.startsWith("/api/hermes/")) {
                    val body = parseBody(req.body)
                    val fromPath = req.path.removePrefix("/api/hermes/").replace('/', '.')
                    val action = if (fromPath == "feature") body.optString("action") else fromPath
                    val payload = body.optJSONObject("payload") ?: JSONObject(body.toString())
                    payload.remove("action"); payload.remove("payload")
                    val response = if (action.isBlank())
                        errorJson("bad_request", "action wajib diisi")
                    else runtime.feature(action, payload)
                    respondJson(out, if (response.optBoolean("ok", false)) 200 else 424, response)
                    headersSent = true; return
                }

                // ---- Berkas workspace ----
                if (req.path == "/api/files") {
                    val response = when (req.method) {
                        "GET" -> runtime.feature("files.list",
                            jsonOf("path" to (queryValue(req.query, "path")
                                ?: com.arkaxhermes.app.runtime.RuntimePaths.HERMES_HOME_IN_ROOTFS)))
                        "POST" -> {
                            val body = parseBody(req.body)
                            val op = body.optString("op", "files.read")
                            runtime.feature(op, body)
                        }
                        "DELETE" -> runtime.feature("files.delete", parseBody(req.body))
                        else -> errorJson("bad_request", "method tidak didukung")
                    }
                    respondJson(out, 200, response); headersSent = true; return
                }

                // ---- Pengaturan ----
                if (req.path == "/api/settings" && req.method == "GET") {
                    respondJson(out, 200, settings.snapshot()); headersSent = true; return
                }
                if (req.path == "/api/settings" && req.method == "POST") {
                    respondJson(out, 200, settings.applyPatch(parseBody(req.body)))
                    headersSent = true; return
                }

                // ---- Layanan ----
                if (req.path == "/api/service" && req.method == "POST") {
                    val body = parseBody(req.body)
                    respondJson(out, 200, runtime.service(
                        body.optString("name", "gateway"), body.optString("action", "start")))
                    headersSent = true; return
                }

                // ---- Log & doctor ----
                if (req.path == "/api/logs" && req.method == "GET") {
                    val n = queryValue(req.query, "lines")?.toIntOrNull() ?: 200
                    respondJson(out, 200, jsonOf("ok" to true, "logs" to runtime.logs(n)))
                    headersSent = true; return
                }
                if (req.path == "/api/doctor" && req.method == "GET") {
                    respondJson(out, 200, runtime.feature("doctor", JSONObject()))
                    headersSent = true; return
                }

                respondJson(out, 404, errorJson("not_found", "Endpoint tidak ada: ${req.path}"))
                headersSent = true
            } catch (e: IllegalArgumentException) {
                if (!headersSent) respondJson(out, 400, errorJson("bad_json", e.message ?: "input tidak valid"))
            } catch (e: Exception) {
                Log.e(TAG, "handler error", e)
                if (!headersSent) respondJson(out, 500,
                    errorJson("exec_failed", e.message ?: "kesalahan internal"))
            }
        }
    }

    companion object {
        private const val TAG = "ArkaxHttpServer"
    }
}
