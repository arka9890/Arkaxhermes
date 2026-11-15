package com.arkaxhermes.app.runtime

import android.content.Context
import android.util.Log
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * Menjalankan perintah apa pun di dalam Ubuntu proot.
 *
 * Biner proot diambil dari nativeLibraryDir (bukan filesDir) karena Android 10+
 * menolak execve() pada berkas di direktori data aplikasi yang writable.
 */
class ProotRuntime(private val context: Context) {

    data class Result(val stdout: String, val stderr: String, val exit: Int, val elapsedMs: Long)

    fun ready(): Boolean = File(RuntimePaths.prootBinary(context)).exists() &&
        RootfsInstaller.isInstalled(context)

    /** Bangun argv lengkap: [libproot.so, …flags…, env, bash entrypoint, inner argv]. */
    fun buildCommand(inner: List<String>): List<String> {
        RuntimePaths.ensure(context)
        val proot = RuntimePaths.prootBinary(context)
        val rootfs = RuntimePaths.rootfs(context)
        val shared = RuntimePaths.shared(context)
        val scripts = RuntimePaths.scripts(context)
        val tmp = RuntimePaths.tmp(context)

        val cmd = mutableListOf(
            proot,
            "-0",                                   // fake uid/gid 0 (bukan root kernel)
            "-r", rootfs.absolutePath,
            "-w", "/root",
            "-b", "/proc", "-b", "/dev", "-b", "/sys",
            "-b", "${shared.absolutePath}:${RuntimePaths.SHARED_IN_ROOTFS}",
            "-b", "${scripts.absolutePath}:${RuntimePaths.RUNTIME_IN_ROOTFS}",
            "--link2symlink",                      // dpkg/apt di filesystem Android
            "--kill-on-exit",
            "/usr/bin/env", "-i",
            "HOME=/root",
            "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "LANG=C.UTF-8", "LC_ALL=C.UTF-8",
            "TERM=xterm-256color",
            "HERMES_HOME=${RuntimePaths.HERMES_HOME_IN_ROOTFS}",
            "ARKAX_NATIVE=1",
            "PROOT_TMP_DIR=${tmp.absolutePath}",
            "TMPDIR=/tmp",
            "UV_CACHE_DIR=/root/.cache/uv"
        )
        // PROOT_LOADER dibaca oleh proses proot ITU SENDIRI (lihat exec():
        // diisi di ProcessBuilder.environment), bukan oleh env -i di dalam rootfs.
        cmd += listOf("/bin/bash", "${RuntimePaths.RUNTIME_IN_ROOTFS}/entrypoint.sh")
        cmd += inner
        return cmd
    }

    /**
     * @param timeoutMs 0 = tunggu sampai selesai (dipakai streaming chat).
     * @param onStdout dipanggil per baris, cocok untuk SSE.
     */
    fun exec(
        inner: List<String>,
        stdin: String? = null,
        timeoutMs: Long = 120_000,
        onStdout: ((String) -> Unit)? = null,
        onStderr: ((String) -> Unit)? = null,
        interrupt: (() -> Boolean)? = null
    ): Result {
        val started = System.currentTimeMillis()
        val command = buildCommand(inner)
        val pb = ProcessBuilder(command)
            .directory(RuntimePaths.base(context))
            .redirectErrorStream(false)
        pb.environment()["PROOT_TMP_DIR"] = RuntimePaths.tmp(context).absolutePath
        // libproot.so Termux membutuhkan libtalloc.so.2 + libandroid-shmem.so
        // yang ikut dibundel di direktori native library yang sama.
        pb.environment()["LD_LIBRARY_PATH"] = context.applicationInfo.nativeLibraryDir
        RuntimePaths.prootLoader(context)?.let {
            pb.environment()["PROOT_LOADER"] = it
        }

        val process = try {
            pb.start()
        } catch (e: Exception) {
            Log.e(TAG, "gagal start proot: ${command.first()}", e)
            return Result("", " Gagal menjalankan proot: ${e.message}", 127,
                System.currentTimeMillis() - started)
        }

        process.outputStream.use { os ->
            if (stdin != null) {
                try { os.write(stdin.toByteArray(Charsets.UTF_8)); os.flush() }
                catch (e: Exception) { Log.w(TAG, "stdin gagal: ${e.message}") }
            }
        }

        val out = StringBuilder()
        val err = StringBuilder()
        val tOut = Thread {
            try {
                process.inputStream.bufferedReader(Charsets.UTF_8).forEachLine { line ->
                    out.appendLine(line)
                    onStdout?.invoke(line)
                }
            } catch (e: Exception) { Log.w(TAG, "stdout reader: ${e.message}") }
        }.apply { isDaemon = true; start() }
        val tErr = Thread {
            try {
                process.errorStream.bufferedReader(Charsets.UTF_8).forEachLine { line ->
                    err.appendLine(line)
                    onStderr?.invoke(line)
                }
            } catch (e: Exception) { Log.w(TAG, "stderr reader: ${e.message}") }
        }.apply { isDaemon = true; start() }

        var exit = 1
        try {
            if (timeoutMs > 0) {
                val finished = process.waitFor(timeoutMs, TimeUnit.MILLISECONDS)
                if (!finished) {
                    process.destroy()
                    Thread.sleep(1500)
                    if (process.isAlive) process.destroyForcibly()
                    err.appendLine("ARKAX: timeout setelah ${timeoutMs}ms")
                }
            } else {
                // Polling ringan supaya tombol Stop bisa menghentikan streaming chat.
                while (process.isAlive) {
                    if (interrupt?.invoke() == true) {
                        process.destroy()
                        Thread.sleep(1000)
                        if (process.isAlive) process.destroyForcibly()
                        err.appendLine("ARKAX: dihentikan pengguna")
                        break
                    }
                    Thread.sleep(120)
                }
            }
            exit = try { process.exitValue() } catch (e: Exception) { 1 }
        } catch (e: InterruptedException) {
            process.destroyForcibly()
            err.appendLine("ARKAX: thread diinterupsi")
        } finally {
            tOut.join(3000)
            tErr.join(3000)
        }
        return Result(out.toString(), err.toString(), exit, System.currentTimeMillis() - started)
    }

    /** Perintah shell bebas (dipakai layar Terminal). */
    fun shell(script: String, onStdout: ((String) -> Unit)? = null,
              onStderr: ((String) -> Unit)? = null, timeoutMs: Long = 180_000): Result =
        exec(listOf("/bin/bash", "-lc", script), onStdout = onStdout, onStderr = onStderr,
            timeoutMs = timeoutMs)

    /** Pseudo-TTY untuk `hermes --tui` (Java ProcessBuilder tidak punya PTY). */
    fun tty(script: String, onStdout: ((String) -> Unit)? = null): Result =
        exec(listOf("/usr/bin/script", "-q", "-c", script, "/dev/null"),
            onStdout = onStdout, timeoutMs = 0)

    companion object {
        private const val TAG = "ProotRuntime"
    }
}
