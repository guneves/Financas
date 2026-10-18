// Helpers de Lancamentos (Extrato, Cartoes) e do sheet "+ Novo".
// Movidos de Transactions.jsx sem mudanca de comportamento.
import { cardPurchaseKey } from '../../lib/transactions'

// Relogio local: as datas padrao passam por aqui, nao por `new Date()` direto
// (ver CLAUDE.md › Known sharp edges).
export function getNow() {
  return new Date()
}

export function getLocalDateString(date = getNow()) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

// Diferente do formatDateBR de lib/format.js: devolve '' (e nao '-') sem data.
export function formatDateBR(dateString) {
  if (!dateString) return ''
  const [year, month, day] = dateString.split('-')
  return `${day}/${month}/${year}`
}

export function parseLocalDate(dateString) {
  if (!dateString) return null
  const [year, month, day] = dateString.split('-').map(Number)
  return new Date(year, month - 1, day)
}

export function parseInstallmentInfo(value) {
  if (!value || typeof value !== 'string' || !value.includes('/')) {
    return { current: 1, total: 1 }
  }

  const [current, total] = value.split('/').map(Number)

  return {
    current: Number.isFinite(current) ? current : 1,
    total: Number.isFinite(total) ? total : 1,
  }
}

// A compra de uma parcela: o client_id dela (lib/transactions.js).
export function getPurchaseGroupKey(expense) {
  return cardPurchaseKey(expense)
}

export function formatInvoiceLabel(month, year) {
  return `${String(month).padStart(2, '0')}/${year}`
}

export function readStoredJson(key, fallback) {
  try {
    const saved = localStorage.getItem(key)
    return saved ? JSON.parse(saved) : fallback
  } catch {
    localStorage.removeItem(key)
    return fallback
  }
}

export function readStoredNumber(key, fallback = 0) {
  const parsed = Number(localStorage.getItem(key))
  return Number.isFinite(parsed) ? parsed : fallback
}

export function categoryLabel(category) {
  return category.parent_name ? `${category.parent_name} > ${category.name}` : category.name
}

// Opcoes de categoria vindas da tabela de categorias (nunca de lista fixa).
// O valor de um select de categoria e o id: o nome se repete ("Outros" na raiz
// e em "Lazer › Outros") e o servidor ficaria com a primeira que achasse.
export function buildCategoryOptions(categories) {
  return categories.map((category) => ({
    id: category.id,
    name: category.name,
    label: categoryLabel(category),
    kind: category.kind,
    parent_id: category.parent_id || null,
  }))
}

// O id para um nome so (um item antigo da fila, guardado antes do id): a
// raiz antes, como o servidor faz.
export function categoryIdForName(options, name) {
  if (!name) return ''
  const matches = options.filter((option) => option.name === name)
  return (matches.find((option) => !option.parent_id) || matches[0])?.id || ''
}

export function categoryNameOf(options, id) {
  return options.find((option) => option.id === id)?.name || ''
}

export function filterCategoryOptions(options, type) {
  if (type === 'INCOME') {
    return options.filter((option) => option.kind !== 'EXPENSE')
  }
  return options.filter((option) => option.kind !== 'INCOME')
}

export function pickDefaultAccountId(accounts) {
  const preferred = accounts.find((account) => account.is_default) || accounts[0]
  return preferred?.id || ''
}
