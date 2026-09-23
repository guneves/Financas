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

export function shiftMonth(key, offset) {
  const [year, month] = String(key).split('-').map(Number)
  const index = year * 12 + (month - 1) + offset
  return `${String(Math.floor(index / 12)).padStart(4, '0')}-${String((index % 12) + 1).padStart(2, '0')}`
}
