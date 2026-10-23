// "Precisa de atencao": o que do aviso fica no cliente, sem React nem
// navegador. As regras (qual fatura venceu, qual fechou, o debito automatico
// sem saldo, as recorrencias, o orcamento) e as chaves sao do servidor
// (GET /api/attention, services/attention.py); aqui ficam o texto e as
// dispensas deste aparelho.
//
// Cada aviso tem uma `key` que identifica o caso, nao o tipo: dispensar a
// "fatura vencida de outubro do Nubank" nao esconde a de novembro. O Inicio
// esconde os dispensados; o sino mostra todos enquanto valerem.
import { formatDateBR } from './format.js'

// O mes da fatura (AAAA-MM), que e o mes do vencimento.
export function invoiceMonthKey(invoice) {
  return `${invoice.invoice_year}-${String(invoice.invoice_month).padStart(2, '0')}`
}

// Vencida so depois do dia do vencimento: no proprio dia ainda se paga em dia.
// A projecao das faturas do Inicio ainda le as compras em aberto e separa as
// vencidas com isto.
export function isPastDue(dueDateText, todayText) {
  return Boolean(dueDateText) && dueDateText < todayText
}

// "Nubank · venceu em 10/10/2026", ou a mais antiga quando sao varias. Recebe
// as `invoices` do aviso INVOICE_OVERDUE, em ordem de vencimento.
export function overdueDetail(overdue) {
  return overdue.length === 1
    ? `${overdue[0].card_name} · venceu em ${formatDateBR(overdue[0].due_date)}`
    : `${overdue.length} faturas · a mais antiga venceu em ${formatDateBR(overdue[0]?.due_date)}`
}

export function undismissedItems(items, dismissedKeys = []) {
  const dismissed = new Set(dismissedKeys)
  return items.filter((item) => !dismissed.has(item.key))
}

// A lista guardada no aparelho nao cresce sem fim: fica com as mais recentes.
export const MAX_DISMISSED_KEYS = 200

export function addDismissed(dismissedKeys = [], keys = []) {
  const merged = [...dismissedKeys.filter((key) => !keys.includes(key)), ...keys]
  return merged.slice(-MAX_DISMISSED_KEYS)
}
