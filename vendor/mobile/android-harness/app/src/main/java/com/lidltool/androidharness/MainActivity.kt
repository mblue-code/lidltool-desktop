package com.lidltool.androidharness

import android.Manifest
import android.content.Context
import android.content.res.Configuration
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts.OpenDocument
import androidx.activity.result.contract.ActivityResultContracts.RequestPermission
import androidx.activity.result.contract.ActivityResultContracts.TakePicture
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.lifecycle.viewmodel.compose.viewModel
import com.lidltool.androidharness.ui.theme.HarnessAppBackground
import com.lidltool.androidharness.ui.theme.LidlToolHarnessTheme
import com.lidltool.androidharness.ui.theme.LidlToolThemeTokens
import java.io.File
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
import java.text.NumberFormat
import java.util.Locale

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            LidlToolHarnessTheme {
                HarnessAppBackground {
                    val viewModel: HarnessViewModel = viewModel()
                    LaunchedEffect(Unit) {
                        val pairingUrl = intent?.dataString
                        if (!pairingUrl.isNullOrBlank() && pairingUrl.startsWith("lidltool-pair://")) {
                            viewModel.updatePairingText(pairingUrl)
                            viewModel.pairFromText()
                        }
                    }
                    HarnessRoot(viewModel)
                }
            }
        }
    }
}

@Composable
private fun HarnessRoot(viewModel: HarnessViewModel) {
    val state = viewModel.uiState
    val snackbarHostState = remember { SnackbarHostState() }

    LaunchedEffect(state.errorMessage) {
        val message = state.errorMessage ?: return@LaunchedEffect
        snackbarHostState.showSnackbar(message)
        viewModel.clearError()
    }

    Scaffold(
        modifier = Modifier.fillMaxSize(),
        containerColor = Color.Transparent,
        snackbarHost = { SnackbarHost(hostState = snackbarHostState) },
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            if (state.pairing == null) {
                PairingScreen(
                    state = state,
                    onPayloadChanged = viewModel::updatePairingText,
                    onPair = viewModel::pairFromText,
                    onLanguageChanged = viewModel::setLanguage,
                )
            } else {
                CompanionApp(
                    state = state,
                    onSelectTab = viewModel::selectTab,
                    onSync = viewModel::syncNow,
                    onForget = viewModel::forgetPairing,
                    onImportCapture = viewModel::importCapture,
                    onMerchantChanged = viewModel::updateManualMerchant,
                    onAmountChanged = viewModel::updateManualAmount,
                    onNoteChanged = viewModel::updateManualNote,
                    onCreateManualExpense = viewModel::createManualExpense,
                    onLanguageChanged = viewModel::setLanguage,
                )
            }
        }
    }
}

