package com.lidltool.androidharness

import android.content.Context
import android.os.Build
import java.util.UUID

class SessionStore(context: Context) {
    private val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    val deviceId: String
        get() {
            val existing = prefs.getString(KEY_DEVICE_ID, null)
            if (!existing.isNullOrBlank()) {
                return existing
            }
            val generated = UUID.randomUUID().toString()
            prefs.edit().putString(KEY_DEVICE_ID, generated).apply()
            return generated
        }

    val deviceName: String
        get() = listOf(Build.MANUFACTURER, Build.MODEL)
            .filter { it.isNotBlank() }
            .joinToString(" ")
            .ifBlank { "Android phone" }

    var languageTag: String
        get() = prefs.getString(KEY_LANGUAGE_TAG, AppLanguage.English.tag) ?: AppLanguage.English.tag
        set(value) {
            prefs.edit().putString(KEY_LANGUAGE_TAG, value).apply()
        }

    companion object {
        private const val PREFS_NAME = "lidltool_companion_device"
        private const val KEY_DEVICE_ID = "device_id"
        private const val KEY_LANGUAGE_TAG = "language_tag"
    }
}
