// Porte: mudou um, muda o outro, com um teste de cada lado (par nativo de SHARE_OPTIONS,
// shareFormFrom, shareFormError e sharePayload: android/app/src/main/java/br/financas/app/
// rules/Sharing.kt e SharingTest.kt; o resto deste arquivo nao foi portado).
//
// De quem e o gasto (032,backend/services/sharing.py). Um lancamento ou uma
// compra no cartao pode ser inteiro de outra pessoa (OTHERS) ou dividido
// (SPLIT, com a parte dos outros em share_others_amount), sempre com o nome
// dela. O dinheiro sai da conta do mesmo jeito: o saldo nao muda. Muda o que e
// "do dono" — o Fluxo de caixa mostra a parte dos outros a parte, e Despesas
// por categoria conta so a parte dele. A parte dos outros de uma despesa fica
// em "A receber" ate o dono marcar que a pessoa pagou.
//
// Puro: sem navegador, React ou lib/api.js (testado com node --test).
import { formatCurrency } from './format.js'

export const SHARE_OPTIONS = [
  { value: '', label: 'Só minha' },
  { value: 'SPLIT', label: 'Dividida' },
  { value: 'OTHERS', label: 'De outra pessoa' },
]

const toCents = (value) => Math.round((Number(value) || 0) * 100)

// Quanto da linha e de outra pessoa, em reais.
export function othersAmount(item) {
  if (item?.share_mode === 'OTHERS') return Number(item.amount) || 0
  if (item?.share_mode === 'SPLIT') return Number(item.share_others_amount) || 0
  return 0
}

// A parte do dono: o que conta como gasto (ou renda) dele.
export function ownAmount(item) {
  return ((toCents(item?.amount) - toCents(othersAmount(item))) / 100)
}

export const isShared = (item) => Boolean(item?.share_mode)

// Uma linha curta para a lista: "Dividida com Ana · sua parte R$ 40,00".
export function shareSummary(item) {
  if (!isShared(item)) return ''
  const person = item.share_person || 'outra pessoa'
  if (item.share_mode === 'OTHERS') return `De ${person}`
  return `Dividida com ${person} · sua parte ${formatCurrency(ownAmount(item))}`
}

// Os campos do formulario a partir da linha gravada.
export function shareFormFrom(item) {
  return {
    share_mode: item?.share_mode || '',
    share_person: item?.share_person || '',
    share_others_amount: item?.share_mode === 'SPLIT' ? String(item.share_others_amount ?? '') : '',
  }
}

// Confere o formulario contra o valor total; devolve a mensagem ou ''.
export function shareFormError(form, amount) {
  if (!form?.share_mode) return ''
  if (!String(form.share_person || '').trim()) return 'Informe o nome da pessoa.'
  if (form.share_mode === 'SPLIT') {
    const others = Number(form.share_others_amount)
    if (!Number.isFinite(others) || others <= 0) return 'Informe a parte da outra pessoa.'
    if (toCents(others) >= toCents(amount)) return 'A parte da outra pessoa deve ser menor que o valor. Se é tudo dela, escolha "De outra pessoa".'
  }
  return ''
}

// O que vai no PATCH. "Só minha" manda share_mode null, que limpa tudo.
export function sharePayload(form) {
  if (!form?.share_mode) return { share_mode: null }
  const payload = { share_mode: form.share_mode, share_person: String(form.share_person || '').trim() }
  if (form.share_mode === 'SPLIT') payload.share_others_amount = Number(form.share_others_amount)
  return payload
}

// "A receber" por pessoa: o total pendente dela e os itens, do maior total
// para o menor. O nome agrupa sem diferenciar maiusculas nem espacos.
export function groupReceivables(items = []) {
  const groups = new Map()
  items.forEach((item) => {
    const name = String(item.person || '').trim() || 'Sem nome'
    const key = name.toLocaleLowerCase('pt-BR')
    if (!groups.has(key)) groups.set(key, { person: name, totalCents: 0, items: [] })
    const group = groups.get(key)
    group.totalCents += toCents(item.others_amount)
    group.items.push(item)
  })
  return [...groups.values()]
    .map(({ totalCents, ...group }) => ({ ...group, total: totalCents / 100 }))
    .sort((a, b) => b.total - a.total || a.person.localeCompare(b.person, 'pt-BR'))
}

// Os ids que POST /api/receivables/settle espera, de uma lista de itens.
export function settlePayload(items = [], settled = true) {
  return {
    transaction_ids: items.filter((item) => item.kind === 'TRANSACTION').map((item) => item.id),
    cc_expense_ids: items.filter((item) => item.kind === 'CARD_PURCHASE').map((item) => item.id),
    settled,
  }
}
