package com.lidltool.androidharness

import android.app.Application
import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import androidx.annotation.StringRes
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.documentfile.provider.DocumentFile
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import java.io.File
import java.security.MessageDigest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.Json

enum class HarnessTab(@StringRes val titleRes: Int) {
    Home(R.string.tab_home),
    Transactions(R.string.tab_transactions),
    Capture(R.string.tab_capture),
    Sync(R.string.tab_sync),
    Settings(R.string.tab_settings),
}

enum class AppLanguage(val tag: String) {
    English("en"),
    German("de");

    companion object {
        fun fromTag(tag: String?): AppLanguage {
            return entries.firstOrNull { it.tag == tag } ?: English
        }
    }
}

data class HarnessUiState(
    val pairing: StoredPairing? = null,
    val syncMetadata: SyncMetadata = SyncMetadata(),
    val selectedTab: HarnessTab = HarnessTab.Home,
    val pairingText: String = "",
    val pairingBusy: Boolean = false,
    val syncBusy: Boolean = false,
    val importBusy: Boolean = false,
    val manualBusy: Boolean = false,
    val manualMerchant: String = "",
    val manualAmount: String = "",
    val manualNote: String = "",
    val captures: List<CaptureQueueEntry> = emptyList(),
    val transactions: List<MobileTransaction> = emptyList(),
    val budgetSummary: MobileBudgetSummary? = null,
    val errorMessage: String? = null,
    val language: AppLanguage = AppLanguage.English,
)

class HarnessViewModel(application: Application) : AndroidViewModel(application) {
    private val sessionStore = SessionStore(application)
    private val store = MobilePersistence(application)

    var uiState by mutableStateOf(HarnessUiState())
        private set

    init {
        reloadLocalState()
    }

    fun selectTab(tab: HarnessTab) {
        uiState = uiState.copy(selectedTab = tab)
    }

    fun updatePairingText(value: String) {
        uiState = uiState.copy(pairingText = value)
    }

    fun updateManualMerchant(value: String) {
        uiState = uiState.copy(manualMerchant = value)
    }

    fun updateManualAmount(value: String) {
        uiState = uiState.copy(manualAmount = value)
    }

    fun updateManualNote(value: String) {
        uiState = uiState.copy(manualNote = value)
    }

    fun clearError() {
        uiState = uiState.copy(errorMessage = null)
    }

    fun setLanguage(language: AppLanguage) {
        sessionStore.languageTag = language.tag
        uiState = uiState.copy(language = language)
    }

    fun pairFromText() {
        pairFromPayload(uiState.pairingText)
    }

    fun pairFromPayload(rawPayload: String) {
        val raw = rawPayload.trim()
        if (raw.isBlank()) {
            uiState = uiState.copy(errorMessage = "Paste the QR pairing payload first.")
            return
        }
        uiState = uiState.copy(pairingText = raw, pairingBusy = true, errorMessage = null)
        viewModelScope.launch {
            try {
                val payload = decodePairingPayload(raw)
                require(payload.protocolVersion == 1) { "Unsupported pairing protocol ${payload.protocolVersion}" }
                val api = HarnessApi(payload.endpointUrl)
                val response = api.pairWithDesktop(
                    payload = payload,
                    request = PairingHandshakeRequest(
                        deviceId = sessionStore.deviceId,
                        deviceName = sessionStore.deviceName,
                        platform = "android",
                        pairingToken = payload.pairingToken,
                        publicKeyFingerprint = payload.publicKeyFingerprint,
                    ),
                )
                store.savePairing(
                    StoredPairing(
                        desktopId = response.desktopId,
                        desktopName = response.desktopName,
                        endpointUrl = response.endpointUrl,
                        publicKeyFingerprint = payload.publicKeyFingerprint,
                        pairedDeviceId = response.pairedDeviceId,
                        syncToken = response.syncToken,
                        issuedAt = response.issuedAt,
                        expiresAt = response.expiresAt,
                    ),
                )
                reloadLocalState(
                    uiState.copy(
                        pairingBusy = false,
                        pairingText = "",
                        selectedTab = HarnessTab.Home,
                    ),
                )
                syncNow()
            } catch (exc: Exception) {
                uiState = uiState.copy(
                    pairingBusy = false,
                    errorMessage = exc.message ?: "Pairing failed.",
                )
            }
        }
    }

