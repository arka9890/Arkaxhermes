package com.arkaxhermes.app

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import com.arkaxhermes.app.runtime.RuntimePaths
import com.arkaxhermes.app.service.AgentService

class ArkaxApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        RuntimePaths.ensure(this)
        val channel = NotificationChannel(
            AgentService.CHANNEL_ID,
            getString(R.string.notification_channel),
            NotificationManager.IMPORTANCE_LOW
        ).apply { description = getString(R.string.notification_channel_desc) }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }
}
