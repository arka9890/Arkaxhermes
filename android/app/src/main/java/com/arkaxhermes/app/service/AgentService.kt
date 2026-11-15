package com.arkaxhermes.app.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.IBinder
import android.os.PowerManager
import com.arkaxhermes.app.MainActivity
import com.arkaxhermes.app.R
import com.arkaxhermes.app.bridge.EventBus
import com.arkaxhermes.app.runtime.HermesRuntime
import org.json.JSONObject
import kotlin.concurrent.thread

/**
 * Menjaga proses panjang Hermes (gateway, cron ticker, dashboard, webhook)
 * tetap hidup dengan notifikasi ongoing + wake lock. Android tetap dapat
 * membunuhnya; status selalu dilaporkan apa adanya lewat EventBus.
 */
class AgentService : Service() {

    private var wakeLock: PowerManager.WakeLock? = null

    override fun onCreate() {
        super.onCreate()
        createChannel()
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "Arkaxhermes:AgentService").apply {
            setReferenceCounted(false)
            acquire(12 * 60 * 60 * 1000L)
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val allowedNames = listOf("gateway", "cron", "dashboard", "webhook", "all")
        val allowedActions = listOf("start", "stop", "restart", "status")
        val name = intent?.getStringExtra("name").takeIf { it in allowedNames } ?: "gateway"
        val action = intent?.getStringExtra("action").takeIf { it in allowedActions } ?: "start"
        startForeground(NOTIFICATION_ID, buildNotification(name, action))

        thread(name = "arkax-service-$name", isDaemon = true) {
            ServiceState.set(name, if (action == "stop") "stopping" else "starting")
            // argv array (bukan string shell) agar nilai dari Intent tidak bisa disuntik.
            val result = HermesRuntime(this).proot.exec(
                listOf("/bin/bash", "/opt/arkax/services.sh", action, name),
                onStdout = { line -> EventBus.log("[$name] $line") },
                onStderr = { line -> EventBus.log("[$name:err] $line") },
                timeoutMs = 120_000
            )
            val state = when {
                result.exit != 0 -> "error"
                action == "stop" -> "stopped"
                else -> "running"
            }
            ServiceState.set(name, state, result.stdout.trim().takeLast(240))
            EventBus.publish("service-result", JSONObject()
                .put("name", name).put("action", action).put("state", state)
                .put("stdout", result.stdout.trim().takeLast(4000))
                .put("stderr", result.stderr.trim().takeLast(4000)))
            startForeground(NOTIFICATION_ID, buildNotification(name, state))
            if (action == "stop" && !ServiceState.anyRunning()) stopSelf()
        }
        return START_STICKY
    }

    private fun createChannel() {
        val manager = getSystemService(NotificationManager::class.java)
        val channel = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.notification_channel),
            NotificationManager.IMPORTANCE_LOW
        ).apply { description = getString(R.string.notification_channel_desc) }
        manager.createNotificationChannel(channel)
    }

    private fun buildNotification(name: String, state: String): Notification {
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        return Notification.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(getString(R.string.notification_title))
            .setContentText("$name: $state · ${getString(R.string.app_subtitle)}")
            .setContentIntent(open)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .build()
    }

    override fun onDestroy() {
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    companion object {
        const val CHANNEL_ID = "arkax_services"
        const val NOTIFICATION_ID = 4242
    }
}
