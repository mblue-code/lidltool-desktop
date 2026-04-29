package com.lidltool.androidharness

import android.content.Context
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.google.mlkit.vision.barcode.BarcodeScanner
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

@Composable
fun PairingQrScannerScreen(
    title: String,
    body: String,
    cancelLabel: String,
    errorTitle: String,
    onCancel: () -> Unit,
    onPayloadScanned: (String) -> Unit,
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val previewView = remember {
        PreviewView(context).apply {
            scaleType = PreviewView.ScaleType.FILL_CENTER
        }
    }
    val cameraExecutor = remember { Executors.newSingleThreadExecutor() }
    val decoded = remember { AtomicBoolean(false) }
    val scanner = remember {
        BarcodeScanning.getClient(
            BarcodeScannerOptions.Builder()
                .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
                .build(),
        )
    }
    var scannerError by remember { mutableStateOf<String?>(null) }

    DisposableEffect(context, lifecycleOwner, previewView, scanner) {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(context)
        cameraProviderFuture.addListener(
            {
                try {
                    val cameraProvider = cameraProviderFuture.get()
                    val preview = Preview.Builder().build().also {
                        it.setSurfaceProvider(previewView.surfaceProvider)
                    }
                    val imageAnalysis = ImageAnalysis.Builder()
                        .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                        .build()
                        .also { analysis ->
                            analysis.setAnalyzer(cameraExecutor) { imageProxy ->
                                analyzePairingQrCode(
                                    context = context,
                                    imageProxy = imageProxy,
                                    scanner = scanner,
                                    decoded = decoded,
                                    onPayloadScanned = onPayloadScanned,
                                )
                            }
                        }

                    cameraProvider.unbindAll()
                    cameraProvider.bindToLifecycle(
                        lifecycleOwner,
                        CameraSelector.DEFAULT_BACK_CAMERA,
                        preview,
                        imageAnalysis,
                    )
                    scannerError = null
                } catch (_: Exception) {
                    scannerError = errorTitle
                }
            },
            ContextCompat.getMainExecutor(context),
        )

        onDispose {
            runCatching {
                if (cameraProviderFuture.isDone) {
                    cameraProviderFuture.get().unbindAll()
                }
            }
            scanner.close()
            cameraExecutor.shutdown()
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Text(body, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Box(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth(),
            contentAlignment = Alignment.Center,
        ) {
            AndroidView(
                factory = { previewView },
                modifier = Modifier.fillMaxSize(),
            )
            scannerError?.let { message ->
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text(message, color = MaterialTheme.colorScheme.onErrorContainer)
                        Button(onClick = onCancel) {
                            Text(cancelLabel)
                        }
                    }
                }
            }
        }
        TextButton(onClick = onCancel, modifier = Modifier.align(Alignment.CenterHorizontally)) {
            Text(cancelLabel)
        }
    }
}

private fun analyzePairingQrCode(
    context: Context,
    imageProxy: ImageProxy,
    scanner: BarcodeScanner,
    decoded: AtomicBoolean,
    onPayloadScanned: (String) -> Unit,
) {
    if (decoded.get()) {
        imageProxy.close()
        return
    }
    val mediaImage = imageProxy.image
    if (mediaImage == null) {
        imageProxy.close()
        return
    }

    val image = InputImage.fromMediaImage(mediaImage, imageProxy.imageInfo.rotationDegrees)
    scanner.process(image)
        .addOnSuccessListener(ContextCompat.getMainExecutor(context)) { barcodes ->
            val rawValue = barcodes
                .firstOrNull { it.rawValue?.isNotBlank() == true }
                ?.rawValue
                ?.trim()
            if (!rawValue.isNullOrBlank() && decoded.compareAndSet(false, true)) {
                vibrateScan(context)
                onPayloadScanned(rawValue)
            }
        }
        .addOnCompleteListener {
            imageProxy.close()
        }
}

private fun vibrateScan(context: Context) {
    val vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        context.getSystemService(VibratorManager::class.java)?.defaultVibrator
    } else {
        @Suppress("DEPRECATION")
        context.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
    } ?: return

    if (!vibrator.hasVibrator()) return

    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        vibrator.vibrate(VibrationEffect.createOneShot(35, VibrationEffect.DEFAULT_AMPLITUDE))
    } else {
        @Suppress("DEPRECATION")
        vibrator.vibrate(35)
    }
}
