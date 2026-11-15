package com.arkaxhermes.app.runtime

import android.content.Context
import android.content.Intent
import android.util.Log
import androidx.core.content.ContextCompat
import com.arkaxhermes.app.bridge.EventBus
import com.arkaxhermes.app.bridge.errorJson
import com.arkaxhermes.app.bridge.jsonOf
import com.arkaxhermes.app.data.KeyVault
import com.arkaxhermes.app.data.SettingsStore
import com.arkaxhermes.app.service.AgentService
import com.arkaxhermes.app.service.ServiceState
import com.arkaxhermes.app.util.SystemStats
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import kotlin.concurrent.thread

/** Lapisan tinggi: instalasi, chat streaming, fitur, layanan, log. */
class HermesRuntime(private val context: Context) {
    val proot = ProotRuntime(context)
    val settings = SettingsStore(context)
    val vault = KeyVault(context)

    @Volatile var state: String = initialState()
        private set
    @Volatile var hermesVersion: String = ""
        private set
    @Volatile var installing = false
        private set
    @Volatile var chatRunning = false
        private set
    @Volatile private var stopRequested = false

    private fun initialState(): String =
        if (RootfsInstaller.isInstalled(context) && File(RuntimePaths.prootBinary(context)).exists())
            "ready" else "not_installed"

    fun status(): JSONObject {
        val rootfs = RuntimePaths.rootfs(context)
        val prootFile = File(RuntimePaths.prootBinary(context))
        return jsonOf(
            "ok" to true,
            "state" to state,
            "installing" to installing,
            "rootfs" to jsonOf(
                "present" to RootfsInstaller.isInstalled(context),
                "path" to rootfs.absolutePath,
                "sizeBytes" to dirSize(rootfs),
                "release" to "Ubuntu 24.04.5 LTS",
                "arch" to (System.getProperty("os.arch") ?: "arm64")
            ),
            "proot" to jsonOf(
                "binary" to prootFile.absolutePath,
                "present" to prootFile.exists(),
                "loader" to (RuntimePaths.prootLoader(context) != null)
            ),
            "hermes" to jsonOf(
                "version" to hermesVersion.ifBlank { "belum terdeteksi" },
                "home" to RuntimePaths.HERMES_HOME_IN_ROOTFS,
                "installed" to (state == "ready"),
                "upstreamTag" to "v0.23.1"
            ),
            "services" to ServiceState.snapshot(),
            "system" to SystemStats.snapshot(),
            "model" to jsonOf(
                "provider" to settings.defaultProvider,
                "name" to settings.defaultModel,
                "context" to 200000
            ),
            "settings" to settings.snapshot()
        )
    }

    private fun dirSize(dir: File): Long {
        if (!dir.exists()) return 0
        var total = 0L
        val stack = ArrayDeque<File>()
        stack.add(dir)
        var visited = 0
        while (stack.isNotEmpty() && visited < 20000) {
            val f = stack.removeLast()
            visited++
            if (f.isFile) total += f.length()
            else f.listFiles()?.forEach { stack.add(it) }
        }
        return total
    }

    private fun appendInstallLog(line: String) {
        try {
            RuntimePaths.installLog(context).appendText(line + "\n")
        } catch (e: Exception) { /* ruang penuh: jangan gagalkan instalasi */ }
    }

    private fun parseArkaxLine(line: String): Pair<String, JSONObject>? {
        if (line.startsWith("ARKAX:step:")) {
            val parts = line.removePrefix("ARKAX:step:").split(":", limit = 4)
            if (parts.size >= 3) return "progress" to jsonOf(
                "step" to parts[0],
                "percent" to (parts[1].toIntOrNull() ?: 0),
                "message" to parts.getOrElse(2) { "" }
            )
        }
        if (line.startsWith("ARKAX:log:")) {
            return "log" to jsonOf("line" to line.removePrefix("ARKAX:log:"))
        }
        return "log" to jsonOf("line" to line)
    }

