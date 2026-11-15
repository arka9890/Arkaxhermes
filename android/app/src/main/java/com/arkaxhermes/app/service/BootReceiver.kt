package com.arkaxhermes.app.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.content.ContextCompat
import com.arkaxhermes.app.data.SettingsStore

/** Nyalakan kembali layanan yang ditandai autostart setelah boot / update APK. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED &&
            intent.action != Intent.ACTION_MY_PACKAGE_REPLACED) return
        val settings = SettingsStore(context)
        listOf("gateway", "cron", "dashboard", "webhook")
            .filter { settings.serviceEnabled(it) }
            .forEach { name ->
                val i = Intent(context, AgentService::class.java)
                    .putExtra("name", name)
                    .putExtra("action", "start")
                ContextCompat.startForegroundService(context, i)
            }
    }
}
