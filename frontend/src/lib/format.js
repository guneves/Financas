// Formatadores compartilhados (4.3 de docs/next-steps.md).
//
// formatCurrency estava copiado em cinco paginas e formatDateBR em tres. Aqui
// eles ficam em um lugar so; as paginas importam daqui.

// Modo privado: o botao do olho (Layout) esconde todo valor em dinheiro e o
// nome de usuario. Fica no localStorage do navegador e vale para todas as telas,
// porque todo valor monetario passa por formatCurrency/formatUnitCurrency ou por
// compactCurrency (charts.jsx). Quem troca o modo remonta a pagina — os
// formatadores leem o estado na hora de renderizar.
const HIDE_VALUES_KEY = '@financeMVP:hideValues'
export const MASKED_CURRENCY = 'R$ ••••••'
export const MASKED_TEXT = '••••••'

let valuesHidden = (() => {
  try {
    return localStorage.getItem(HIDE_VALUES_KEY) === '1'
  } catch {
    return false
  }
})()

export function areValuesHidden() {
  return valuesHidden
}

export function setValuesHidden(hidden) {
  valuesHidden = Boolean(hidden)
  try {
    localStorage.setItem(HIDE_VALUES_KEY, valuesHidden ? '1' : '0')
  } catch {
    // Sem localStorage o modo so dura ate recarregar a pagina.
  }
}

export function formatCurrency(value) {
  if (valuesHidden) return MASKED_CURRENCY
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(Number(value || 0))
}

// Preco unitario de ativo aceita mais casas: R$ 0,000001 e um preco valido.
export function formatUnitCurrency(value) {
  if (valuesHidden) return MASKED_CURRENCY
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
  }).format(Number(value || 0))
}

export function formatPercent(value, digits = 2) {
  return `${Number(value || 0).toFixed(digits)}%`
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