    /** Jalankan seluruh first-run: ekstraksi → bootstrap → env → doctor. */
    fun install(emit: (String, JSONObject) -> Unit) {
        if (installing) {
            emit("error", jsonOf("message" to "Instalasi sedang berjalan"))
            return
        }
        installing = true
        state = "extracting"
        EventBus.publish("state", jsonOf("state" to state, "message" to "Menyiapkan Ubuntu proot"))
        emit("state", jsonOf("state" to state, "message" to "Menyiapkan Ubuntu proot"))

        thread(name = "arkax-install", isDaemon = true) {
            try {
                val ok = RootfsInstaller.install(context) { event, data ->
                    EventBus.publish(event, data)
                    emit(event, data)
                    appendInstallLog("[${event}] ${data.optString("message", data.optString("line", ""))}")
                }
                if (!ok) {
                    state = "error"
                    EventBus.publish("state", jsonOf("state" to "error", "message" to "Ekstraksi rootfs gagal"))
                    emit("state", jsonOf("state" to "error", "message" to "Ekstraksi rootfs gagal"))
                    return@thread
                }

                state = "installing"
                EventBus.publish("state", jsonOf("state" to state, "message" to "Memasang Hermes Agent"))
                emit("state", jsonOf("state" to state, "message" to "Memasang Hermes Agent"))

                val result = proot.exec(
                    listOf("/bin/bash", "/opt/arkax/bootstrap.sh"),
                    timeoutMs = 0,
                    onStdout = { line ->
                        val parsed = parseArkaxLine(line)
                        if (parsed != null) {
                            appendInstallLog(line)
                            EventBus.publish(parsed.first, parsed.second)
                            emit(parsed.first, parsed.second)
                        }
                    },
                    onStderr = { line ->
                        appendInstallLog("stderr: $line")
                        EventBus.log("stderr: $line")
                        emit("log", jsonOf("line" to "stderr: $line"))
                    }
                )

                // Tulis ulang kunci API terenkripsi ke ~/.hermes/.env setelah rootfs siap.
                vault.names().forEach { key ->
                    val value = vault.get(key) ?: return@forEach
                    proot.exec(listOf("python3", "/opt/arkax/hermes_bridge.py", "env.set",
                        jsonOf("key" to key, "value" to value).toString()), timeoutMs = 30_000)
                }

                if (result.exit == 0) {
                    state = "ready"
                    hermesVersion = version()
                    val payload = jsonOf("state" to "ready", "message" to "hermes doctor: OK")
                    EventBus.publish("state", payload)
                    emit("state", payload)
                } else {
                    state = "error"
                    val payload = jsonOf("state" to "error",
                        "message" to "Bootstrap gagal (exit ${result.exit}). Lihat Log & Doctor.")
                    EventBus.publish("state", payload)
                    emit("state", payload)
                }
            } catch (e: Exception) {
                Log.e(TAG, "install gagal", e)
                state = "error"
                emit("error", jsonOf("message" to (e.message ?: "Instalasi gagal")))
            } finally {
                installing = false
            }
        }
    }

    fun version(): String {
        if (state != "ready") return ""
        return proot.exec(listOf("hermes", "--version"), timeoutMs = 30_000)
            .stdout.lines().firstOrNull { it.isNotBlank() }?.trim() ?: ""
    }

    fun streamChat(req: JSONObject, emit: (String, JSONObject) -> Unit) {
        if (state != "ready") {
            emit("error", jsonOf("message" to "Hermes belum siap (state=$state)"))
            return
        }
        val message = req.optString("message")
        if (message.isBlank()) {
            emit("error", jsonOf("message" to "Pesan kosong"))
            return
        }
        if (chatRunning) {
            emit("error", jsonOf("message" to "Masih ada percakapan berjalan. Tekan Stop dulu."))
            return
        }
        chatRunning = true
        stopRequested = false

        val threadId = req.optString("threadId", "default").replace(Regex("[^a-zA-Z0-9_-]"), "_")
        val session = req.optString("session", "").takeIf { it.isNotBlank() }
        val args = mutableListOf("hermes", "chat", "--query-file", "-")
        if (session != null) args += listOf("--resume", session)
        else args += listOf("--continue", "Arkax/$threadId", "--create-if-missing")

        req.optString("model", "").takeIf { it.isNotBlank() }?.let { args += listOf("--model", it) }
        req.optString("provider", "").takeIf { it.isNotBlank() && it != "auto" }?.let { args += listOf("--provider", it) }
        req.optString("toolsets", settings.toolsets).takeIf { it.isNotBlank() }?.let { args += listOf("--toolsets", it) }
        val skills = req.optJSONArray("skills")
        if (skills != null && skills.length() > 0) {
            val names = (0 until skills.length()).map { skills.getString(it) }
            args += listOf("-s", names.joinToString(","))
        }
        val images = req.optJSONArray("images")
        if (images != null) {
            for (i in 0 until images.length()) args += listOf("--image", images.getString(i))
        }
        if (req.optBoolean("yolo", settings.yolo)) args += "--yolo"
        if (req.optBoolean("safeMode", false)) args += "--safe-mode"
        val maxTurns = req.optInt("maxTurns", 90)
        args += listOf("--max-turns", maxTurns.toString(), "--pass-session-id",
            "--source", "arkaxhermes")

        val sessionRegex = Regex("""(?:Session:|session_id[=: ]+)([A-Za-z0-9_\-]+)""")
        try {
            val result = proot.exec(
                args,
                stdin = message,
                timeoutMs = 0,
                interrupt = { stopRequested },
                onStdout = { line ->
                    val trimmed = line.trim()
                    when {
                        trimmed.startsWith("{") && trimmed.endsWith("}") -> {
                            try {
                                val obj = JSONObject(trimmed)
                                val type = obj.optString("type", "chunk")
                                emit(type, obj)
                            } catch (e: Exception) { emit("chunk", jsonOf("text" to line + "\n")) }
                        }
                        sessionRegex.containsMatchIn(line) -> {
                            val id = sessionRegex.find(line)?.groupValues?.get(1) ?: ""
                            emit("session", jsonOf("id" to id, "title" to "Arkax/$threadId"))
                            emit("chunk", jsonOf("text" to line + "\n"))
                        }
                        trimmed.startsWith("→") || trimmed.startsWith("[tool]") ||
                            trimmed.contains("tool_call", true) ->
                            emit("tool", jsonOf("name" to "tool", "detail" to line))
                        else -> emit("chunk", jsonOf("text" to line + "\n"))
                    }
                },
                onStderr = { line -> emit("log", jsonOf("line" to line)) }
            )
            emit("done", jsonOf("exit" to result.exit, "elapsedMs" to result.elapsedMs,
                "tokens" to (message.length + result.stdout.length) / 4))
            if (result.exit != 0 && !stopRequested) {
                emit("error", jsonOf("message" to result.stderr.takeLast(1000), "exit" to result.exit))
            }
        } catch (e: Exception) {
            emit("error", jsonOf("message" to (e.message ?: "chat gagal")))
        } finally {
            chatRunning = false
        }
    }