    fun forgetPairing() {
        store.clearPairing()
        reloadLocalState(HarnessUiState())
    }

    fun importCapture(context: Context, uri: Uri) {
        uiState = uiState.copy(importBusy = true, errorMessage = null)
        viewModelScope.launch {
            try {
                val capture = withContext(Dispatchers.IO) { copyCaptureIntoAppStorage(context, uri) }
                store.insertCapture(capture)
                reloadLocalState(uiState.copy(importBusy = false, selectedTab = HarnessTab.Capture))
            } catch (exc: Exception) {
                uiState = uiState.copy(
                    importBusy = false,
                    errorMessage = exc.message ?: "Failed to import capture.",
                )
            }
        }
    }

    fun syncNow() {
        val pairing = store.loadPairing()
        if (pairing == null) {
            uiState = uiState.copy(errorMessage = "Pair with the desktop app before syncing.")
            return
        }
        uiState = uiState.copy(syncBusy = true, errorMessage = null)
        viewModelScope.launch {
            try {
                val api = HarnessApi(pairing.endpointUrl, pairing.syncToken)
                store.loadCaptures()
                    .filter { it.status == CaptureStatus.LOCAL_ONLY || it.status == CaptureStatus.QUEUED_FOR_UPLOAD }
                    .forEach { capture ->
                        val queued = capture.copy(status = CaptureStatus.QUEUED_FOR_UPLOAD, updatedAt = nowIso())
                        store.updateCapture(queued)
                        val upload = api.uploadMobileCapture(queued)
                        store.updateCapture(
                            queued.copy(
                                status = upload.status.toCaptureStatus(),
                                desktopCaptureId = upload.desktopCaptureId,
                                updatedAt = nowIso(),
                            ),
                        )
                    }
                val changes = api.mobileSyncChanges(store.loadSyncMetadata().cursor)
                store.upsertSyncChanges(changes)
                reloadLocalState(uiState.copy(syncBusy = false))
            } catch (exc: Exception) {
                reloadLocalState(
                    uiState.copy(
                        syncBusy = false,
                        errorMessage = exc.message ?: "Sync failed.",
                    ),
                )
            }
        }
    }

    fun createManualExpense() {
        val pairing = store.loadPairing()
        if (pairing == null) {
            uiState = uiState.copy(errorMessage = "Pair with the desktop app before adding expenses.")
            return
        }
        val merchant = uiState.manualMerchant.trim()
        val amountCents = parseAmountCents(uiState.manualAmount)
        if (merchant.isBlank() || amountCents == null) {
            uiState = uiState.copy(errorMessage = "Enter a merchant and amount.")
            return
        }
        uiState = uiState.copy(manualBusy = true, errorMessage = null)
        viewModelScope.launch {
            try {
                val api = HarnessApi(pairing.endpointUrl, pairing.syncToken)
                api.createMobileManualTransaction(
                    MobileManualTransactionRequest(
                        merchantName = merchant,
                        totalCents = amountCents,
                        note = uiState.manualNote.trim().ifBlank { null },
                        idempotencyKey = "android-${sessionStore.deviceId}-${System.currentTimeMillis()}",
                    ),
                )
                uiState = uiState.copy(
                    manualBusy = false,
                    manualMerchant = "",
                    manualAmount = "",
                    manualNote = "",
                )
                syncNow()
            } catch (exc: Exception) {
                uiState = uiState.copy(
                    manualBusy = false,
                    errorMessage = exc.message ?: "Manual expense failed.",
                )
            }
        }
    }

