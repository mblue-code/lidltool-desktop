package com.lidltool.androidharness

import java.io.IOException
import java.io.File
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.logging.HttpLoggingInterceptor

class ApiException(
    message: String,
    val code: String? = null,
    val httpStatus: Int? = null,
) : IOException(message)

class HarnessApi(
    baseUrl: String,
    private val bearerToken: String? = null,
) {
    private val normalizedBaseUrl = normalizeBaseUrl(baseUrl)

    suspend fun health(): HealthStatus = get("/api/v1/health")

    suspend fun pairWithDesktop(payload: PairingQrPayload, request: PairingHandshakeRequest): PairingHandshakeResponse {
        return postFlexible(
            path = "/api/mobile-pair/v1/handshake",
            payload = request,
            overrideBaseUrl = payload.endpointUrl,
        )
    }

    suspend fun uploadMobileCapture(capture: CaptureQueueEntry): CaptureUploadResponse {
        return withContext(Dispatchers.IO) {
            val metadata = CaptureUploadMetadata(
                mobileCaptureId = capture.id,
                fileName = capture.fileName,
                mimeType = capture.mimeType,
                fileSizeBytes = capture.fileSizeBytes,
                sha256 = capture.sha256,
                note = capture.note,
                createdAt = capture.createdAt,
            )
            val file = File(capture.filePath)
            val multipart = MultipartBody.Builder()
                .setType(MultipartBody.FORM)
                .addFormDataPart(
                    name = "file",
                    filename = capture.fileName,
                    body = file.readBytes().toRequestBody(capture.mimeType.toMediaTypeOrNull()),
                )
                .addFormDataPart("metadata", json.encodeToString(metadata))
                .addFormDataPart("mobile_capture_id", capture.id)
                .build()
            val request = authorizedRequest(buildUrl("/api/mobile-captures/v1"))
                .post(multipart)
                .build()
            sharedClient.newCall(request).execute().use { response ->
                val bodyText = response.body?.string().orEmpty()
                if (!response.isSuccessful) {
                    throw parseApiException(bodyText, response.code)
                }
                decodeFlexibleResult(bodyText)
            }
        }
    }

    suspend fun mobileSyncChanges(cursor: String?): MobileSyncChangesResponse {
        return getFlexible(
            path = "/api/mobile-sync/v1/changes",
            params = mapOf("cursor" to cursor),
        )
    }

    suspend fun createMobileManualTransaction(request: MobileManualTransactionRequest): MobileManualTransactionResponse {
        return postFlexible(
            path = "/api/mobile-sync/v1/manual-transactions",
            payload = request,
        )
    }

    suspend fun setupRequired(): AuthSetupStatus = get("/api/v1/auth/setup-required")

    suspend fun login(username: String, password: String): CurrentUser {
        return post(
            path = "/api/v1/auth/login",
            payload = AuthLoginRequest(username = username, password = password),
        )
    }

    suspend fun currentUser(): CurrentUser = get("/api/v1/auth/me")

    suspend fun dashboardSummary(): DashboardSummary = get("/api/v1/dashboard/summary")

    suspend fun transactions(query: String? = null, limit: Int = 50): TransactionListResponse {
        return get(
            path = "/api/v1/transactions",
            params = mapOf(
                "limit" to limit.toString(),
                "query" to query,
            ),
        )
    }

    suspend fun transactionDetail(transactionId: String): TransactionDetailResponse {
        return get("/api/v1/transactions/$transactionId")
    }

    suspend fun offersOverview(): OfferOverview = get("/api/v1/offers")

    suspend fun offerAlerts(limit: Int = 30): OfferAlertListResponse {
        return get("/api/v1/offers/alerts", params = mapOf("limit" to limit.toString()))
    }

    suspend fun watchlists(): OfferWatchlistListResponse = get("/api/v1/offers/watchlists")

    suspend fun updateWatchlist(watchlistId: String, active: Boolean): OfferWatchlist {
        return patch(
            path = "/api/v1/offers/watchlists/$watchlistId",
            payload = OfferWatchlistUpdateRequest(active = active),
        )
    }

    suspend fun registerMobileDevice(request: MobileDeviceRegistrationRequest): JsonObject {
        val primaryAttempt = runCatching<JsonObject> {
            put("/api/v1/mobile/devices/current", request)
        }
        if (primaryAttempt.isSuccess) {
            return primaryAttempt.getOrThrow()
        }
        val failure = primaryAttempt.exceptionOrNull()
        if (failure is ApiException && failure.httpStatus in setOf(404, 405)) {
            return post("/api/v1/mobile/devices", request)
        }
        throw (failure ?: ApiException("mobile device registration failed"))
    }

    suspend fun markAlertRead(alertId: String, read: Boolean): OfferAlert {
        return patch(
            path = "/api/v1/offers/alerts/$alertId",
            payload = OfferAlertUpdateRequest(read = read),
        )
    }

    suspend fun sourcesStatus(): SourceStatusListResponse = get("/api/v1/sources/status")

    suspend fun chatThreads(): ChatThreadListResponse = get("/api/v1/chat/threads")

    suspend fun createChatThread(title: String? = null): ChatThread {
        return post("/api/v1/chat/threads", ChatThreadCreateRequest(title = title))
    }

    suspend fun chatMessages(threadId: String): ChatMessageListResponse {
        return get("/api/v1/chat/threads/$threadId/messages")
    }

    suspend fun createChatMessage(threadId: String, content: String, idempotencyKey: String): ChatMessageCreateResult {
        return post(
            path = "/api/v1/chat/threads/$threadId/messages",
            payload = ChatMessageCreateRequest(content = content, idempotencyKey = idempotencyKey),
        )
    }

    suspend fun streamChat(threadId: String, onEvent: suspend (ChatStreamEvent) -> Unit) {
        withContext(Dispatchers.IO) {
            val requestBody = json.encodeToString(ChatStreamRequest()).toRequestBody(jsonMediaType)
            val request = authorizedRequest(
                buildUrl("/api/v1/chat/threads/$threadId/stream"),
            )
                .post(requestBody)
                .build()
            sharedClient.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    throw parseApiException(response.body?.string().orEmpty(), response.code)
                }
                val source = response.body?.source() ?: throw ApiException("chat stream body missing")
                val eventLines = mutableListOf<String>()
                while (!source.exhausted()) {
                    val line = source.readUtf8Line() ?: break
                    if (line.isBlank()) {
                        if (eventLines.isNotEmpty()) {
                            val data = eventLines
                                .filter { it.startsWith("data:") }
                                .joinToString("\n") { it.removePrefix("data:").trim() }
                            if (data.isNotBlank()) {
                                onEvent(json.decodeFromString(data))
                            }
                            eventLines.clear()
                        }
                        continue
                    }
                    eventLines += line
                }
            }
        }
    }

    suspend fun uploadDocument(
        fileName: String,
        mimeType: String,
        bytes: ByteArray,
        source: String = "ocr_upload",
    ): DocumentUploadResult {
        return withContext(Dispatchers.IO) {
            val multipart = MultipartBody.Builder()
                .setType(MultipartBody.FORM)
                .addFormDataPart(
                    name = "file",
                    filename = fileName,
                    body = bytes.toRequestBody(mimeType.toMediaTypeOrNull()),
                )
                .addFormDataPart("source", source)
                .build()
            val request = authorizedRequest(buildUrl("/api/v1/documents/upload"))
                .post(multipart)
                .build()
            sharedClient.newCall(request).execute().use { response ->
                val bodyText = response.body?.string().orEmpty()
                if (!response.isSuccessful) {
                    throw parseApiException(bodyText, response.code)
                }
                decodeResult(bodyText)
            }
        }
    }

    suspend fun processDocument(documentId: String): DocumentProcessResult {
        return withContext(Dispatchers.IO) {
            val multipart = MultipartBody.Builder()
                .setType(MultipartBody.FORM)
                .build()
            val request = authorizedRequest(buildUrl("/api/v1/documents/$documentId/process"))
                .post(multipart)
                .build()
            sharedClient.newCall(request).execute().use { response ->
                val bodyText = response.body?.string().orEmpty()
                if (!response.isSuccessful) {
                    throw parseApiException(bodyText, response.code)
                }
                decodeResult(bodyText)
            }
        }
    }

    suspend fun documentStatus(documentId: String, jobId: String? = null): DocumentStatusResult {
        return get(
            path = "/api/v1/documents/$documentId/status",
            params = mapOf("job_id" to jobId),
        )
    }

    private suspend inline fun <reified T> get(
        path: String,
        params: Map<String, String?> = emptyMap(),
    ): T = requestJson(
        authorizedRequest(buildUrl(path, params = params))
            .get()
            .build(),
    )

    private suspend inline fun <reified T, reified P> post(path: String, payload: P): T {
        val body = json.encodeToString(payload).toRequestBody(jsonMediaType)
        return requestJson(
            authorizedRequest(buildUrl(path))
                .post(body)
                .build(),
        )
    }

    private suspend inline fun <reified T> getFlexible(
        path: String,
        params: Map<String, String?> = emptyMap(),
    ): T = requestJsonFlexible(
        authorizedRequest(buildUrl(path, params = params))
            .get()
            .build(),
    )

    private suspend inline fun <reified T, reified P> postFlexible(
        path: String,
        payload: P,
        overrideBaseUrl: String? = null,
    ): T {
        val body = json.encodeToString(payload).toRequestBody(jsonMediaType)
        val url = if (overrideBaseUrl.isNullOrBlank()) {
            buildUrl(path)
        } else {
            buildUrl(path, overrideBaseUrl = overrideBaseUrl)
        }
        return requestJsonFlexible(
            authorizedRequest(url)
                .post(body)
                .build(),
        )
    }

    private suspend inline fun <reified T, reified P> patch(path: String, payload: P): T {
        val body = json.encodeToString(payload).toRequestBody(jsonMediaType)
        return requestJson(
            authorizedRequest(buildUrl(path))
                .patch(body)
                .build(),
        )
    }

    private suspend inline fun <reified T, reified P> put(path: String, payload: P): T {
        val body = json.encodeToString(payload).toRequestBody(jsonMediaType)
        return requestJson(
            authorizedRequest(buildUrl(path))
                .put(body)
                .build(),
        )
    }

    private suspend inline fun <reified T> delete(path: String): T {
        return requestJson(
            authorizedRequest(buildUrl(path))
                .delete()
                .build(),
        )
    }

    private suspend inline fun <reified T> requestJson(request: Request): T {
        return withContext(Dispatchers.IO) {
            sharedClient.newCall(request).execute().use { response ->
                val bodyText = response.body?.string().orEmpty()
                if (!response.isSuccessful) {
                    throw parseApiException(bodyText, response.code)
                }
                decodeResult(bodyText)
            }
        }
    }

    private suspend inline fun <reified T> requestJsonFlexible(request: Request): T {
        return withContext(Dispatchers.IO) {
            sharedClient.newCall(request).execute().use { response ->
                val bodyText = response.body?.string().orEmpty()
                if (!response.isSuccessful) {
                    throw parseApiException(bodyText, response.code)
                }
                decodeFlexibleResult(bodyText)
            }
        }
    }

    private inline fun <reified T> decodeResult(bodyText: String): T {
        val envelope = json.decodeFromString<ApiEnvelope<T>>(bodyText)
        if (!envelope.ok || envelope.result == null) {
            throw ApiException(envelope.error ?: "request failed", envelope.errorCode)
        }
        return envelope.result
    }

    private inline fun <reified T> decodeFlexibleResult(bodyText: String): T {
        return runCatching { decodeResult<T>(bodyText) }
            .getOrElse { json.decodeFromString(bodyText) }
    }

    private fun authorizedRequest(url: HttpUrl): Request.Builder {
        return Request.Builder()
            .url(url)
            .header("Accept", "application/json")
            .apply {
                if (!bearerToken.isNullOrBlank()) {
                    header("Authorization", "Bearer $bearerToken")
                }
            }
    }

    private fun buildUrl(
        path: String,
        params: Map<String, String?> = emptyMap(),
        overrideBaseUrl: String? = null,
    ): HttpUrl {
        val resolvedBaseUrl = normalizeBaseUrl(overrideBaseUrl ?: normalizedBaseUrl)
        val base = resolvedBaseUrl.toHttpUrlOrNull()
            ?: throw ApiException("invalid backend URL: $resolvedBaseUrl")
        val builder = base.newBuilder()
        val normalizedPath = path.removePrefix("/")
        val resolvedPath = ((base.encodedPath.takeIf { it.isNotBlank() } ?: "/").trimEnd('/') + "/" + normalizedPath)
            .replace("//", "/")
        builder.encodedPath(if (resolvedPath.startsWith("/")) resolvedPath else "/$resolvedPath")
        params.forEach { (key, value) ->
            if (!value.isNullOrBlank()) {
                builder.addQueryParameter(key, value)
            }
        }
        return builder.build()
    }

    private fun parseApiException(bodyText: String, statusCode: Int): ApiException {
        return try {
            val envelope = json.decodeFromString<ApiEnvelope<JsonObject>>(bodyText)
            ApiException(
                message = envelope.error ?: "request failed with HTTP $statusCode",
                code = envelope.errorCode,
                httpStatus = statusCode,
            )
        } catch (_: Exception) {
            ApiException("request failed with HTTP $statusCode", httpStatus = statusCode)
        }
    }

    companion object {
        @OptIn(ExperimentalSerializationApi::class)
        private val json = Json {
            ignoreUnknownKeys = true
            explicitNulls = false
        }

        private val jsonMediaType = "application/json; charset=utf-8".toMediaType()

        private val sharedClient: OkHttpClient by lazy {
            val logging = HttpLoggingInterceptor().apply {
                level = HttpLoggingInterceptor.Level.BASIC
            }
            OkHttpClient.Builder()
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(120, TimeUnit.SECONDS)
                .writeTimeout(120, TimeUnit.SECONDS)
                .addInterceptor(logging)
                .build()
        }

        fun normalizeBaseUrl(raw: String): String {
            val trimmed = raw.trim().removeSuffix("/")
            return trimmed.ifBlank { raw.trim() }
        }
    }
}