@Composable
private fun PairingScreen(
    state: HarnessUiState,
    onPayloadChanged: (String) -> Unit,
    onPair: () -> Unit,
    onLanguageChanged: (AppLanguage) -> Unit,
) {
    val t = rememberStrings(state.language)
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item {
            LanguageSelector(state.language, onLanguageChanged)
        }
        item {
            Eyebrow(t(R.string.login_eyebrow))
            Text(
                t(R.string.pairing_title),
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.height(8.dp))
            Text(
                t(R.string.pairing_body),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        item {
            InfoCard(
                title = t(R.string.pairing_no_cloud_title),
                body = t(R.string.pairing_no_cloud_body),
            )
        }
        item {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer)) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(t(R.string.pairing_qr_payload), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    OutlinedTextField(
                        value = state.pairingText,
                        onValueChange = onPayloadChanged,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(180.dp),
                        label = { Text(t(R.string.pairing_payload_label)) },
                        minLines = 5,
                    )
                    Button(
                        onClick = onPair,
                        enabled = !state.pairingBusy,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        if (state.pairingBusy) {
                            CircularProgressIndicator(strokeWidth = 2.dp)
                        } else {
                            Text(t(R.string.pairing_action))
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CompanionApp(
    state: HarnessUiState,
    onSelectTab: (HarnessTab) -> Unit,
    onSync: () -> Unit,
    onForget: () -> Unit,
    onImportCapture: (android.content.Context, android.net.Uri) -> Unit,
    onMerchantChanged: (String) -> Unit,
    onAmountChanged: (String) -> Unit,
    onNoteChanged: (String) -> Unit,
    onCreateManualExpense: () -> Unit,
    onLanguageChanged: (AppLanguage) -> Unit,
) {
    val context = LocalContext.current
    val t = rememberStrings(state.language)
    var pendingCameraUri by remember { mutableStateOf<Uri?>(null) }
    val picker = rememberLauncherForActivityResult(OpenDocument()) { uri ->
        if (uri != null) onImportCapture(context, uri)
    }
    val camera = rememberLauncherForActivityResult(TakePicture()) { saved ->
        val uri = pendingCameraUri
        pendingCameraUri = null
        if (saved && uri != null) {
            onImportCapture(context, uri)
        }
    }
    val cameraPermission = rememberLauncherForActivityResult(RequestPermission()) { granted ->
        if (granted) {
            val uri = createCameraCaptureUri(context)
            pendingCameraUri = uri
            camera.launch(uri)
        }
    }
    Scaffold(
        modifier = Modifier.fillMaxSize(),
        containerColor = Color.Transparent,
        topBar = {
            TopAppBar(
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = LidlToolThemeTokens.extras.navSurface,
                    titleContentColor = LidlToolThemeTokens.extras.navOnSurface,
                    actionIconContentColor = LidlToolThemeTokens.extras.navOnSurface,
                ),
                title = {
                    Column(Modifier.fillMaxWidth()) {
                        Text(
                            state.pairing?.desktopName ?: t(R.string.app_name),
                            style = MaterialTheme.typography.titleMedium,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        Text(
                            state.pairing?.endpointUrl.orEmpty(),
                            style = MaterialTheme.typography.labelSmall,
                            color = LidlToolThemeTokens.extras.navOnSurface.copy(alpha = 0.78f),
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                },
                actions = {
                    val navButtonColors = ButtonDefaults.textButtonColors(
                        contentColor = LidlToolThemeTokens.extras.navOnSurface,
                        disabledContentColor = LidlToolThemeTokens.extras.navOnSurface.copy(alpha = 0.68f),
                    )
                    TextButton(onClick = onSync, enabled = !state.syncBusy, colors = navButtonColors) { Text(t(R.string.action_sync)) }
                    TextButton(onClick = onForget, colors = navButtonColors) { Text(t(R.string.action_forget)) }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            if (state.syncBusy || state.importBusy) {
                LinearProgressIndicator(Modifier.fillMaxWidth())
            }
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 10.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                listOf(
                    HarnessTab.Home,
                    HarnessTab.Transactions,
                    HarnessTab.Capture,
                    HarnessTab.Sync,
                    HarnessTab.Settings,
                ).forEach { tab ->
                    val selected = state.selectedTab == tab
                    Surface(
                        modifier = Modifier.weight(1f),
                        shape = MaterialTheme.shapes.medium,
                        color = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceContainerHigh.copy(alpha = 0.42f),
                        contentColor = if (selected) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
                        border = if (selected) null else BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.9f)),
                    ) {
                        Box(
                            modifier = Modifier
                                .clickable { onSelectTab(tab) }
                                .padding(horizontal = 4.dp, vertical = 10.dp),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text(
                                t(tab.titleRes),
                                style = MaterialTheme.typography.labelMedium,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                            )
                        }
                    }
                }
            }
            when (state.selectedTab) {
                HarnessTab.Home -> OverviewScreen(state, onSync)
                HarnessTab.Transactions -> TransactionsScreen(
                    state = state,
                    onMerchantChanged = onMerchantChanged,
                    onAmountChanged = onAmountChanged,
                    onNoteChanged = onNoteChanged,
                    onCreateManualExpense = onCreateManualExpense,
                )
                HarnessTab.Capture -> CaptureQueueScreen(
                    state = state,
                    onTakePhoto = {
                        if (ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                            val uri = createCameraCaptureUri(context)
                            pendingCameraUri = uri
                            camera.launch(uri)
                        } else {
                            cameraPermission.launch(Manifest.permission.CAMERA)
                        }
                    },
                    onPickCapture = { picker.launch(arrayOf("image/*", "application/pdf")) },
                    onSync = onSync,
                )
                HarnessTab.Sync -> SyncStatusScreen(state, onLanguageChanged)
                HarnessTab.Settings -> AnalysisScreen(state)
            }
        }
    }
}

@Composable
private fun OverviewScreen(state: HarnessUiState, onSync: () -> Unit) {
    val t = rememberStrings(state.language)
    val budget = state.budgetSummary
    val currency = budget?.currency ?: state.transactions.firstOrNull()?.currency ?: "EUR"
    val spentCents = budget?.spentCents ?: state.transactions.sumOf { it.totalGrossCents }
    val budgetCents = budget?.budgetCents ?: 0
    val remainingCents = (budgetCents - spentCents).coerceAtLeast(0)
    val pendingCaptures = state.captures.count {
        it.status == CaptureStatus.LOCAL_ONLY || it.status == CaptureStatus.QUEUED_FOR_UPLOAD
    }
    val needsReview = state.captures.count { it.status == CaptureStatus.NEEDS_REVIEW } +
        state.transactions.count { it.needsReview }
    val completedCaptures = state.captures.count { it.status == CaptureStatus.COMPLETED }
    val topMerchant = state.transactions
        .groupBy { it.merchantName?.ifBlank { null } ?: t(R.string.common_unknown_merchant) }
        .mapValues { entry -> entry.value.sumOf { it.totalGrossCents } }
        .maxByOrNull { it.value }
    val progress = if (budgetCents > 0) {
        (spentCents.toFloat() / budgetCents.toFloat()).coerceIn(0f, 1f)
    } else {
        0f
    }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            SectionHeader(
                eyebrow = t(R.string.dashboard_eyebrow),
                title = t(R.string.overview_title),
                description = t(R.string.overview_description),
            )
        }
        item {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer)) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Top) {
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(t(R.string.dashboard_current_period), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                            Text(
                                budget?.periodLabel ?: t(R.string.overview_synced_spend),
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis,
                            )
                        }
                        StatusPill(
                            label = if (state.syncBusy) t(R.string.action_syncing) else t(R.string.overview_local),
                            color = if (state.syncBusy) LidlToolThemeTokens.extras.info else LidlToolThemeTokens.extras.success,
                        )
                    }
                    if (budget == null) {
                        Text(
                            t(R.string.overview_no_budget),
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    Text(
                        if (budgetCents > 0) {
                            t(R.string.overview_of, moneyText(spentCents, currency), moneyText(budgetCents, currency))
                        } else {
                            moneyText(spentCents, currency)
                        },
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    LinearProgressIndicator(progress = { progress }, modifier = Modifier.fillMaxWidth())
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        Button(onClick = onSync, enabled = !state.syncBusy) { Text(if (state.syncBusy) t(R.string.action_syncing) else t(R.string.action_sync_now)) }
                        Text(
                            displayTimestamp(state.syncMetadata.lastSuccessAt) ?: t(R.string.common_not_synced_yet),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                }
            }
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
                MetricCard(t(R.string.metric_remaining), moneyText(remainingCents, currency), t(R.string.metric_available_budget), Modifier.weight(1f))
                MetricCard(t(R.string.metric_transactions), state.transactions.size.toString(), t(R.string.metric_synced_locally), Modifier.weight(1f))
            }
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
                MetricCard(t(R.string.metric_queued), pendingCaptures.toString(), t(R.string.metric_captures_to_upload), Modifier.weight(1f))
                MetricCard(t(R.string.metric_review), needsReview.toString(), t(R.string.metric_desktop_follow_up), Modifier.weight(1f))
            }
        }
        item {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer)) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(t(R.string.highlights_title), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    KeyValue(t(R.string.highlight_top_merchant), topMerchant?.let { "${it.key} · ${moneyText(it.value, currency)}" } ?: t(R.string.common_not_enough_data))
                    KeyValue(t(R.string.highlight_completed_captures), completedCaptures.toString())
                    KeyValue(t(R.string.highlight_last_sync), displayTimestamp(state.syncMetadata.lastSuccessAt) ?: t(R.string.common_not_synced_yet))
                }
            }
        }
        if (state.transactions.isNotEmpty()) {
            item { SectionHeader(t(R.string.activity_eyebrow), t(R.string.activity_recent_spending), t(R.string.activity_description)) }
            items(state.transactions.take(5)) { transaction ->
                CompactTransactionCard(transaction, state.language)
            }
        } else {
            item {
                InfoCard(t(R.string.empty_no_transactions_title), t(R.string.empty_no_transactions_body))
            }
        }
    }
}