    private fun reloadLocalState(base: HarnessUiState = uiState) {
        val captures = store.loadCaptures()
        uiState = base.copy(
            pairing = store.loadPairing(),
            syncMetadata = store.loadSyncMetadata().copy(
                pendingCaptureCount = captures.count {
                    it.status == CaptureStatus.LOCAL_ONLY || it.status == CaptureStatus.QUEUED_FOR_UPLOAD
                },
            ),
            captures = captures,
            transactions = store.loadTransactions(),
            budgetSummary = store.loadBudgetSummary(),
            language = AppLanguage.fromTag(sessionStore.languageTag),
        )
    }

    private fun decodePairingPayload(raw: String): PairingQrPayload {
        val normalized = raw.trim()
        val outlaysScheme = "outlays-pair://"
        val legacyScheme = "lidltool-pair://"
        val matchedScheme = listOf(outlaysScheme, legacyScheme).firstOrNull { normalized.startsWith(it) }
        val jsonText = raw
            .removePrefix(matchedScheme.orEmpty())
            .let { text -> Uri.decode(text).takeIf { matchedScheme != null } ?: text }
        return json.decodeFromString(jsonText)
    }

    private fun copyCaptureIntoAppStorage(context: Context, uri: Uri): CaptureQueueEntry {
        val resolver = context.contentResolver
        val document = DocumentFile.fromSingleUri(context, uri)
        val originalName = document?.name ?: queryDisplayName(context, uri) ?: "receipt-capture"
        val mimeType = document?.type ?: resolver.getType(uri) ?: "application/octet-stream"
        val id = MobilePersistence.newCaptureId()
        val extension = originalName.substringAfterLast('.', "").takeIf { it.isNotBlank() }?.let { ".$it" }.orEmpty()
        val targetDir = File(context.filesDir, "captures").apply { mkdirs() }
        val target = File(targetDir, "$id$extension")
        resolver.openInputStream(uri)?.use { input ->
            target.outputStream().use { output -> input.copyTo(output) }
        } ?: throw ApiException("Selected capture could not be opened.")
        val bytes = target.readBytes()
        val createdAt = nowIso()
        return CaptureQueueEntry(
            id = id,
            fileName = originalName,
            mimeType = mimeType,
            filePath = target.absolutePath,
            fileSizeBytes = target.length(),
            sha256 = sha256(bytes),
            status = CaptureStatus.LOCAL_ONLY,
            createdAt = createdAt,
            updatedAt = createdAt,
        )
    }

    private fun queryDisplayName(context: Context, uri: Uri): String? {
        return context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
            ?.use { cursor ->
                if (cursor.moveToFirst()) {
                    cursor.getString(0)
                } else {
                    null
                }
            }
    }

    private fun sha256(bytes: ByteArray): String {
        return MessageDigest.getInstance("SHA-256")
            .digest(bytes)
            .joinToString("") { "%02x".format(it) }
    }

    private fun String.toCaptureStatus(): CaptureStatus {
        return when (lowercase()) {
            "uploaded" -> CaptureStatus.UPLOADED
            "processing_on_desktop" -> CaptureStatus.PROCESSING_ON_DESKTOP
            "needs_review" -> CaptureStatus.NEEDS_REVIEW
            "completed" -> CaptureStatus.COMPLETED
            "failed" -> CaptureStatus.FAILED
            "queued_for_upload" -> CaptureStatus.QUEUED_FOR_UPLOAD
            else -> CaptureStatus.UPLOADED
        }
    }

    companion object {
        private val json = Json {
            ignoreUnknownKeys = true
        }

        private fun parseAmountCents(raw: String): Int? {
            val normalized = raw.trim().replace(',', '.')
            if (normalized.isBlank()) return null
            return normalized.toBigDecimalOrNull()?.movePointRight(2)?.setScale(0)?.toInt()
        }
    }
}
