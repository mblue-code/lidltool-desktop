package com.lidltool.androidharness

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import java.util.UUID

/**
 * Persistence foundation for the local-first desktop companion.
 *
 * This intentionally uses SQLiteOpenHelper instead of Room to avoid widening
 * Gradle/plugin risk in the vendored harness while the native refit is still
 * stabilizing. Tables are shaped so they can be migrated to Room later without
 * changing the app-level model.
 */
class MobilePersistence(context: Context) : SQLiteOpenHelper(context, DB_NAME, null, DB_VERSION) {
    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE pairing_state (
                id TEXT PRIMARY KEY,
                desktop_id TEXT NOT NULL,
                desktop_name TEXT NOT NULL,
                endpoint_url TEXT NOT NULL,
                public_key_fingerprint TEXT NOT NULL,
                paired_device_id TEXT NOT NULL,
                sync_token TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """.trimIndent(),
        )
        db.execSQL(
            """
            CREATE TABLE sync_metadata (
                id TEXT PRIMARY KEY,
                cursor TEXT,
                server_time TEXT,
                last_success_at TEXT,
                pending_capture_count INTEGER NOT NULL DEFAULT 0
            )
            """.trimIndent(),
        )
        db.execSQL(
            """
            CREATE TABLE capture_queue (
                id TEXT PRIMARY KEY,
                file_name TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size_bytes INTEGER NOT NULL,
                sha256 TEXT,
                status TEXT NOT NULL,
                note TEXT,
                desktop_capture_id TEXT,
                transaction_id TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """.trimIndent(),
        )
        db.execSQL(
            """
            CREATE TABLE transactions (
                id TEXT PRIMARY KEY,
                purchased_at TEXT NOT NULL,
                merchant_name TEXT,
                total_gross_cents INTEGER NOT NULL,
                currency TEXT NOT NULL,
                category TEXT,
                needs_review INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT
            )
            """.trimIndent(),
        )
        db.execSQL(
            """
            CREATE TABLE transaction_items (
                id TEXT PRIMARY KEY,
                transaction_id TEXT NOT NULL,
                name TEXT NOT NULL,
                quantity REAL,
                line_total_cents INTEGER NOT NULL,
                category TEXT,
                FOREIGN KEY(transaction_id) REFERENCES transactions(id) ON DELETE CASCADE
            )
            """.trimIndent(),
        )
        db.execSQL(
            """
            CREATE TABLE budget_summary (
                id TEXT PRIMARY KEY,
                period_label TEXT NOT NULL,
                spent_cents INTEGER NOT NULL,
                budget_cents INTEGER NOT NULL,
                currency TEXT NOT NULL,
                updated_at TEXT
            )
            """.trimIndent(),
        )
        db.insert(
            "sync_metadata",
            null,
            ContentValues().apply {
                put("id", SINGLETON_ID)
                putNull("cursor")
                putNull("server_time")
                putNull("last_success_at")
                put("pending_capture_count", 0)
            },
        )
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        db.execSQL("DROP TABLE IF EXISTS transaction_items")
        db.execSQL("DROP TABLE IF EXISTS transactions")
        db.execSQL("DROP TABLE IF EXISTS capture_queue")
        db.execSQL("DROP TABLE IF EXISTS sync_metadata")
        db.execSQL("DROP TABLE IF EXISTS pairing_state")
        db.execSQL("DROP TABLE IF EXISTS budget_summary")
        onCreate(db)
    }

    fun loadPairing(): StoredPairing? {
        readableDatabase.query(
            "pairing_state",
            null,
            "id = ?",
            arrayOf(SINGLETON_ID),
            null,
            null,
            null,
            "1",
        ).use { cursor ->
            if (!cursor.moveToFirst()) return null
            return StoredPairing(
                desktopId = cursor.string("desktop_id"),
                desktopName = cursor.string("desktop_name"),
                endpointUrl = cursor.string("endpoint_url"),
                publicKeyFingerprint = cursor.string("public_key_fingerprint"),
                pairedDeviceId = cursor.string("paired_device_id"),
                syncToken = cursor.string("sync_token"),
                issuedAt = cursor.string("issued_at"),
                expiresAt = cursor.string("expires_at"),
            )
        }
    }

    fun savePairing(pairing: StoredPairing) {
        writableDatabase.replace(
            "pairing_state",
            null,
            ContentValues().apply {
                put("id", SINGLETON_ID)
                put("desktop_id", pairing.desktopId)
                put("desktop_name", pairing.desktopName)
                put("endpoint_url", pairing.endpointUrl)
                put("public_key_fingerprint", pairing.publicKeyFingerprint)
                put("paired_device_id", pairing.pairedDeviceId)
                put("sync_token", pairing.syncToken)
                put("issued_at", pairing.issuedAt)
                put("expires_at", pairing.expiresAt)
                put("created_at", nowIso())
            },
        )
    }

    fun clearPairing() {
        writableDatabase.delete("pairing_state", "id = ?", arrayOf(SINGLETON_ID))
    }

    fun loadSyncMetadata(): SyncMetadata {
        readableDatabase.query(
            "sync_metadata",
            null,
            "id = ?",
            arrayOf(SINGLETON_ID),
            null,
            null,
            null,
            "1",
        ).use { cursor ->
            if (!cursor.moveToFirst()) return SyncMetadata()
            return SyncMetadata(
                cursor = cursor.stringOrNull("cursor"),
                serverTime = cursor.stringOrNull("server_time"),
                lastSuccessAt = cursor.stringOrNull("last_success_at"),
                pendingCaptureCount = cursor.int("pending_capture_count"),
            )
        }
    }

    fun saveSyncMetadata(metadata: SyncMetadata) {
        writableDatabase.replace(
            "sync_metadata",
            null,
            ContentValues().apply {
                put("id", SINGLETON_ID)
                put("cursor", metadata.cursor)
                put("server_time", metadata.serverTime)
                put("last_success_at", metadata.lastSuccessAt)
                put("pending_capture_count", metadata.pendingCaptureCount)
            },
        )
    }

    fun insertCapture(capture: CaptureQueueEntry) {
        writableDatabase.insert(
            "capture_queue",
            null,
            capture.toValues(),
        )
    }

    fun updateCapture(capture: CaptureQueueEntry) {
        writableDatabase.update(
            "capture_queue",
            capture.toValues(),
            "id = ?",
            arrayOf(capture.id),
        )
    }

    fun loadCaptures(): List<CaptureQueueEntry> {
        readableDatabase.query("capture_queue", null, null, null, null, null, "created_at DESC").use { cursor ->
            val captures = mutableListOf<CaptureQueueEntry>()
            while (cursor.moveToNext()) {
                captures += CaptureQueueEntry(
                    id = cursor.string("id"),
                    fileName = cursor.string("file_name"),
                    mimeType = cursor.string("mime_type"),
                    filePath = cursor.string("file_path"),
                    fileSizeBytes = cursor.long("file_size_bytes"),
                    sha256 = cursor.stringOrNull("sha256"),
                    status = CaptureStatus.valueOf(cursor.string("status")),
                    note = cursor.stringOrNull("note"),
                    desktopCaptureId = cursor.stringOrNull("desktop_capture_id"),
                    transactionId = cursor.stringOrNull("transaction_id"),
                    error = cursor.stringOrNull("error"),
                    createdAt = cursor.string("created_at"),
                    updatedAt = cursor.string("updated_at"),
                )
            }
            return captures
        }
    }

    fun upsertSyncChanges(response: MobileSyncChangesResponse) {
        writableDatabase.beginTransaction()
        try {
            response.transactions.forEach { transaction ->
                writableDatabase.replace(
                    "transactions",
                    null,
                    ContentValues().apply {
                        put("id", transaction.id)
                        put("purchased_at", transaction.purchasedAt)
                        put("merchant_name", transaction.merchantName)
                        put("total_gross_cents", transaction.totalGrossCents)
                        put("currency", transaction.currency)
                        put("category", transaction.category)
                        put("needs_review", if (transaction.needsReview) 1 else 0)
                        put("updated_at", transaction.updatedAt)
                    },
                )
            }
            response.transactionItems.forEach { item ->
                writableDatabase.replace(
                    "transaction_items",
                    null,
                    ContentValues().apply {
                        put("id", item.id)
                        put("transaction_id", item.transactionId)
                        put("name", item.name)
                        put("quantity", item.quantity)
                        put("line_total_cents", item.lineTotalCents)
                        put("category", item.category)
                    },
                )
            }
            response.budgetSummary?.let { budget ->
                writableDatabase.replace(
                    "budget_summary",
                    null,
                    ContentValues().apply {
                        put("id", SINGLETON_ID)
                        put("period_label", budget.periodLabel)
                        put("spent_cents", budget.spentCents)
                        put("budget_cents", budget.budgetCents)
                        put("currency", budget.currency)
                        put("updated_at", budget.updatedAt)
                    },
                )
            }
            response.captureStatuses.forEach { status ->
                val values = ContentValues().apply {
                    put("status", status.status.name)
                    put("desktop_capture_id", status.desktopCaptureId)
                    put("transaction_id", status.transactionId)
                    put("error", status.error)
                    put("updated_at", nowIso())
                }
                writableDatabase.update("capture_queue", values, "id = ?", arrayOf(status.mobileCaptureId))
            }
            val pending = loadCaptures().count { it.status == CaptureStatus.LOCAL_ONLY || it.status == CaptureStatus.QUEUED_FOR_UPLOAD }
            saveSyncMetadata(
                SyncMetadata(
                    cursor = response.cursor,
                    serverTime = response.serverTime,
                    lastSuccessAt = nowIso(),
                    pendingCaptureCount = pending,
                ),
            )
            writableDatabase.setTransactionSuccessful()
        } finally {
            writableDatabase.endTransaction()
        }
    }

    fun loadTransactions(): List<MobileTransaction> {
        readableDatabase.query("transactions", null, null, null, null, null, "purchased_at DESC", "80").use { cursor ->
            val transactions = mutableListOf<MobileTransaction>()
            while (cursor.moveToNext()) {
                transactions += MobileTransaction(
                    id = cursor.string("id"),
                    purchasedAt = cursor.string("purchased_at"),
                    merchantName = cursor.stringOrNull("merchant_name"),
                    totalGrossCents = cursor.int("total_gross_cents"),
                    currency = cursor.string("currency"),
                    category = cursor.stringOrNull("category"),
                    needsReview = cursor.int("needs_review") == 1,
                    updatedAt = cursor.stringOrNull("updated_at"),
                )
            }
            return transactions
        }
    }

    fun loadBudgetSummary(): MobileBudgetSummary? {
        readableDatabase.query(
            "budget_summary",
            null,
            "id = ?",
            arrayOf(SINGLETON_ID),
            null,
            null,
            null,
            "1",
        ).use { cursor ->
            if (!cursor.moveToFirst()) return null
            return MobileBudgetSummary(
                periodLabel = cursor.string("period_label"),
                spentCents = cursor.int("spent_cents"),
                budgetCents = cursor.int("budget_cents"),
                currency = cursor.string("currency"),
                updatedAt = cursor.stringOrNull("updated_at"),
            )
        }
    }

    private fun CaptureQueueEntry.toValues(): ContentValues {
        return ContentValues().apply {
            put("id", id)
            put("file_name", fileName)
            put("mime_type", mimeType)
            put("file_path", filePath)
            put("file_size_bytes", fileSizeBytes)
            put("sha256", sha256)
            put("status", status.name)
            put("note", note)
            put("desktop_capture_id", desktopCaptureId)
            put("transaction_id", transactionId)
            put("error", error)
            put("created_at", createdAt)
            put("updated_at", updatedAt)
        }
    }

    companion object {
        private const val DB_NAME = "lidltool_mobile_companion.db"
        private const val DB_VERSION = 1
        const val SINGLETON_ID = "primary"

        fun newCaptureId(): String = UUID.randomUUID().toString()
    }
}

private fun android.database.Cursor.string(column: String): String = getString(getColumnIndexOrThrow(column))
private fun android.database.Cursor.stringOrNull(column: String): String? = getString(getColumnIndexOrThrow(column))
private fun android.database.Cursor.int(column: String): Int = getInt(getColumnIndexOrThrow(column))
private fun android.database.Cursor.long(column: String): Long = getLong(getColumnIndexOrThrow(column))
