package com.arkaxhermes.app.runtime

import android.content.Context
import android.util.Log
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest

/**
 * Mengunduh Chrome for Testing saat Browser pertama kali dibutuhkan.
 *
 * APK sengaja tidak membundel ZIP 128 MB. URL + SHA-256 dibaca dari
 * assets/manifest.json (disalin dari rootfs/manifest.json saat build APK),
 * jadi sumber versi Chrome selalu sinkron dengan repo.
 */
object ChromeDownloader {
    private const val TAG = "ChromeDownloader"

    private fun manifestChrome(context: Context): JSONObject? = try {
        val json = context.assets.open("manifest.json").bufferedReader().use { it.readText() }
        JSONObject(json).optJSONObject("chrome")
    } catch (e: Exception) {
        Log.w(TAG, "manifest.json tidak ada atau tidak terbaca: ${e.message}")
        null
    }

    /** Kembalikan (berhasil, pesan) setelah mengunduh ZIP ke dest dan memverifikasi checksum. */
    fun download(context: Context, dest: File): Pair<Boolean, String> {
        val chrome = manifestChrome(context)
            ?: return false to "Manifest Chrome tidak ditemukan"
        val url = chrome.optString("url", "")
        val expectedSha = chrome.optString("sha256", "")
        if (url.isBlank() || expectedSha.isBlank()) {
            return false to "Manifest Chrome tidak lengkap (url/sha256 kosong)"
        }
        dest.parentFile?.mkdirs()
        val tmp = File(dest.parentFile, dest.name + ".part")
        Log.i(TAG, "Mengunduh Chrome dari $url")
        return try {
            java.net.URL(url).openStream().use { input ->
                FileOutputStream(tmp).use { out ->
                    val buf = ByteArray(256 * 1024)
                    while (true) {
                        val n = input.read(buf)
                        if (n <= 0) break
                        out.write(buf, 0, n)
                    }
                }
            }
            val md = MessageDigest.getInstance("SHA-256")
            tmp.inputStream().use { fis ->
                val buf = ByteArray(128 * 1024)
                while (true) {
                    val n = fis.read(buf)
                    if (n <= 0) break
                    md.update(buf, 0, n)
                }
            }
            val actual = md.digest().joinToString("") { "%02x".format(it) }
            if (actual != expectedSha) {
                tmp.delete()
                return false to "Checksum tidak cocok (expected $expectedSha, got $actual)"
            }
            if (!tmp.renameTo(dest)) {
                tmp.delete()
                return false to "Gagal memindahkan hasil unduhan"
            }
            Log.i(TAG, "Chrome terunduh dan terverifikasi: ${dest.name}")
            true to "Chrome siap"
        } catch (e: Exception) {
            tmp.delete()
            Log.e(TAG, "unduhan Chrome gagal", e)
            false to (e.message ?: e.javaClass.simpleName)
        }
    }
}