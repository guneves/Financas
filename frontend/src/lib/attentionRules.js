// "Precisa de atencao": o que do aviso fica no cliente, sem React nem
// navegador. As regras (qual fatura venceu, qual fechou, o debito automatico
// sem saldo, as recorrencias, o orcamento) e as chaves sao do servidor
// (GET /api/attention, services/attention.py); aqui ficam o texto e as
// dispensas deste aparelho.
//
// Cada aviso tem uma `key` que identifica o caso, nao o tipo: dispensar a
// "fatura vencida de outubro do Nubank" nao esconde a de novembro. O Inicio
// esconde os dispensados; o sino mostra todos enquanto valerem.
//
// Port: android/.../rules/AttentionRules.kt (AttentionRulesTest.kt, os mesmos
// casos): o texto, os links, o selo do sino e as dispensas. Mudou um, muda o
// outro.
import { formatCurrency, formatDateBR } from './format.js'

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

// Titulo e detalhe de um aviso (os cartoes do Inicio e o sino). O saldo da
// conta, e o que falta (que o revela), passam por `privateMoney`: no modo
// privado e o formatador que mascara (lib/privacy.js).
export function attentionText(item, privateMoney = formatCurrency) {
  switch (item.kind) {
    case 'INVOICE_OVERDUE':
      return { title: `Fatura vencida: ${formatCurrency(item.total)}`, detail: `${overdueDetail(item.invoices || [])} · ${item.item_count} lançamento(s)` }
    case 'INVOICE_PAYABLE':
      return { title: `Fatura fechada: ${formatCurrency(item.total)}`, detail: 'O pagamento já está liberado.' }
    case 'AUTOPAY_SHORTFALL':
      return {
        title: `Débito automático sem saldo: faltam ${privateMoney(item.missing)}`,
        detail: `${item.account_name} tem ${privateMoney(item.balance)} para ${formatCurrency(item.total)} a debitar · o primeiro em ${formatDateBR(item.first_due)}`,
      }
    case 'RECURRING':
      return { title: `${item.count} ${item.count === 1 ? 'recorrência vencida' : 'recorrências vencidas'}`, detail: '' }
    case 'OVER_BUDGET':
      return { title: `${item.category_name} passou do orçamento`, detail: `${formatCurrency(item.spent)} de ${formatCurrency(item.available)}` }
    default:
      return { title: '', detail: '' }
  }
}

// Para onde cada aviso leva quando nao ha uma acao na propria tela.
export const ATTENTION_LINKS = {
  INVOICE_OVERDUE: { to: '/lancamentos/cartoes', label: 'Ver faturas' },
  INVOICE_PAYABLE: { to: '/lancamentos/cartoes', label: 'Ver faturas' },
  AUTOPAY_SHORTFALL: { to: '/lancamentos/cartoes', label: 'Ver faturas' },
  RECURRING: { to: '/planejamento/recorrentes', label: 'Ver recorrentes' },
  OVER_BUDGET: { to: '/planejamento/orcamento', label: 'Ver orçamento' },
}

export function attentionLink(kind) {
  return ATTENTION_LINKS[kind] || null
}

// O numero no sino: todos os avisos de agora, dispensados inclusive; acima de
// 9, "9+". Sem aviso, nada.
export function bellBadge(count) {
  if (!count) return ''
  return count > 9 ? '9+' : String(count)
}

export function bellLabel(count) {
  return count ? `Precisa de atenção: ${count} ${count === 1 ? 'aviso' : 'avisos'}` : 'Precisa de atenção: nenhum aviso'
}
