package com.arkaxhermes.app.util

import android.os.Build
import org.json.JSONObject
import java.io.File

/** Metrik perangkat untuk kartu "Status Sistem & Sumber Daya" di Pengaturan. */
object SystemStats {
    fun snapshot(): JSONObject {
        val mem = memInfo()
        val totalMb = (mem.first / 1024).toInt().coerceAtLeast(1)
        val availableMb = (mem.second / 1024).toInt()
        val usedMb = (totalMb - availableMb).coerceAtLeast(0)
        return JSONObject()
            .put("cpuLoad", cpuLoadPercent())
            .put("cores", Runtime.getRuntime().availableProcessors())
            .put("ramUsedMb", usedMb)
            .put("ramTotalMb", totalMb)
            .put("tempC", thermalCelsius())
            .put("diskFreeMb", (File("/data").usableSpace / (1024 * 1024)).toInt())
            .put("device", Build.MODEL ?: "Android")
            .put("abi", Build.SUPPORTED_ABIS.firstOrNull() ?: "unknown")
            .put("sdk", Build.VERSION.SDK_INT)
    }

    private fun memInfo(): Pair<Long, Long> {
        var total = 0L
        var available = 0L
        try {
            File("/proc/meminfo").forEachLine { line ->
                when {
                    line.startsWith("MemTotal:") -> total = digits(line)
                    line.startsWith("MemAvailable:") -> available = digits(line)
                }
            }
        } catch (e: Exception) { /* abaikan */ }
        if (total == 0L) {
            val runtime = Runtime.getRuntime()
            total = runtime.maxMemory() / 1024
            available = (runtime.maxMemory() - (runtime.totalMemory() - runtime.freeMemory())) / 1024
        }
        return total to available
    }

    private fun digits(line: String): Long =
        Regex("(\\d+)").find(line)?.groupValues?.get(1)?.toLongOrNull() ?: 0L

    private fun cpuLoadPercent(): Int = try {
        val load = File("/proc/loadavg").readText().trim().split(" ")[0].toDoubleOrNull() ?: 0.0
        val cores = Runtime.getRuntime().availableProcessors().coerceAtLeast(1)
        ((load / cores) * 100).toInt().coerceIn(0, 100)
    } catch (e: Exception) {
        0
    }

    private fun thermalCelsius(): Float? {
        for (i in 0..8) {
            val f = File("/sys/class/thermal/thermal_zone$i/temp")
            if (!f.exists()) continue
            val raw = f.readText().trim().toDoubleOrNull() ?: continue
            val c = if (raw > 1000) raw / 1000.0 else raw
            if (c in 5.0..95.0) return c.toFloat()
        }
        return null
    }
}
