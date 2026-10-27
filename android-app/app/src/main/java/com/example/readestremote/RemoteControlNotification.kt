package com.example.readestremote

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.widget.Toast
import android.widget.RemoteViews
import java.net.HttpURLConnection
import java.net.URL
import java.security.KeyStore
import java.util.concurrent.Executors
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import org.json.JSONObject

internal object RemoteControlNotification {
    const val NOTIFICATION_ID = 18765
    private const val CHANNEL_ID = "reading_controls"
    private const val PREFS = "remote_settings"
    private const val KEY_HOST = "host"
    private const val KEY_PORT = "port"
    private const val KEY_SECRET = "secret_encrypted"
    private const val KEY_MODE = "reading_mode"
    private const val KEY_PINNED = "notification_pinned"

    fun show(context: Context, mode: String) {
        val manager = context.getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 33 && context.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        if (Build.VERSION.SDK_INT >= 26) {
            manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, "Reading controls", NotificationManager.IMPORTANCE_LOW).apply {
                description = "Pinned controls for Readest on your laptop"
                setShowBadge(false)
            })
        }
        val title = "Readest Remote · ${modeLabel(mode)}"
        val openIntent = PendingIntent.getActivity(
            context, 0, Intent(context, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = Notification.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_reading_mode)
            .setContentTitle(title)
            .setContentText("Use the controls here while Readest stays open on your laptop")
            .setContentIntent(openIntent)
            .setCategory(Notification.CATEGORY_STATUS)
            .setVisibility(Notification.VISIBILITY_PUBLIC)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setShowWhen(false)
            .setColor(0xff2664ce.toInt())
            .setStyle(Notification.DecoratedCustomViewStyle())
            .setCustomContentView(controlView(context, mode, expanded = false))
            .setCustomBigContentView(controlView(context, mode, expanded = true))
            .build()
        try {
            manager.notify(NOTIFICATION_ID, notification)
        } catch (_: SecurityException) {
            // Notification permission may have been revoked while the app was backgrounded.
        }
    }

    private data class Control(val label: String, val icon: Int, val command: String)

    private fun modeControls(mode: String): List<Control> {
        val controls = when (mode) {
            "autoscroll" -> listOf(
                Control("Slower", android.R.drawable.ic_media_rew, "autoscroll_slower"),
                Control("Pause / play", android.R.drawable.ic_media_pause, "autoscroll_pause"),
                Control("Faster", android.R.drawable.ic_media_ff, "autoscroll_faster"),
                Control("Previous page", android.R.drawable.ic_media_previous, "previous"),
                Control("Next page", android.R.drawable.ic_media_next, "next"),
            )
            "speed" -> listOf(
                Control("Slower", android.R.drawable.ic_media_rew, "speed_slower"),
                Control("Pause / play", android.R.drawable.ic_media_pause, "speed_pause"),
                Control("Faster", android.R.drawable.ic_media_ff, "speed_faster"),
                Control("Previous page", android.R.drawable.ic_media_previous, "rsvp_previous"),
                Control("Next page", android.R.drawable.ic_media_next, "rsvp_next"),
            )
            "tts" -> listOf(
                Control("Previous sentence", android.R.drawable.ic_media_previous, "tts_previous"),
                Control("Pause / play", android.R.drawable.ic_media_pause, "tts_pause"),
                Control("Next sentence", android.R.drawable.ic_media_next, "tts_next"),
                Control("Stop TTS", android.R.drawable.ic_menu_close_clear_cancel, "tts_close"),
            )
            else -> listOf(
                Control("Previous page", android.R.drawable.ic_media_previous, "previous"),
                Control("Next page", android.R.drawable.ic_media_next, "next"),
                Control("Previous chapter", android.R.drawable.ic_media_rew, "previous_chapter"),
                Control("Next chapter", android.R.drawable.ic_media_ff, "next_chapter"),
            )
        }
        return controls + listOf(
            Control("Full screen", R.drawable.ic_fullscreen, "fullscreen"),
            Control("Start Readest", android.R.drawable.ic_media_play, "launch_readest"),
            Control("Close Readest", android.R.drawable.ic_menu_close_clear_cancel, "close_readest"),
        )
    }

    private fun controlView(context: Context, mode: String, expanded: Boolean): RemoteViews {
        val controls = modeControls(mode)
        val view = RemoteViews(context.packageName, if (expanded) R.layout.notification_controls_expanded else R.layout.notification_controls_compact)
        val ids = if (expanded) listOf(
            R.id.control_0, R.id.control_1, R.id.control_2, R.id.control_3,
            R.id.control_4, R.id.control_5, R.id.control_6, R.id.control_7,
        ) else listOf(R.id.control_0, R.id.control_1, R.id.control_2, R.id.control_3, R.id.control_4)
        val iconIds = if (expanded) listOf(
            R.id.control_icon_0, R.id.control_icon_1, R.id.control_icon_2, R.id.control_icon_3,
            R.id.control_icon_4, R.id.control_icon_5, R.id.control_icon_6, R.id.control_icon_7,
        ) else listOf(R.id.control_icon_0, R.id.control_icon_1, R.id.control_icon_2, R.id.control_icon_3, R.id.control_icon_4)
        val labelIds = if (expanded) listOf(
            R.id.control_label_0, R.id.control_label_1, R.id.control_label_2, R.id.control_label_3,
            R.id.control_label_4, R.id.control_label_5, R.id.control_label_6, R.id.control_label_7,
        ) else listOf(R.id.control_label_0, R.id.control_label_1, R.id.control_label_2, R.id.control_label_3, R.id.control_label_4)
        for (index in ids.indices) {
            val control = controls.getOrNull(index)
            view.setViewVisibility(ids[index], if (control == null) android.view.View.INVISIBLE else android.view.View.VISIBLE)
            if (control == null) continue
            view.setImageViewResource(iconIds[index], control.icon)
            view.setTextViewText(labelIds[index], control.label)
            view.setContentDescription(ids[index], control.label)
            val intent = Intent(context, NotificationControlReceiver::class.java)
                .setAction("com.example.readestremote.CONTROL")
                .putExtra("command", control.command)
            val pending = PendingIntent.getBroadcast(
                context, control.command.hashCode(), intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
            view.setOnClickPendingIntent(ids[index], pending)
        }
        return view
    }

    fun modeLabel(mode: String): String = when (mode) {
        "autoscroll" -> "Auto Scroll"
        "paragraph" -> "Paragraph"
        "speed" -> "Speed Reading"
        "tts" -> "Text to Speech"
        else -> "Normal"
    }
}

class NotificationControlReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val command = intent.getStringExtra("command") ?: return
        val pendingResult = goAsync()
        executor.execute {
            try {
                val prefs = context.getSharedPreferences("remote_settings", Context.MODE_PRIVATE)
                val host = prefs.getString("host", "") ?: ""
                val port = prefs.getString("port", "18765") ?: "18765"
                val encrypted = prefs.getString("secret_encrypted", null)
                val fingerprint = prefs.getString("receiver_fingerprint", "") ?: ""
                val deviceId = prefs.getString("device_id", "") ?: ""
                if (host.isBlank() || encrypted.isNullOrBlank() || fingerprint.isBlank() || deviceId.isBlank()) throw IllegalStateException("Pairing is not saved")
                val token = SecretVault.decrypt(encrypted)
                val conn = PinnedHttp.open(host, port.toIntOrNull() ?: 18765, fingerprint, "/turn").apply {
                    requestMethod = "POST"
                    connectTimeout = 3000
                    readTimeout = 3000
                    doOutput = true
                    setRequestProperty("Content-Type", "application/json")
                    setRequestProperty("X-Device-Token", token)
                    setRequestProperty("X-Device-Id", deviceId)
                }
                val body = JSONObject().put("action", command).toString().toByteArray(Charsets.UTF_8)
                conn.outputStream.use { it.write(body) }
                val response = conn.responseCode
                conn.disconnect()
                if (response == 200 && command in setOf("tts_close", "rsvp_previous", "rsvp_next", "rsvp_previous_chapter", "rsvp_next_chapter")) {
                    prefs.edit().putString("reading_mode", "normal").apply()
                    RemoteControlNotification.show(context, "normal")
                }
                if (response != 200) throw IllegalStateException("Receiver replied with HTTP $response")
            } catch (error: Exception) {
                android.os.Handler(context.mainLooper).post {
                    Toast.makeText(context, "Readest Remote: ${error.message ?: "Could not send control"}", Toast.LENGTH_SHORT).show()
                }
            } finally {
                pendingResult.finish()
            }
        }
    }

    companion object {
        private val executor = Executors.newCachedThreadPool()
    }
}

private object SecretVault {
    private const val KEY_ALIAS = "readest_remote_pairing_key"

    private fun secretKey(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(KeyGenParameterSpec.Builder(
            KEY_ALIAS,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
        ).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setRandomizedEncryptionRequired(true)
            .build())
        return generator.generateKey()
    }

    fun decrypt(value: String): String {
        val combined = android.util.Base64.decode(value, android.util.Base64.DEFAULT)
        val iv = combined.copyOfRange(0, 12)
        val encrypted = combined.copyOfRange(12, combined.size)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(128, iv))
        return String(cipher.doFinal(encrypted), Charsets.UTF_8)
    }
}
