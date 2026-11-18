package com.arkaxhermes.app.runtime

import android.content.Context
import android.system.Os
import android.util.Log
import org.json.JSONObject
import java.io.BufferedInputStream
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.io.FilterInputStream
import java.io.InputStream
import java.io.OutputStream
import java.security.MessageDigest
import java.util.zip.GZIPInputStream

/**
 * Ekstrak Ubuntu rootfs yang dibundel di APK ke direktori privat aplikasi.
 *
 * Parser TAR/GZIP sengaja ditulis sendiri: `tar` tidak dijamin ada di Android,
 * dan proot belum bisa dipakai sebelum rootfs tersedia. Mendukung ustar,
 * GNU longname, PAX path, symlink, hardlink, dan mode bit.
 */
object RootfsInstaller {
    private const val TAG = "RootfsInstaller"
    private const val BLOCK = 512

    fun isInstalled(context: Context): Boolean = RuntimePaths.readyMarker(context).exists()

    private fun assetExists(context: Context, path: String): Boolean = try {
        context.assets.open(path).use { true }
    } catch (e: Exception) {
        false
    }

    private fun sha256(file: File): String {
        val md = MessageDigest.getInstance("SHA-256")
        FileInputStream(file).use { fis ->
            val buf = ByteArray(128 * 1024)
            while (true) {
                val n = fis.read(buf)
                if (n < 0) break
                md.update(buf, 0, n)
            }
        }
        return md.digest().joinToString("") { "%02x".format(it) }
    }

    private fun assembleArchive(context: Context, emit: (String, JSONObject) -> Unit): File? {
        val parts = try {
            context.assets.list("rootfs")?.filter { it.startsWith("ubuntu-rootfs.tar.gz.part") }?.sorted()
                ?: emptyList()
        } catch (e: Exception) {
            emptyList()
        }
        val archive = RuntimePaths.rootfsArchive(context)
        archive.parentFile?.mkdirs()

        if (parts.isNotEmpty()) {
            emit("progress", JSONObject().put("step", "extract").put("percent", 3)
                .put("message", "Menggabungkan ${parts.size} bagian rootfs …"))
            FileOutputStream(archive).use { out ->
                parts.forEachIndexed { index, part ->
                    context.assets.open("rootfs/$part").use { it.copyTo(out, 128 * 1024) }
                    emit("progress", JSONObject().put("step", "extract").put("percent", 3 + index * 4 / parts.size)
                        .put("message", "Bagian ${index + 1}/${parts.size}"))
                }
            }
        } else if (assetExists(context, "rootfs/ubuntu-rootfs.tar.gz")) {
            emit("progress", JSONObject().put("step", "extract").put("percent", 5)
                .put("message", "Menyalin arsip rootfs …"))
            context.assets.open("rootfs/ubuntu-rootfs.tar.gz").use { input ->
                FileOutputStream(archive).use { out -> input.copyTo(out, 128 * 1024) }
            }
        } else {
            emit("error", JSONObject().put("message",
                "Arsip rootfs tidak dibundel. Jalankan scripts/make-assets.sh lalu build ulang APK."))
            return null
        }

        val expected = try {
            context.assets.open("rootfs/rootfs.sha256").bufferedReader().use { it.readText().trim() }
        } catch (e: Exception) {
            ""
        }
        if (expected.length == 64) {
            emit("log", JSONObject().put("line", "Memverifikasi SHA-256 rootfs …"))
            val actual = sha256(archive)
            if (!actual.equals(expected, ignoreCase = true)) {
                emit("error", JSONObject().put("message", "SHA-256 rootfs tidak cocok. Instalasi dihentikan."))
                archive.delete()
                return null
            }
            emit("log", JSONObject().put("line", "SHA-256 OK: $actual"))
        } else {
            emit("log", JSONObject().put("line", "Peringatan: rootfs.sha256 tidak ada, verifikasi dilewati (disarankan memperbaikinya)"))
        }
        return archive
    }

    fun install(context: Context, emit: (String, JSONObject) -> Unit): Boolean {
        RuntimePaths.ensure(context)
        AssetExtractor.extractRuntime(context)
        val root = RuntimePaths.rootfs(context)
        if (!root.exists()) root.mkdirs()

        val archive = assembleArchive(context, emit) ?: return false
        try {
            // Bersihkan sisa ekstraksi sebelumnya. Tanpa ini, berkas yang tadinya
            // regular file lalu menjadi direktori (atau sebaliknya) membuat
            // FileOutputStream/mkdirs melempar FileNotFoundException dan
            // ekstraksi gagal di tengah pada percobaan kedua.
            if (root.exists()) {
                val cleaned = root.deleteRecursively()
                if (!cleaned) emit("log", JSONObject().put("line",
                    "Peringatan: sebagian berkas lama gagal dihapus, ekstraksi melanjutkan"))
                root.mkdirs()
            }
            TarExtractor.extract(archive, root) { percent, message ->
                emit("progress", JSONObject().put("step", "extract").put("percent", 8 + (percent * 0.42).toInt())
                    .put("message", message))
            }
        } catch (e: Exception) {
            Log.e(TAG, "ekstraksi gagal", e)
            val detail = e.message ?: e.javaClass.simpleName
            emit("error", JSONObject().put("message", "Gagal mengekstrak rootfs: $detail"))
            return false
        } finally {
            archive.delete()
        }
        RuntimePaths.readyMarker(context).writeText("rootfs-extracted ${System.currentTimeMillis()}\n")
        emit("progress", JSONObject().put("step", "extract").put("percent", 50)
            .put("message", "Rootfs Ubuntu siap, menyiapkan Hermes …"))
        return true
    }

