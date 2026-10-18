// Aprovar (Lançamentos › Aprovar): os textos e as contas da tela, como funcoes
// puras — nada aqui toca em rede ou React, entao os testes rodam com
// `node --test` (inboxRules.test.js). As regras de verdade (o que junta com o
// que, o que fica lembrado, o que vira lancamento) estao no servidor
// (backend/services/inbox.py e inbox_decisions.py); aqui so se diz isso em
// portugues e se monta o pedido.

export const ENTRY_TYPE_LABELS = {
  EXPENSE: 'Despesa',
  INCOME: 'Receita',
  TRANSFER: 'Transferência',
  CARD: 'Cartão de crédito',
}

export function entryTypeLabel(type) {
  return ENTRY_TYPE_LABELS[type] || 'Crédito ou débito?'
}

const KIND_LABELS = {
  CREDIT_PURCHASE: 'compra no crédito',
  DEBIT_PURCHASE: 'compra no débito',
  PURCHASE: 'compra (sem crédito/débito)',
  PIX_OUT: 'Pix enviado',
  PIX_IN: 'Pix recebido',
  TRANSFER_OUT: 'transferência enviada',
  TRANSFER_IN: 'transferência recebida',
  REFUND: 'estorno',
  DECLINED: 'compra negada',
}

// De onde veio cada fonte do item, numa linha.
export function sourceLabel(source) {
  if (!source) return ''
  const app = source.app_label || source.app || 'Notificação'
  const kind = KIND_LABELS[source.kind]
  const card = source.card_last4 ? `final ${source.card_last4}` : source.card_name || ''
  return [`Notificação ${app}`, kind, card].filter(Boolean).join(' · ')
}

// "via Samsung Wallet" quando so o Samsung avisou: o banco nao notificou.
export function onlySamsung(item) {
  const notifications = (item?.sources || []).filter((source) => source.source === 'notification')
  return notifications.length > 0 && notifications.every((source) => source.app === 'com.samsung.android.spay')
}

// A hora como a fonte disse, sem converter fuso: "2026-10-17T22:30:00-03:00"
// e 17/10/2026 às 22:30 em qualquer aparelho. So a data, quando a fonte nao
// tem hora.
export function splitOccurredAt(occurredAt) {
  const text = String(occurredAt || '')
  const date = text.slice(0, 10)
  const time = text.length > 10 ? text.slice(11, 16) : ''
  return { date, time }
}

export function whenText(occurredAt) {
  const { date, time } = splitOccurredAt(occurredAt)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return ''
  const [year, month, day] = date.split('-')
  const day_ = `${day}/${month}/${year}`
  return time ? `${day_} às ${time}` : day_
}

// O que o dono corrigiu na data/hora, para o PATCH. Hora vazia: so a data. O
// fuso fica o do item (o servidor completa).
export function composeOccurredAt(date, time) {
  if (!date) return ''
  return time ? `${date}T${time}` : date
}

// O sinal do valor na lista: sai (-), entra (+), transferencia sem sinal.
export function amountSign(item) {
  if (item?.entry_type === 'TRANSFER') return 0
  return item?.direction === 'IN' ? 1 : -1
}

export const NEED_TEXTS = {
  method: 'Foi no crédito ou no débito?',
  card: 'Qual cartão?',
  account: 'Qual conta?',
  transfer_account: 'Para qual conta?',
  amount: 'Confira o valor em reais (compra em outra moeda).',
}

export function needText(need) {
  return NEED_TEXTS[need] || 'Falta escolher algo.'
}

export const CONFIRM_TEXTS = {
  card: 'Cartão preenchido por palpite: confirme.',
  account: 'Conta preenchida por palpite: confirme.',
  transfer_account: 'Conta de destino preenchida por palpite: confirme.',
}

// Por que o item espera (alem do normal "aprovar ou recusar").
export function reasonText(item) {
  switch (item?.reason) {
    case 'several_candidates':
      return 'Há mais de um lançamento parecido já gravado. Se um deles for este, toque em "É este"; se não, aprove para lançar.'
    case 'possible_duplicate':
      return 'Parece um lançamento que já está no app. Se for, toque em "É este" para não contar duas vezes.'
    case 'installments_differ':
      return 'Há uma compra de mesmo total com outro número de parcelas. Se for a mesma, toque em "É este".'
    case 'out_of_reach':
      return 'Parece uma transferência, um pagamento de fatura ou um movimento da carteira que já está no app. Se for, toque em "É este".'
    case 'own_transfer':
      return 'Entre suas contas: entra como transferência e não conta como entrada nem saída.'
    default:
      return ''
  }
}

export const DECISION_LABELS = {
  APPROVED: 'Aprovado',
  MATCHED: 'Já estava lançado',
  DENIED: 'Recusado',
  REMOVED: 'Saiu',
}

export function decisionText(item) {
  if (item?.state === 'REMOVED') {
    return item.reason === 'declined' ? 'Compra negada pelo banco' : 'Saiu da lista'
  }
  if (item?.state === 'MATCHED' && item.reason === 'created_elsewhere') return 'Lançado pelo "+ Novo"'
  return DECISION_LABELS[item?.state] || ''
}

