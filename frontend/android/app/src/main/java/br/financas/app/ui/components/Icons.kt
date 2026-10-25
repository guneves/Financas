package br.financas.app.ui.components

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.unit.dp

/**
 * Os icones das telas nativas: os mesmos da web (lucide-react), desenhados dos caminhos SVG
 * deles (24 x 24, traco 2, pontas redondas). Sem biblioteca de icones: o Material 3 atual nao
 * traz mais nenhum, e o app precisa de poucos. Use com Icon(..., tint = cor do LocalPalette).
 */
object AppIcons {
    private fun icon(name: String, vararg paths: String): ImageVector {
        val builder = ImageVector.Builder(
            name = name,
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f,
        )
        paths.forEach { data ->
            builder.addPath(
                pathData = PathParser().parsePathString(data).toNodes(),
                fill = null,
                stroke = SolidColor(Color.Black),
                strokeLineWidth = 2f,
                strokeLineCap = StrokeCap.Round,
                strokeLineJoin = StrokeJoin.Round,
            )
        }
        return builder.build()
    }

    // O <circle> do SVG como dois arcos.
    private fun circle(cx: Float, cy: Float, r: Float): String =
        "M${cx - r} ${cy}a$r $r 0 1 0 ${2 * r} 0a$r $r 0 1 0 ${-2 * r} 0"

    // O <rect rx> do SVG.
    private fun rect(x: Float, y: Float, w: Float, h: Float, r: Float): String =
        "M${x + r} ${y}h${w - 2 * r}a$r $r 0 0 1 $r ${r}v${h - 2 * r}a$r $r 0 0 1 ${-r} ${r}" +
            "h${-(w - 2 * r)}a$r $r 0 0 1 ${-r} ${-r}v${-(h - 2 * r)}a$r $r 0 0 1 $r ${-r}z"

    private const val BELL_BODY = "M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"
    private const val BELL_CLAPPER = "M10.3 21a1.94 1.94 0 0 0 3.4 0"

    val Bell: ImageVector by lazy { icon("bell", BELL_BODY, BELL_CLAPPER) }
    val BellRing: ImageVector by lazy {
        icon("bell-ring", BELL_BODY, BELL_CLAPPER, "M4 2C2.8 3.7 2 5.7 2 8", "M22 8c0-2.3-.8-4.3-2-6")
    }
    val Eye: ImageVector by lazy {
        icon("eye", "M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z", circle(12f, 12f, 3f))
    }
    val EyeOff: ImageVector by lazy {
        icon(
            "eye-off",
            "M9.88 9.88a3 3 0 1 0 4.24 4.24",
            "M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68",
            "M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61",
            "M2 2l20 20",
        )
    }
    val X: ImageVector by lazy { icon("x", "M18 6L6 18", "M6 6l12 12") }
    val ChevronRight: ImageVector by lazy { icon("chevron-right", "M9 18l6-6-6-6") }
    val ChevronDown: ImageVector by lazy { icon("chevron-down", "M6 9l6 6 6-6") }
    val Paperclip: ImageVector by lazy {
        icon(
            "paperclip",
            "M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48",
        )
    }
    val Search: ImageVector by lazy { icon("search", circle(11f, 11f, 8f), "M21 21l-4.3-4.3") }
    val Download: ImageVector by lazy {
        icon("download", "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4", "M7 10l5 5 5-5", "M12 15V3")
    }
    val CreditCard: ImageVector by lazy { icon("credit-card", rect(2f, 5f, 20f, 14f, 2f), "M2 10h20") }
    val Wallet: ImageVector by lazy {
        icon(
            "wallet",
            "M21 12V7H5a2 2 0 0 1 0-4h14v4",
            "M3 5v14a2 2 0 0 0 2 2h16v-5",
            "M18 12a2 2 0 0 0 0 4h4v-4Z",
        )
    }
    val Repeat: ImageVector by lazy {
        icon("repeat", "M17 2l4 4-4 4", "M3 11v-1a4 4 0 0 1 4-4h14", "M7 22l-4-4 4-4", "M21 13v1a4 4 0 0 1-4 4H3")
    }
    val Target: ImageVector by lazy {
        icon("target", circle(12f, 12f, 10f), circle(12f, 12f, 6f), circle(12f, 12f, 2f))
    }
    val Plus: ImageVector by lazy { icon("plus", "M5 12h14", "M12 5v14") }
    val Minus: ImageVector by lazy { icon("minus", "M5 12h14") }
    val Undo: ImageVector by lazy { icon("undo-2", "M9 14 4 9l5-5", "M4 9h10.5a5.5 5.5 0 0 1 0 11H11") }
    val Home: ImageVector by lazy {
        icon("home", "M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z", "M9 22V12h6v10")
    }
    val Receipt: ImageVector by lazy {
        icon(
            "receipt",
            "M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z",
            "M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8",
            "M12 17.5v-11",
        )
    }
    val Briefcase: ImageVector by lazy {
        icon("briefcase", rect(2f, 7f, 20f, 14f, 2f), "M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16")
    }
    val Settings: ImageVector by lazy {
        icon("settings-2", "M20 7h-9", "M14 17H5", circle(17f, 17f, 3f), circle(7f, 7f, 3f))
    }
    val Info: ImageVector by lazy { icon("info", circle(12f, 12f, 10f), "M12 16v-4", "M12 8h.01") }
    val CheckCircle: ImageVector by lazy { icon("check-circle-2", circle(12f, 12f, 10f), "M9 12l2 2 4-4") }
    val ArrowUpRight: ImageVector by lazy { icon("arrow-up-right", "M7 7h10v10", "M7 17 17 7") }
    val ArrowDownRight: ImageVector by lazy { icon("arrow-down-right", "m7 7 10 10", "M17 7v10H7") }
    val CloudOff: ImageVector by lazy {
        icon("cloud-off", "m2 2 20 20", "M5.782 5.782A7 7 0 0 0 9 19h8.5a4.5 4.5 0 0 0 1.307-.193",
            "M21.532 16.5A4.5 4.5 0 0 0 17.5 10h-1.79A7.008 7.008 0 0 0 10 5.07")
    }
}
