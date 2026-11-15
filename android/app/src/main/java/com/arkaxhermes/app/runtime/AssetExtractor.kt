package com.arkaxhermes.app.runtime

import android.content.Context
import android.util.Log
import java.io.File
import java.io.FileOutputStream

/** Menyalin aset runtime (skrip shell/python) ke filesDir agar bisa di-bind ke /opt/arkax. */
object AssetExtractor {
    private const val TAG = "AssetExtractor"

    fun extractAsset(context: Context, assetPath: String, destination: File): Boolean {
        return try {
            destination.parentFile?.mkdirs()
            context.assets.open(assetPath).use { input ->
                FileOutputStream(destination).use { output -> input.copyTo(output, 64 * 1024) }
            }
            true
        } catch (e: Exception) {
            Log.w(TAG, "aset tidak ada: $assetPath (${e.message})")
            false
        }
    }

    private fun listRecursive(context: Context, path: String): List<String> {
        val result = mutableListOf<String>()
        val entries = try { context.assets.list(path)?.toList() ?: emptyList() } catch (e: Exception) { emptyList() }
        if (entries.isEmpty()) {
            result += path
        } else {
            for (entry in entries) {
                val child = if (path.isEmpty()) entry else "$path/$entry"
                result += listRecursive(context, child)
            }
        }
        return result
    }

    /** Ekstrak seluruh assets/runtime/ → filesDir/arkax/runtime/ */
    fun extractRuntime(context: Context): Int {
        RuntimePaths.ensure(context)
        var count = 0
        for (asset in listRecursive(context, "runtime")) {
            val relative = asset.removePrefix("runtime/")
            if (relative == asset || relative.endsWith(".md") || relative.endsWith("/")) continue
            val dest = File(RuntimePaths.scripts(context), relative)
            if (extractAsset(context, asset, dest)) {
                if (relative.endsWith(".sh") || relative.endsWith(".py")) {
                    @Suppress("unused")
                    dest.setExecutable(true, false)
                }
                count++
            }
        }
        Log.i(TAG, "$count berkas runtime diekstrak ke ${RuntimePaths.scripts(context)}")
        return count
    }
}