@Composable
private fun AnalysisScreen(state: HarnessUiState) {
    val t = rememberStrings(state.language)
    val currency = state.budgetSummary?.currency ?: state.transactions.firstOrNull()?.currency ?: "EUR"
    val totalCents = state.transactions.sumOf { it.totalGrossCents }
    val categoryTotals = state.transactions
        .groupBy { it.category?.ifBlank { null } ?: t(R.string.common_uncategorized) }
        .mapValues { entry -> entry.value.sumOf { it.totalGrossCents } }
        .toList()
        .sortedByDescending { it.second }
    val merchantTotals = state.transactions
        .groupBy { it.merchantName?.ifBlank { null } ?: t(R.string.common_unknown_merchant) }
        .mapValues { entry -> entry.value.sumOf { it.totalGrossCents } }
        .toList()
        .sortedByDescending { it.second }
    val monthTotals = state.transactions
        .groupBy { it.purchasedAt.take(7).ifBlank { t(R.string.common_unknown) } }
        .mapValues { entry -> entry.value.sumOf { it.totalGrossCents } }
        .toList()
        .sortedByDescending { it.first }
    val averageCents = if (state.transactions.isEmpty()) 0 else totalCents / state.transactions.size
    val reviewCount = state.transactions.count { it.needsReview }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            SectionHeader(
                eyebrow = t(R.string.tab_settings),
                title = t(R.string.analysis_title),
                description = t(R.string.analysis_description),
            )
        }
        if (state.transactions.isEmpty()) {
            item { InfoCard(t(R.string.analysis_empty_title), t(R.string.analysis_empty_body)) }
        } else {
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
                    MetricCard(t(R.string.metric_total), moneyText(totalCents, currency), t(R.string.metric_synced_spend), Modifier.weight(1f))
                    MetricCard(t(R.string.metric_average), moneyText(averageCents, currency), t(R.string.metric_per_transaction), Modifier.weight(1f))
                }
            }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
                    MetricCard(t(R.string.metric_merchants), merchantTotals.size.toString(), t(R.string.metric_unique_names), Modifier.weight(1f))
                    MetricCard(t(R.string.metric_review), reviewCount.toString(), t(R.string.status_needs_review), Modifier.weight(1f))
                }
            }
            item { RankedListCard(t(R.string.analysis_top_categories), categoryTotals.take(6), totalCents, currency) }
            item { RankedListCard(t(R.string.analysis_top_merchants), merchantTotals.take(6), totalCents, currency) }
            item { RankedListCard(t(R.string.analysis_monthly_trend), monthTotals.take(6), totalCents, currency) }
        }
    }
}

