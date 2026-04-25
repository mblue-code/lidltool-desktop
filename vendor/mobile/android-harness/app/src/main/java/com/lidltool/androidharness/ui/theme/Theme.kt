package com.lidltool.androidharness.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.draw.drawBehind
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.ui.unit.dp

private val LightColorScheme = lightColorScheme(
    primary = BluePrimaryLight,
    onPrimary = BackgroundLight,
    primaryContainer = SecondaryLight,
    onPrimaryContainer = ForegroundLight,
    secondary = SecondaryLight,
    onSecondary = Color(0xFF0E213E),
    secondaryContainer = MutedLight,
    onSecondaryContainer = ForegroundLight,
    tertiary = InfoLight,
    onTertiary = BackgroundLight,
    tertiaryContainer = Color(0xFFE1F2FD),
    onTertiaryContainer = ForegroundLight,
    background = BackgroundLight,
    onBackground = ForegroundLight,
    surface = BackgroundLight,
    onSurface = ForegroundLight,
    surfaceVariant = MutedLight,
    onSurfaceVariant = MutedForegroundLight,
    surfaceContainer = CardLight,
    surfaceContainerHigh = SecondaryLight,
    surfaceContainerHighest = MutedLight,
    outline = BorderLight,
    outlineVariant = BorderLight,
    error = ErrorLight,
    onError = BackgroundLight,
    errorContainer = Color(0xFFFFE7E8),
    onErrorContainer = ForegroundLight,
)

private val DarkColorScheme = darkColorScheme(
    primary = BluePrimaryDark,
    onPrimary = BackgroundLight,
    primaryContainer = Color(0xFF143055),
    onPrimaryContainer = ForegroundDark,
    secondary = SecondaryDark,
    onSecondary = ForegroundDark,
    secondaryContainer = MutedDark,
    onSecondaryContainer = ForegroundDark,
    tertiary = InfoDark,
    onTertiary = BackgroundLight,
    tertiaryContainer = Color(0xFF0F2740),
    onTertiaryContainer = ForegroundDark,
    background = BackgroundDark,
    onBackground = ForegroundDark,
    surface = CardDarkLowest,
    onSurface = ForegroundDark,
    surfaceVariant = MutedDark,
    onSurfaceVariant = MutedForegroundDark,
    surfaceContainerLowest = CardDarkLowest,
    surfaceContainerLow = CardDark,
    surfaceContainer = CardDark,
    surfaceContainerHigh = CardDarkHigh,
    surfaceContainerHighest = CardDarkHighest,
    surfaceBright = BackgroundTopDark,
    surfaceDim = BackgroundDark,
    outline = BorderDark,
    outlineVariant = BorderDark,
    error = ErrorDark,
    onError = BackgroundDark,
    errorContainer = Color(0xFF3A1013),
    onErrorContainer = ForegroundDark,
)

val LidlToolShapes = Shapes(
    extraSmall = androidx.compose.foundation.shape.RoundedCornerShape(6.dp),
    small = androidx.compose.foundation.shape.RoundedCornerShape(6.dp),
    medium = androidx.compose.foundation.shape.RoundedCornerShape(10.dp),
    large = androidx.compose.foundation.shape.RoundedCornerShape(14.dp),
    extraLarge = androidx.compose.foundation.shape.RoundedCornerShape(18.dp),
)

@Immutable
data class LidlToolExtendedColors(
    val success: Color,
    val warning: Color,
    val info: Color,
    val navSurface: Color,
    val navSurfaceRaised: Color,
    val navOnSurface: Color,
    val positiveContainer: Color,
    val warningContainer: Color,
    val infoContainer: Color,
)

private val LightExtendedColors = LidlToolExtendedColors(
    success = SuccessLight,
    warning = WarningLight,
    info = InfoLight,
    navSurface = SidebarLight,
    navSurfaceRaised = SidebarAccentLight,
    navOnSurface = SidebarForeground,
    positiveContainer = Color(0xFFE6F7EA),
    warningContainer = Color(0xFFFFF2D9),
    infoContainer = Color(0xFFE4F4FD),
)

private val DarkExtendedColors = LidlToolExtendedColors(
    success = SuccessDark,
    warning = WarningDark,
    info = InfoDark,
    navSurface = SidebarDark,
    navSurfaceRaised = SidebarAccentDark,
    navOnSurface = SidebarForeground,
    positiveContainer = Color(0xCC112A14),
    warningContainer = Color(0xCC332405),
    infoContainer = Color(0xCC0E2637),
)

private val LocalExtendedColors = staticCompositionLocalOf { LightExtendedColors }
private val LocalDarkTheme = compositionLocalOf { false }

object LidlToolThemeTokens {
    val extras: LidlToolExtendedColors
        @Composable
        @ReadOnlyComposable
        get() = LocalExtendedColors.current

    val isDarkTheme: Boolean
        @Composable
        @ReadOnlyComposable
        get() = LocalDarkTheme.current
}

@Composable
fun LidlToolHarnessTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val colorScheme = if (darkTheme) DarkColorScheme else LightColorScheme
    val extendedColors = if (darkTheme) DarkExtendedColors else LightExtendedColors

    CompositionLocalProvider(
        LocalExtendedColors provides extendedColors,
        LocalDarkTheme provides darkTheme,
    ) {
        MaterialTheme(
            colorScheme = colorScheme,
            typography = LidlToolTypography,
            shapes = LidlToolShapes,
            content = content,
        )
    }
}

@Composable
fun HarnessAppBackground(
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    val isDarkTheme = LidlToolThemeTokens.isDarkTheme
    val backgroundColor = MaterialTheme.colorScheme.background
    Box(
        modifier = modifier
            .fillMaxSize()
            .drawBehind {
                if (isDarkTheme) {
                    drawRect(
                        brush = Brush.linearGradient(
                            colors = listOf(BackgroundTopDark, BackgroundMidDark, BackgroundDark),
                            start = Offset.Zero,
                            end = Offset(size.width, size.height),
                        ),
                    )
                    drawRect(
                        brush = Brush.radialGradient(
                            colors = listOf(BackgroundCoolGlowDark, Color.Transparent),
                            center = Offset(size.width * 0.88f, size.height * 0.10f),
                            radius = size.maxDimension * 0.78f,
                        ),
                    )
                    drawRect(
                        brush = Brush.radialGradient(
                            colors = listOf(BackgroundWarmGlowDark, Color.Transparent),
                            center = Offset(size.width * 0.15f, size.height * 0.12f),
                            radius = size.maxDimension * 0.62f,
                        ),
                    )
                } else {
                    drawRect(color = backgroundColor)
                }
            },
    ) {
        CompositionLocalProvider(LocalContentColor provides MaterialTheme.colorScheme.onBackground) {
            content()
        }
    }
}

@Composable
fun tabularStyle(colorScheme: ColorScheme = MaterialTheme.colorScheme) =
    MaterialTheme.typography.headlineSmall.copy(
        color = colorScheme.onSurface,
        fontFeatureSettings = "tnum",
    )
