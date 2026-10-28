// Port: mudou um, muda o outro, com um teste de cada lado. O app nativo tem a copia em
// frontend/android/app/src/main/java/br/financas/app/core/Format.kt (testes em FormatTest.kt).
//
// Formatadores compartilhados (4.3 de docs/next-steps.md).
//
// formatCurrency estava copiado em cinco paginas e formatDateBR em tres. Aqui
// eles ficam em um lugar so; as paginas importam daqui.

// O modo privado (lib/privacy.js) nao passa por aqui: os formatadores sempre
// mostram o valor, e quem exibe um valor sensivel usa usePrivateFormatter().

// Sinal de menos de verdade (U+2212): o hifen do Intl e mais curto que o "+",
// e com numeros tabulares as colunas deixam de alinhar pelo sinal.
const MINUS = '−'

function withTrueMinus(text) {
  return text.replace('-', MINUS)
}

export function formatCurrency(value) {
  return withTrueMinus(new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(Number(value || 0)))
}

// So a tela da Conta global (pages/ContaGlobal.jsx) mostra outra moeda: o saldo
// e o extrato da conta em dolar, "US$ 46,10". Em qualquer outro lugar e real.
export function formatForeignCurrency(value, currency = 'USD') {
  return withTrueMinus(new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency,
  }).format(Number(value || 0)))
}

export function formatSignedForeignCurrency(value, sign, currency = 'USD') {
  const amount = Math.abs(Number(value || 0))
  const direction = sign ?? Math.sign(Number(value || 0))
  const body = formatForeignCurrency(amount, currency)
  if (!direction || amount === 0) return body
  return `${direction > 0 ? '+' : MINUS}${body}`
}

// Valor com sinal explicito, para listas de entradas e saidas: "+R$ 8.500,00",
// "−R$ 1.048,22". `sign` (1, -1 ou 0) vale quando o valor vem sempre positivo
// e o sentido esta no tipo do lancamento; zero sai sem sinal. O espaco depois
// do "R$" e inquebravel (Intl), entao sinal e numero nunca se separam.
export function formatSignedCurrency(value, sign) {
  const amount = Math.abs(Number(value || 0))
  const direction = sign ?? Math.sign(Number(value || 0))
  const body = formatCurrency(amount)
  if (!direction || amount === 0) return body
  return `${direction > 0 ? '+' : MINUS}${body}`
}

// Preco unitario de ativo aceita mais casas: R$ 0,000001 e um preco valido.
export function formatUnitCurrency(value) {
  return withTrueMinus(new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
  }).format(Number(value || 0)))
}

// Quantidade de cotas: "1.022", "62,7", "0,333333" — separadores do pt-BR. Um
// numero cru sairia "1022" e, numa fracao (bonificacao, desdobramento), "62.7",
// que no Brasil se le como 627.
export function formatQuantity(value) {
  return withTrueMinus(Number(value || 0).toLocaleString('pt-BR', { maximumFractionDigits: 8 }))
}

// "12,50%", com virgula. `signed` poe "+" nos positivos (rentabilidade).
export function formatPercent(value, digits = 2, { signed = false } = {}) {
  const number = Number(value || 0)
  const text = withTrueMinus(number.toLocaleString('pt-BR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }))
  return `${signed && number > 0 ? '+' : ''}${text}%`
}

// Data vem do backend como 'AAAA-MM-DD'. Fatiar e montar com new Date(y, m, d)
// evita o fuso: new Date('2026-09-01') e UTC e volta um dia antes no Brasil.
export function parseLocalDate(value) {
  if (!value) return null
  const [year, month, day] = String(value).slice(0, 10).split('-').map(Number)
  if (!year || !month || !day) return null
  return new Date(year, month - 1, day)
}

export function formatDateBR(value, fallback = '-') {
  const date = parseLocalDate(value)
  if (!date || Number.isNaN(date.getTime())) return fallback
  return date.toLocaleDateString('pt-BR')
}

export function getLocalDateString(date = new Date()) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

// Um instante do servidor (utc_timestamp(), '...Z') no dia local 'AAAA-MM-DD'.
// Fatiar o texto dava o dia em UTC: depois das 21h no Brasil, o dia seguinte.
export function localDateOfTimestamp(value) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : getLocalDateString(date)
}

// 'AAAA-MM' — a chave de mes que o backend usa em orcamentos.
export function monthKey(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}

export function monthLabel(key) {
  const [year, month] = String(key || '').split('-').map(Number)
  if (!year || !month) return String(key || '')
  return new Date(year, month - 1, 1).toLocaleDateString('pt-BR', {
    month: 'long',
    year: 'numeric',
  })
}

// Rotulo curto de mes para eixos e legendas: 'AAAA-MM' ou 'MM/AA' -> 'out/25'.
// Um formato so no app (eram tres: 'out/25', '10/25' e '2026-01').
export function shortMonthLabel(key) {
  const text = String(key || '')
  let year
  let month
  if (/^\d{4}-\d{2}/.test(text)) {
    [year, month] = text.split('-').map(Number)
  } else if (/^\d{2}\/\d{2}$/.test(text)) {
    const [mm, yy] = text.split('/').map(Number)
    month = mm
    year = 2000 + yy
  } else {
    return text
  }
  const name = new Date(year, month - 1, 1).toLocaleDateString('pt-BR', { month: 'short' }).replace('.', '')
  return `${name}/${String(year).slice(2)}`
}

export function shiftMonth(key, offset) {
  const [year, month] = String(key).split('-').map(Number)
  const index = year * 12 + (month - 1) + offset
  return `${String(Math.floor(index / 12)).padStart(4, '0')}-${String((index % 12) + 1).padStart(2, '0')}`
}

// E-mail mascarado para exibir na tela: as duas primeiras letras do usuario, a
// primeira do dominio e o final (".com"). "fulano@gmail.com" -> "fu•••@g•••.com".
export function maskEmail(email) {
  const text = String(email || '').trim()
  const at = text.lastIndexOf('@')
  if (at < 1) return text ? `${text.slice(0, 2)}•••` : ''
  const local = text.slice(0, at)
  const domain = text.slice(at + 1)
  const dot = domain.indexOf('.')
  const name = dot > 0 ? domain.slice(0, dot) : domain
  const suffix = dot > 0 ? domain.slice(dot) : ''
  const keep = local.length > 2 ? 2 : 1
  return `${local.slice(0, keep)}•••@${name.slice(0, 1)}•••${suffix}`
}
