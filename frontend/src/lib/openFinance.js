// Port: rules/OpenFinanceRules.kt (OpenFinanceRulesTest.kt) copia itemStatus, itemProblem, accountLabel,
// balanceCheck e syncSummary — mudou um, muda o outro, com um teste de cada lado.
// Ajustes › Open Finance (043): os textos e as escolhas da tela, como funcoes
// puras (testes em openFinance.test.js, `node --test`). As regras de verdade —
// o que a Pluggy traz e para onde vai — estao no servidor
// (backend/services/open_finance.py e open_finance_inbox.py).

// O estado da conexao como a Pluggy diz, em portugues, com o tom do Badge.
const STATUS = {
  UPDATED: { label: 'Atualizada', tone: 'success' },
  UPDATING: { label: 'Atualizando no banco…', tone: 'info' },
  OUTDATED: { label: 'Desatualizada', tone: 'warning' },
  LOGIN_ERROR: { label: 'Precisa entrar de novo', tone: 'danger' },
  WAITING_USER_INPUT: { label: 'Esperando um código seu', tone: 'warning' },
}

export function itemStatus(item) {
  if (!item) return { label: '', tone: 'neutral' }
  const known = STATUS[item.status]
  // Um item "atualizado" pode ainda esperar o dono (executionStatus): o aviso vence.
  if (item.needs_owner && (!known || known.tone === 'success' || known.tone === 'info')) {
    return { label: 'Precisa de você no banco', tone: 'warning' }
  }
  return known || { label: item.status || 'Sem estado', tone: 'neutral' }
}

// O que o dono faz quando a conexao espera por ele. A mensagem da Pluggy
// (ex.: o limite de CPF do plano) vem como esta, sem tentar de novo.
export function itemProblem(item) {
  if (!item) return ''
  if (item.error_message) return item.error_message
  if (item.needs_owner) return 'A conexão espera uma ação sua (senha, código ou um aceite no banco). Use "Reconectar".'
  if (item.last_sync_error) return `A última atualização falhou: ${item.last_sync_error}`
  return ''
}

// "Conta Corrente · 12345-0" / "Mastercard Black · final 9437".
export function accountLabel(account) {
  if (!account) return ''
  const name = account.name || (account.type === 'CREDIT' ? 'Cartão' : 'Conta')
  const digits = String(account.number || '').replace(/\D/g, '')
  if (!digits) return name
  return account.type === 'CREDIT' ? `${name} · final ${digits.slice(-4)}` : `${name} · ${account.number}`
}

// Para onde uma conta da Pluggy pode ir: conta do banco ativa em reais (nunca a
// Corretora) ou cartao ativo com credito; o que outra conta da Pluggy ja usa
// fica de fora (traria tudo duas vezes), menos o da propria.
export function mappingChoices(account, { accounts = [], cards = [], items = [] } = {}) {
  if (!account) return []
  const field = account.type === 'CREDIT' ? 'card_id' : 'account_id'
  const taken = new Set()
  for (const item of items) {
    for (const other of item.accounts || []) {
      if (other.id !== account.id && other[field]) taken.add(other[field])
    }
  }
  if (account.type === 'CREDIT') {
    return cards
      .filter((card) => !card.archived_at && card.credit_enabled !== false && card.credit_enabled !== 0)
      .filter((card) => !taken.has(card.id))
      .map((card) => ({ value: card.id, label: card.name }))
  }
  return accounts
    .filter((row) => !row.archived_at && row.type !== 'BROKERAGE' && (row.currency || 'BRL') === 'BRL')
    .filter((row) => !taken.has(row.id))
    .map((row) => ({ value: row.id, label: row.name }))
}

export function mappedId(account) {
  return (account?.type === 'CREDIT' ? account?.card_id : account?.account_id) || ''
}

// O payload do PUT: o campo do tipo da conta; '' desliga.
export function mappingPayload(account, value) {
  const field = account?.type === 'CREDIT' ? 'card_id' : 'account_id'
  return { [field]: value || null }
}

// Conferir o saldo, nunca ajustar: igual (ao centavo), diferente, ou sem
// comparacao (cartao, ou conta sem mapeamento).
export function balanceCheck(account) {
  if (!account || account.type === 'CREDIT' || account.app_balance == null || account.pluggy_balance == null) {
    return { state: 'none', difference: null }
  }
  const difference = Math.round((Number(account.pluggy_balance) - Number(account.app_balance)) * 100) / 100
  return { state: difference === 0 ? 'match' : 'drift', difference }
}

// O itemId que o widget Pluggy Connect devolve no onSuccess.
export function connectedItemId(data) {
  return data?.item?.id || data?.itemId || data?.id || ''
}

// O resumo de um "Atualizar" para o toast.
export function syncSummary(result) {
  const counts = result?.counts || {}
  const fresh = (counts.new || 0)
  const joined = (counts.merged || 0)
  const parts = []
  if (fresh) parts.push(fresh === 1 ? '1 movimento novo no Aprovar' : `${fresh} movimentos novos no Aprovar`)
  if (joined) parts.push(joined === 1 ? '1 juntou-se a um aviso' : `${joined} juntaram-se a avisos`)
  if (result?.removed) parts.push(result.removed === 1 ? '1 saiu (o banco desfez)' : `${result.removed} saíram (o banco desfez)`)
  return parts.length ? `${parts.join(', ')}.` : 'Nada novo.'
}

// A primeira busca: quantos dias para tras (1 a 365, a Pluggy guarda 12 meses).
export function firstSyncDaysError(value) {
  const text = String(value ?? '').trim()
  if (!/^\d+$/.test(text)) return 'Informe um número de dias.'
  const days = Number(text)
  if (days < 1 || days > 365) return 'De 1 a 365 dias.'
  return ''
}