    private class CountingInputStream(input: InputStream) : FilterInputStream(input) {
        var count: Long = 0L
            private set
        override fun read(): Int {
            val v = super.read()
            if (v >= 0) count++
            return v
        }
        override fun read(b: ByteArray, off: Int, len: Int): Int {
            val n = super.read(b, off, len)
            if (n > 0) count += n
            return n
        }
    }

    private object TarExtractor {
        private fun readExactly(input: InputStream, size: Int): ByteArray? {
            val buf = ByteArray(size)
            var off = 0
            while (off < size) {
                val n = input.read(buf, off, size - off)
                if (n < 0) return if (off == 0) null else buf.copyOf(off)
                off += n
            }
            return buf
        }

        private fun copyExactly(input: InputStream, output: OutputStream, size: Long) {
            var remaining = size
            val buf = ByteArray(128 * 1024)
            while (remaining > 0) {
                val want = minOf(remaining, buf.size.toLong()).toInt()
                val n = input.read(buf, 0, want)
                if (n < 0) break
                output.write(buf, 0, n)
                remaining -= n
            }
        }

        private fun str(header: ByteArray, off: Int, len: Int): String {
            var end = off + len
            for (i in off until off + len) {
                if (header[i] == 0.toByte()) { end = i; break }
            }
            return String(header, off, end - off, Charsets.UTF_8)
        }

        private fun octal(header: ByteArray, off: Int, len: Int): Long {
            // Format base-256 GNU (bit 7 set) untuk ukuran sangat besar.
            if ((header[off].toInt() and 0x80) != 0) {
                var value = 0L
                for (i in off + 1 until off + len) value = (value shl 8) or (header[i].toLong() and 0xff)
                return value
            }
            val text = str(header, off, len).trim { it.isWhitespace() || it == '\u0000' }
            return text.toLongOrNull(8) ?: 0L
        }

        private fun padded(input: InputStream, size: Long) {
            val skip = ((BLOCK - (size % BLOCK)) % BLOCK)
            if (skip > 0) readExactly(input, skip.toInt())
        }

        private fun safeTarget(root: File, name: String): File {
            val cleaned = name.removePrefix("./").removePrefix("/")
            val rootCan = root.canonicalFile
            val target = File(root, cleaned).canonicalFile
            if (target != rootCan && !target.path.startsWith(rootCan.path + File.separator)) {
                throw SecurityException("path traversal ditolak: $name")
            }
            return target
        }

        fun extract(archive: File, root: File, onProgress: (Int, String) -> Unit) {
            val total = archive.length().coerceAtLeast(1)
            FileInputStream(archive).use { fis ->
                val counting = CountingInputStream(BufferedInputStream(fis))
                GZIPInputStream(counting).use { gz ->
                    var pendingName: String? = null
                    var entries = 0
                    while (true) {
                        val header = readExactly(gz, BLOCK) ?: break
                        if (header.all { it == 0.toByte() }) break

                        val rawName = pendingName ?: run {
                            val prefix = str(header, 345, 155)
                            val name = str(header, 0, 100)
                            if (prefix.isNotEmpty()) "$prefix/$name" else name
                        }
                        pendingName = null
                        val size = octal(header, 124, 12)
                        val mode = octal(header, 100, 8).toInt() and 0xfff
                        val type = header[156].toInt().toChar()
                        val linkName = str(header, 157, 100)

                        when (type) {
                            'L' -> { // GNU long name
                                val bytes = readExactly(gz, size.toInt()) ?: ByteArray(0)
                                pendingName = String(bytes, Charsets.UTF_8).trimEnd('\u0000', '\n')
                                padded(gz, size)
                                continue
                            }
                            'x', 'g' -> { // PAX extended header
                                val bytes = readExactly(gz, size.toInt()) ?: ByteArray(0)
                                val text = String(bytes, Charsets.UTF_8)
                                Regex("""\d+ path=([^\n]+)""").find(text)?.let {
                                    pendingName = it.groupValues[1].trim()
                                }
                                padded(gz, size)
                                continue
                            }
                            'K' -> { padded(gz, size); continue }
                        }

                        if (rawName.isBlank()) { padded(gz, size); continue }
                        val target = safeTarget(root, rawName)
                        when (type) {
                            '5' -> {
                                target.mkdirs()
                                padded(gz, size)
                            }
                            '2' -> {
                                target.parentFile?.mkdirs()
                                try {
                                    if (target.exists()) target.delete()
                                    Os.symlink(linkName, target.absolutePath)
                                } catch (e: Exception) {
                                    Log.w(TAG, "symlink gagal: ${target.name} → $linkName")
                                }
                                padded(gz, size)
                            }
                            '1' -> {
                                val source = safeTarget(root, linkName)
                                target.parentFile?.mkdirs()
                                if (source.exists()) {
                                    try { source.copyTo(target, overwrite = true) }
                                    catch (e: Exception) { Log.w(TAG, "hardlink → copy gagal: ${e.message}") }
                                }
                                padded(gz, size)
                            }
                            '0', '\u0000', '7' -> {
                                target.parentFile?.mkdirs()
                                try {
                                    FileOutputStream(target).use { out -> copyExactly(gz, out, size) }
                                } catch (e: Exception) {
                                    throw java.io.IOException(
                                        "menulis $rawName (${e.message ?: e.javaClass.simpleName})", e)
                                }
                                if (mode != 0) target.setExecutable((mode and 0x111) != 0, false)
                                padded(gz, size)
                            }
                            else -> padded(gz, size)
                        }

                        entries++
                        if (entries % 250 == 0) {
                            val percent = ((counting.count * 100) / total).toInt().coerceIn(0, 100)
                            onProgress(percent, "Menulis $rawName ($entries berkas)")
                        }
                    }
                    onProgress(100, "$entries berkas diekstrak")
                }
            }
        }
    }
}