    fun stopChat() { stopRequested = true }

    fun execRequest(req: JSONObject): JSONObject {
        if (state != "ready") return errorJson("not_ready", "Hermes belum siap")
        val array = req.optJSONArray("argv")
            ?: return errorJson("bad_argv", "argv (array string) wajib diisi")
        val argv = (0 until array.length()).map { array.getString(it) }
        if (argv.isEmpty()) return errorJson("bad_argv", "argv kosong")
        val stdin = req.optString("stdin", "").takeIf { it.isNotEmpty() }
        val timeout = req.optLong("timeoutMs", 180_000)
        val tty = req.optBoolean("tty", false)
        val result = if (tty) {
            proot.tty(argv.joinToString(" ") { if (it.contains(" ")) "'$it'" else it })
        } else {
            proot.exec(argv, stdin = stdin, timeoutMs = timeout)
        }
        return jsonOf("ok" to (result.exit == 0), "stdout" to result.stdout,
            "stderr" to result.stderr, "exit" to result.exit, "elapsedMs" to result.elapsedMs)
    }

    /** Satu pintu ke semua aksi hermes_bridge.py. */
    fun feature(action: String, payload: JSONObject): JSONObject {
        if (state != "ready") return errorJson("not_ready", "Hermes belum siap",
            "Layar ini akan aktif setelah Ubuntu proot siap.")
        val body = JSONObject(payload.toString())
        when (action) {
            "env.set" -> {
                val key = body.optString("key")
                val value = body.optString("value")
                if (key.isNotBlank()) {
                    if (value.isBlank()) vault.delete(key) else vault.put(key, value)
                }
            }
            "env.delete" -> vault.delete(body.optString("key"))
        }
        val result = proot.exec(
            listOf("python3", "/opt/arkax/hermes_bridge.py", action, body.toString()),
            timeoutMs = 150_000
        )
        val line = result.stdout.lines().lastOrNull {
            val t = it.trim()
            t.startsWith("{") && t.endsWith("}")
        }
        return try {
            JSONObject(line ?: "{}")
        } catch (e: Exception) {
            errorJson("bridge_failed", "Output bridge bukan JSON", result.stdout.takeLast(800))
        }
    }

    fun service(name: String, action: String): JSONObject {
        val allowedNames = listOf("gateway", "cron", "dashboard", "webhook", "all")
        val allowedActions = listOf("start", "stop", "restart", "status")
        if (name !in allowedNames || action !in allowedActions)
            return errorJson("bad_request", "nama/aksi layanan tidak dikenal")
        settings.setServiceEnabled(name, action != "stop")
        val intent = Intent(context, AgentService::class.java)
            .putExtra("name", name)
            .putExtra("action", action)
        ContextCompat.startForegroundService(context, intent)
        return jsonOf("ok" to true, "name" to name, "action" to action,
            "message" to "Permintaan $action untuk $name dikirim ke AgentService")
    }

    fun logs(lines: Int = 200): String {
        val all = mutableListOf<String>()
        val installLog = RuntimePaths.installLog(context)
        if (installLog.exists()) all += installLog.readLines()
        val hermesLogs = RuntimePaths.hermesHomeOnHost(context).resolve("logs")
        if (hermesLogs.exists()) {
            hermesLogs.listFiles()?.sortedByDescending { it.lastModified() }?.take(4)?.forEach { f ->
                if (f.isFile) all += f.readLines().takeLast(200)
            }
        }
        return all.takeLast(lines).joinToString("\n")
    }

    companion object {
        private const val TAG = "HermesRuntime"
    }
}
