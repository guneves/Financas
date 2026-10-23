package br.financas.app.data

import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.KSerializer
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonDecoder
import kotlinx.serialization.json.JsonEncoder
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.JsonUnquotedLiteral
import java.math.BigDecimal

/**
 * Dinheiro no JSON: BigDecimal lido do texto do literal ("1234.56", 0.1, 1e+16), nunca
 * passando por Double — 0.1 vira exatamente 0.1. Escrito como numero sem aspas, em notacao
 * simples (toPlainString), que e o que o servidor le com parse_money().
 */
object BigDecimalSerializer : KSerializer<BigDecimal> {

    override val descriptor: SerialDescriptor =
        PrimitiveSerialDescriptor("br.financas.app.data.BigDecimal", PrimitiveKind.STRING)

    override fun deserialize(decoder: Decoder): BigDecimal {
        val text = if (decoder is JsonDecoder) {
            val element = decoder.decodeJsonElement()
            if (element !is JsonPrimitive || element is JsonNull) {
                throw SerializationException("Valor numerico esperado, veio $element")
            }
            element.content
        } else {
            decoder.decodeString()
        }
        return parse(text)
    }

    @OptIn(ExperimentalSerializationApi::class)
    override fun serialize(encoder: Encoder, value: BigDecimal) {
        if (encoder is JsonEncoder) {
            encoder.encodeJsonElement(JsonUnquotedLiteral(value.toPlainString()))
        } else {
            encoder.encodeString(value.toPlainString())
        }
    }

    fun parse(text: String): BigDecimal {
        val trimmed = text.trim()
        if (trimmed.isEmpty()) throw SerializationException("Valor numerico vazio")
        try {
            return BigDecimal(trimmed)
        } catch (error: NumberFormatException) {
            throw SerializationException("Valor numerico invalido: $trimmed")
        }
    }
}

/** Um valor em dinheiro vindo da API (ver BigDecimalSerializer). */
typealias Money = @Serializable(with = BigDecimalSerializer::class) BigDecimal

/**
 * Sim/nao do servidor: is_default chega como true/false (serialize_account), mas
 * credit_enabled chega como a coluna do SQLite, 0/1. Aceita os dois.
 */
object FlexibleBooleanSerializer : KSerializer<Boolean> {

    override val descriptor: SerialDescriptor =
        PrimitiveSerialDescriptor("br.financas.app.data.FlexibleBoolean", PrimitiveKind.BOOLEAN)

    override fun deserialize(decoder: Decoder): Boolean {
        if (decoder !is JsonDecoder) return decoder.decodeBoolean()
        val element = decoder.decodeJsonElement()
        if (element !is JsonPrimitive || element is JsonNull) {
            throw SerializationException("Sim/nao esperado, veio $element")
        }
        return when (element.content.trim().lowercase()) {
            "true", "1" -> true
            "false", "0", "" -> false
            else -> throw SerializationException("Sim/nao invalido: ${element.content}")
        }
    }

    override fun serialize(encoder: Encoder, value: Boolean) {
        encoder.encodeBoolean(value)
    }
}

/** 0/1 ou true/false da API (ver FlexibleBooleanSerializer). */
typealias Flag = @Serializable(with = FlexibleBooleanSerializer::class) Boolean

/**
 * O Json de toda a camada de dados: tolera campos novos do servidor (ignoreUnknownKeys) e um
 * null onde o DTO tem valor padrao (coerceInputValues).
 */
val ApiJson: Json = Json {
    ignoreUnknownKeys = true
    coerceInputValues = true
    explicitNulls = false
}