@Composable
private fun TransactionsScreen(
    state: HarnessUiState,
    onMerchantChanged: (String) -> Unit,
    onAmountChanged: (String) -> Unit,
    onNoteChanged: (String) -> Unit,
    onCreateManualExpense: () -> Unit,
) {
    val t = rememberStrings(state.language)
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            SectionHeader(
                eyebrow = t(R.string.transactions_eyebrow),
                title = t(R.string.transactions_title),
                description = t(R.string.transactions_description),
            )
        }
        item {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer)) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(t(R.string.manual_expense_title), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    OutlinedTextField(
                        value = state.manualMerchant,
                        onValueChange = onMerchantChanged,
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text(t(R.string.manual_merchant)) },
                        singleLine = true,
                    )
                    OutlinedTextField(
                        value = state.manualAmount,
                        onValueChange = onAmountChanged,
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text(t(R.string.manual_amount)) },
                        singleLine = true,
                    )
                    OutlinedTextField(
                        value = state.manualNote,
                        onValueChange = onNoteChanged,
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text(t(R.string.manual_note)) },
                        singleLine = true,
                    )
                    Button(
                        onClick = onCreateManualExpense,
                        enabled = !state.manualBusy,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(if (state.manualBusy) t(R.string.action_saving) else t(R.string.manual_save))
                    }
                }
            }
        }
        if (state.transactions.isEmpty()) {
            item { InfoCard(t(R.string.empty_transactions_title), t(R.string.empty_transactions_body)) }
        } else {
            items(state.transactions) { transaction ->
                CompactTransactionCard(transaction, state.language)
            }
        }
    }
}

@Composable
private fun CompactTransactionCard(transaction: MobileTransaction, language: AppLanguage) {
    val t = rememberStrings(language)
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Top) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(
                        transaction.merchantName ?: t(R.string.common_unknown_merchant),
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        displayTimestamp(transaction.purchasedAt) ?: transaction.purchasedAt,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                Text(
                    moneyText(transaction.totalGrossCents, transaction.currency),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                )
            }
            transaction.category?.let { StatusPill(it, MaterialTheme.colorScheme.primary) }
            if (transaction.needsReview) {
                StatusPill(t(R.string.status_needs_review), LidlToolThemeTokens.extras.warning)
            }
        }
    }
}

