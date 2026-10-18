// Os textos e as contas da tela da Pluggy (Ajustes › Banco), como funcoes
// puras: nada aqui toca em rede ou React, entao os testes rodam com
// `node --test` (pluggyRules.test.js). As regras de verdade — o que confirma,
// o que entra, o que espera o dono — estao no servidor
// (backend/services/pluggy_sync.py); aqui so se diz isso em portugues.

// Uma sincronizacao que mudou algo no servidor pede para as telas lerem de novo.
const CHANGE_KEYS = ['created', 'attached', 'updated', 'removed', 'review']

export function syncChangedData(result) {
  return CHANGE_KEYS.some((key) => Number(result?.[key]) > 0)
}

function plural(count, one, many) {
  return `${count} ${count === 1 ? one : many}`
}

// O resumo de uma sincronizacao pedida pelo botao.
export function syncSummary(result) {
  if (!result) return 'Não foi possível falar com o servidor.'
  if (result.status === 'not_configured') return 'A Pluggy não está configurada no servidor.'
  if (result.status === 'running') return 'Uma sincronização já está em andamento.'
  if (result.status === 'skipped') return result.message || 'Sincronizado há pouco.'
  const parts = []
  if (result.created) parts.push(plural(result.created, 'novo', 'novos'))
  if (result.attached) parts.push(plural(result.attached, 'conferido', 'conferidos'))
  if (result.updated) parts.push(plural(result.updated, 'atualizado', 'atualizados'))
  if (result.removed) parts.push(plural(result.removed, 'removido', 'removidos'))
  if (result.review) parts.push(plural(result.review, 'para revisar', 'para revisar'))
  const body = parts.length ? `Banco: ${parts.join(', ')}.` : 'Nada novo no banco.'
  if (result.status === 'error') return `A Pluggy não respondeu. ${result.message || ''}`.trim()
  if (result.status === 'partial') return `${body} Algumas contas não responderam: ${(result.failed || []).join(', ')}.`
  return body
}

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

// Por que uma transacao do banco espera o dono ("Possivel duplicata").
export function reviewReasonText(item) {
  if (item?.reason === 'several_candidates') {
    return 'Há mais de um lançamento parecido (mesma conta, valor e data próxima). Escolha qual é este, ou lance separado.'
  }
  if (item?.reason === 'installments_differ') {
    return 'Há uma compra de mesmo total com outro número de parcelas. Se for a mesma, confirme; se não, lance separado.'
  }
  if (item?.reason === 'out_of_reach') {
    const kinds = [...new Set((item.candidates || [])
      .map((candidate) => candidate.kind)
      .filter((kind) => kind && kind !== 'entry' && kind !== 'card_purchase'))]
      .map((kind) => candidateKindLabel(kind).toLowerCase())
    const what = kinds.length ? kinds.join(' ou ') : 'um lançamento de outra tela'
    return `Parece ${what} que já está no app. Se for, confirme para não contar duas vezes.`
  }
  return 'Confira antes de lançar.'
}

// O que um lancamento conferido tem de diferente do que o banco diz.
export function differenceText(difference, formatCurrency = (value) => String(value), formatDate = (value) => value) {
  if (!difference) return ''
  const parts = []
  if (difference.amount !== undefined) parts.push(`valor ${formatCurrency(difference.amount)}`)
  if (difference.date) parts.push(`data ${formatDate(difference.date)}`)
  return parts.length ? `No banco: ${parts.join(', ')}.` : ''
}

// Para onde uma conta da Pluggy pode ir: conta corrente/poupanca vai para uma
// conta do app (ativa); cartao, para um cartao.
export function linkTargets(pluggyAccount, { accounts = [], cards = [] } = {}) {
  if (pluggyAccount?.type === 'CREDIT') {
    return cards.map((card) => ({ id: card.id, name: card.name }))
  }
  return accounts
    .filter((account) => !account.archived_at)
    .map((account) => ({ id: account.id, name: account.name }))
}

// A ligacao a gravar (PUT /api/pluggy/links/<conta da Pluggy>).
export function linkPayload(pluggyAccount, { itemRowId, targetId, since }) {
  const base = {
    item: itemRowId,
    type: pluggyAccount.type === 'CREDIT' ? 'CREDIT' : 'BANK',
    name: [pluggyAccount.name, pluggyAccount.number].filter(Boolean).join(' · '),
    since,
  }
  return base.type === 'CREDIT' ? { ...base, card_id: targetId } : { ...base, account_id: targetId }
}

export function pluggyAccountLabel(account) {
  const kind = account?.type === 'CREDIT' ? 'Cartão' : 'Conta'
  return [kind, account?.name, account?.number].filter(Boolean).join(' · ')
}

// A ultima sincronizacao entre as conexoes (ISO), ou ''.
export function lastSyncAt(items = []) {
  return items
    .map((item) => item.last_sync_at || '')
    .filter(Boolean)
    .sort()
    .pop() || ''
}

export function reviewCount(status) {
  return Number(status?.counts?.REVIEW) || 0
}

// O aviso do Extrato quando ha possiveis duplicatas esperando o dono.
export function reviewNoticeText(count) {
  if (!count) return ''
  return count === 1
    ? '1 transação do banco espera você decidir se já está lançada.'
    : `${count} transações do banco esperam você decidir se já estão lançadas.`
}

// O status de uma conexao (item) na Pluggy, em portugues; o desconhecido sai como veio.
const ITEM_STATUS_LABELS = {
  UPDATED: 'Atualizada',
  UPDATING: 'Atualizando',
  OUTDATED: 'Desatualizada',
  LOGIN_ERROR: 'Erro de login no banco',
  WAITING_USER_INPUT: 'Esperando você no banco',
  WAITING_USER_ACTION: 'Esperando você no banco',
  CREATED: 'Criada',
}

export function itemStatusLabel(status) {
  if (!status) return 'Sem status'
  return ITEM_STATUS_LABELS[status] || status
}

// A marca de um lancamento no extrato: veio do banco, ou o banco conferiu.
export function bankMark(transaction) {
  if (!transaction?.external_id) return ''
  return transaction.source_type === 'PLUGGY' ? 'Veio do banco (Pluggy)' : 'Conferido pelo banco (Pluggy)'
}

// O toast do "+ Novo" quando o servidor confirmou uma linha que a Pluggy ja
// tinha trazido, em vez de criar outra (matched_bank).
export function matchedBankNotice(data, label) {
  const row = Array.isArray(data) ? data[0] : data
  if (!row?.matched_bank) return ''
  return `${label}: já estava no extrato, trazida pelo banco. Ficou uma só, com a sua categoria.`
}