// Fontes que podem ser separadas ("não é a mesma"): toda notificacao ligada
// ao item.
export function splittableSources(item) {
  const sources = (item?.sources || []).filter((source) => (
    source.source === 'notification' && ['SOURCE', 'PAIRED'].includes(source.role)
  ))
  return sources.length > 1 ? sources : []
}

export function readyIds(items = []) {
  return items.filter((item) => item.ready).map((item) => item.id)
}

// Que tipo de lancamento parecido ja gravado e cada candidato.
export const CANDIDATE_KIND_LABELS = {
  entry: 'Lançamento',
  card_purchase: 'Compra no cartão',
  transfer: 'Transferência',
  invoice_payment: 'Pagamento de fatura',
  investment_cash: 'Pela carteira',
  proceed: 'Provento',
}

export function candidateKindLabel(kind) {
  return CANDIDATE_KIND_LABELS[kind] || 'Lançamento'
}

// O formulario de edicao a partir do item.
export function draftFromItem(item) {
  const { date, time } = splitOccurredAt(item?.occurred_at)
  return {
    entry_type: item?.entry_type || '',
    amount: item?.amount ?? '',
    date,
    time,
    description: item?.description || '',
    category: item?.category || '',
    account_id: item?.account_id || '',
    card_id: item?.card_id || '',
    transfer_account_id: item?.transfer_account_id || '',
    installments: item?.installments || 1,
  }
}

// O PATCH/approve: so o que mudou em relacao ao item, mais a versao.
export function changesFromDraft(item, draft) {
  const original = draftFromItem(item)
  const changes = {}
  if (draft.entry_type && draft.entry_type !== original.entry_type) changes.entry_type = draft.entry_type
  if (Number(draft.amount) !== Number(original.amount)) changes.amount = Number(draft.amount)
  if (draft.date !== original.date || (draft.time || '') !== original.time) {
    changes.occurred_at = composeOccurredAt(draft.date, draft.time)
  }
  const description = String(draft.description || '').trim()
  if (description !== original.description) changes.description = description || null
  if ((draft.category || '') !== original.category) changes.category = draft.category || null
  ;['account_id', 'card_id', 'transfer_account_id'].forEach((key) => {
    if ((draft[key] || '') !== original[key]) changes[key] = draft[key] || null
  })
  if (Number(draft.installments || 1) !== Number(original.installments || 1)) {
    changes.installments = Number(draft.installments) || 1
  }
  return { version: item?.version, ...changes }
}

// Uma escolha rapida no cartao do item (credito/debito, qual cartao, qual
// conta): o pedido que a grava, ja com o tipo certo.
export function quickChoice(item, choice) {
  const body = { version: item?.version }
  if (choice.method === 'CARD') body.entry_type = 'CARD'
  if (choice.method === 'DEBIT') body.entry_type = item?.direction === 'IN' ? 'INCOME' : 'EXPENSE'
  if (choice.card_id !== undefined) body.card_id = choice.card_id || null
  if (choice.account_id !== undefined) body.account_id = choice.account_id || null
  if (choice.transfer_account_id !== undefined) body.transfer_account_id = choice.transfer_account_id || null
  return body
}

// Lembrar so faz sentido quando havia o que decidir.
export function offersRemember(item) {
  return Boolean(item?.needs?.length || item?.confirm?.length)
}

// O aviso do Extrato e do cabecalho.
export function pendingNoticeText(count) {
  if (!count) return ''
  return count === 1
    ? '1 movimento do celular ou do banco espera sua aprovação.'
    : `${count} movimentos do celular ou do banco esperam sua aprovação.`
}

// O toast do "+ Novo" quando o que foi digitado ja esperava em Aprovar.
export function matchedInboxNotice(data, label) {
  const row = Array.isArray(data) ? data[0] : data
  if (!row?.matched_inbox) return ''
  return `${label}: já esperava em Aprovar (do celular ou do banco). Ficou um lançamento só.`
}

// O resultado de "Aprovar prontos".
export function approveReadySummary(result) {
  const approved = result?.approved?.length || 0
  const skipped = result?.skipped?.length || 0
  if (!approved && !skipped) return 'Nada para aprovar.'
  const parts = [`${approved} ${approved === 1 ? 'aprovado' : 'aprovados'}`]
  if (skipped) parts.push(`${skipped} ${skipped === 1 ? 'ficou' : 'ficaram'} para você decidir`)
  return `${parts.join(', ')}.`
}

// Uma escolha lembrada, numa linha: "Samsung Wallet · sem crédito/débito · final 1234 → Itaú Visa".
export function hintText(hint) {
  if (!hint) return ''
  const target = hint.entry_type === 'TRANSFER'
    ? `transferência para ${hint.transfer_account_name || '?'}`
    : hint.entry_type === 'CARD'
      ? hint.card_name || 'cartão removido'
      : `${hint.account_name || 'conta removida'}${hint.entry_type === 'INCOME' ? ' (receita)' : ''}`
  return `${hint.label || hint.hint_key} → ${target}`
}