@Composable
private fun RankedListCard(
    title: String,
    rows: List<Pair<String, Int>>,
    totalCents: Int,
    currency: String,
) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            rows.forEach { (label, cents) ->
                val progress = if (totalCents > 0) {
                    (cents.toFloat() / totalCents.toFloat()).coerceIn(0f, 1f)
                } else {
                    0f
                }
                Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Top) {
                        Text(label, modifier = Modifier.weight(1f), maxLines = 2, overflow = TextOverflow.Ellipsis)
                        Text(
                            moneyText(cents, currency),
                            fontWeight = FontWeight.SemiBold,
                            maxLines = 1,
                        )
                    }
                    LinearProgressIndicator(progress = { progress }, modifier = Modifier.fillMaxWidth())
                }
            }
        }
    }
}

@Composable
private fun CaptureQueueScreen(
    state: HarnessUiState,
    onTakePhoto: () -> Unit,
    onPickCapture: () -> Unit,
    onSync: () -> Unit,
) {
    val t = rememberStrings(state.language)
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            SectionHeader(
                eyebrow = t(R.string.capture_eyebrow),
                title = t(R.string.capture_title),
                description = t(R.string.capture_description),
            )
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = onTakePhoto, enabled = !state.importBusy) { Text(t(R.string.capture_take_photo)) }
                Button(onClick = onPickCapture, enabled = !state.importBusy) { Text(t(R.string.capture_import_receipt)) }
                OutlinedButton(onClick = onSync, enabled = !state.syncBusy) { Text(t(R.string.capture_upload_queue)) }
            }
        }
        if (state.captures.isEmpty()) {
            item { InfoCard(t(R.string.capture_empty_title), t(R.string.capture_empty_body)) }
        } else {
            items(state.captures) { capture ->
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer)) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(capture.fileName, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                            Text(
                                captureStatusLabel(capture.status, t),
                                color = MaterialTheme.colorScheme.primary,
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis,
                            )
                        }
                        Text("${capture.mimeType} · ${capture.fileSizeBytes} bytes", color = MaterialTheme.colorScheme.onSurfaceVariant)
                        capture.desktopCaptureId?.let { Text(t(R.string.capture_desktop_capture, it)) }
                        capture.transactionId?.let { Text(t(R.string.capture_transaction, it)) }
                        capture.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                    }
                }
            }
        }
    }
}

@Composable
private fun SyncStatusScreen(state: HarnessUiState, onLanguageChanged: (AppLanguage) -> Unit) {
    val t = rememberStrings(state.language)
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            SectionHeader(
                eyebrow = t(R.string.sync_eyebrow),
                title = t(R.string.sync_title),
                description = t(R.string.sync_description),
            )
        }
        item {
            LanguageSelector(state.language, onLanguageChanged)
        }
        item {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer)) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    state.pairing?.let { pairing ->
                        KeyValue(t(R.string.sync_desktop), pairing.desktopName)
                        KeyValue(t(R.string.sync_desktop_id), pairing.desktopId)
                        KeyValue(t(R.string.sync_endpoint), pairing.endpointUrl)
                        KeyValue(t(R.string.sync_fingerprint), pairing.publicKeyFingerprint)
                        KeyValue(t(R.string.sync_token_expires), pairing.expiresAt)
                    }
                    HorizontalDivider()
                    KeyValue(t(R.string.sync_cursor), state.syncMetadata.cursor ?: t(R.string.common_none))
                    KeyValue(t(R.string.sync_server_time), displayTimestamp(state.syncMetadata.serverTime) ?: t(R.string.common_none))
                    KeyValue(t(R.string.sync_pending_captures), state.syncMetadata.pendingCaptureCount.toString())
                }
            }
        }
    }
}

@Composable
private fun SectionHeader(eyebrow: String, title: String, description: String) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Eyebrow(eyebrow)
        Text(title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Text(description, color = MaterialTheme.colorScheme.onSurfaceVariant, lineHeight = MaterialTheme.typography.bodyMedium.lineHeight)
    }
}

@Composable
private fun Eyebrow(text: String) {
    Text(text.uppercase(Locale.getDefault()), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
}

@Composable
private fun InfoCard(title: String, body: String) {
    Card(colors = CardDefaults.cardColors(containerColor = LidlToolThemeTokens.extras.infoContainer)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(title, fontWeight = FontWeight.SemiBold)
            Text(body, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun MetricCard(title: String, value: String, supporting: String, modifier: Modifier = Modifier) {
    Card(modifier = modifier, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(title, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(
                value,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                supporting,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodySmall,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
private fun KeyValue(label: String, value: String) {
    Column(verticalArrangement = Arrangement.spacedBy(2.dp), modifier = Modifier.fillMaxWidth()) {
        Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, maxLines = 2, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun StatusPill(label: String, color: Color) {
    Surface(
        color = color.copy(alpha = 0.12f),
        contentColor = color,
        shape = MaterialTheme.shapes.small,
    ) {
        Text(
            label,
            style = MaterialTheme.typography.labelMedium,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
        )
    }
}

@Composable
private fun LanguageSelector(
    selected: AppLanguage,
    onLanguageChanged: (AppLanguage) -> Unit,
) {
    val t = rememberStrings(selected)
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(t(R.string.language_title), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                LanguageOption(
                    label = t(R.string.language_english),
                    selected = selected == AppLanguage.English,
                    onClick = { onLanguageChanged(AppLanguage.English) },
                    modifier = Modifier.weight(1f),
                )
                LanguageOption(
                    label = t(R.string.language_german),
                    selected = selected == AppLanguage.German,
                    onClick = { onLanguageChanged(AppLanguage.German) },
                    modifier = Modifier.weight(1f),
                )
            }
        }
    }
}

@Composable
private fun LanguageOption(
    label: String,
    selected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier,
        shape = MaterialTheme.shapes.medium,
        color = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceContainerHigh.copy(alpha = 0.42f),
        contentColor = if (selected) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
        border = if (selected) null else BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.9f)),
    ) {
        Box(
            modifier = Modifier
                .clickable(onClick = onClick)
                .padding(horizontal = 12.dp, vertical = 10.dp),
            contentAlignment = Alignment.Center,
        ) {
            Text(label, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

@Composable
private fun rememberStrings(language: AppLanguage): (Int, Array<out Any>) -> String {
    val context = LocalContext.current
    return remember(context, language) {
        val localized = context.localizedFor(language)
        val translator: (Int, Array<out Any>) -> String = { resId, args ->
            if (args.isEmpty()) localized.getString(resId) else localized.getString(resId, *args)
        }
        translator
    }
}

private operator fun ((Int, Array<out Any>) -> String).invoke(resId: Int, vararg args: Any): String {
    return this(resId, args)
}

private fun Context.localizedFor(language: AppLanguage): android.content.res.Resources {
    val config = Configuration(resources.configuration)
    config.setLocale(Locale.forLanguageTag(language.tag))
    return createConfigurationContext(config).resources
}

private fun moneyText(cents: Int, currencyCode: String): String {
    val format = NumberFormat.getCurrencyInstance(Locale.getDefault())
    format.currency = java.util.Currency.getInstance(currencyCode)
    return format.format(cents / 100.0)
}

private fun displayTimestamp(value: String?): String? {
    val raw = value?.trim().orEmpty()
    if (raw.isBlank()) return null
    val formatter = DateTimeFormatter.ofPattern("dd.MM.yyyy HH:mm", Locale.getDefault())
    return runCatching { OffsetDateTime.parse(raw).format(formatter) }
        .recoverCatching { LocalDateTime.parse(raw).format(formatter) }
        .getOrElse { raw.replace('T', ' ').take(16) }
}

private fun captureStatusLabel(status: CaptureStatus, t: (Int, Array<out Any>) -> String): String {
    return when (status) {
        CaptureStatus.LOCAL_ONLY -> t(R.string.status_local_only)
        CaptureStatus.QUEUED_FOR_UPLOAD -> t(R.string.status_queued)
        CaptureStatus.UPLOADED -> t(R.string.status_uploaded)
        CaptureStatus.PROCESSING_ON_DESKTOP -> t(R.string.status_processing)
        CaptureStatus.NEEDS_REVIEW -> t(R.string.status_needs_review)
        CaptureStatus.COMPLETED -> t(R.string.status_completed)
        CaptureStatus.FAILED -> t(R.string.status_failed)
    }
}

private fun createCameraCaptureUri(context: Context): Uri {
    val dir = File(context.filesDir, "captures").apply { mkdirs() }
    val file = File(dir, "camera-${System.currentTimeMillis()}.jpg")
    return FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
}
