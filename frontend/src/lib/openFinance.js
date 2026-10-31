// Port: rules/OpenFinanceRules.kt (OpenFinanceRulesTest.kt) copia itemStatus, itemProblem, accountLabel,
// balanceCheck, syncSummary, syncHoursLabel, syncHoursChoices, checkSummary, itemBankName, checkReasonLabel e
// balanceExplanation — mudou um, muda o outro, com um teste de cada lado.
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

// O banco de uma conexao: o que os nomes das contas dizem (o servidor manda
// bank_name; o MeuPluggy, o conector do plano gratis, nao diz o banco).
export function itemBankName(item) {
  return item?.bank_name || item?.connector_name || 'Open Finance'
}

// A conta de investimentos da corretora ("BTG Investimentos"): o caixa da
// carteira, a unica que vai para a Corretora (o mesmo teste do servidor).
export function isInvestmentAccount(account) {
  const text = `${account?.name || ''} ${account?.subtype || ''}`
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
  return /\b(investimentos?|investments|corretora)\b/.test(text)
}

// "Nao usar" no seletor de destino (044): a conta fica puxada, nunca gera nada.
export const IGNORE_CHOICE = '__ignore__'

// Para onde uma conta da Pluggy pode ir: conta do banco ativa em reais (a
// Corretora so para a conta de investimentos) ou cartao ativo com credito; o
// que outra conta da Pluggy ja usa fica de fora (traria tudo duas vezes),
// menos o da propria.
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
  const brokerage = isInvestmentAccount(account)
  return accounts
    .filter((row) => !row.archived_at && (row.type === 'BROKERAGE') === brokerage && (row.currency || 'BRL') === 'BRL')
    .filter((row) => !taken.has(row.id))
    .map((row) => ({ value: row.id, label: row.name }))
}

export function mappedId(account) {
  if (account?.ignored) return IGNORE_CHOICE
  return (account?.type === 'CREDIT' ? account?.card_id : account?.account_id) || ''
}

// O payload do PUT: o campo do tipo da conta; '' desliga; IGNORE_CHOICE e "nao usar".
export function mappingPayload(account, value) {
  if (value === IGNORE_CHOICE) return { ignore: true }
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
  // O que o banco ja moveu e ainda espera o par (um Pix no prazo) nao e diferenca.
  const waiting = Number(account.check?.explanation?.awaiting || 0) / 100
  return { state: Math.round((difference - waiting) * 100) === 0 ? 'match' : 'drift', difference }
}

// O itemId que o widget Pluggy Connect devolve no onSuccess.
export function connectedItemId(data) {
  return data?.item?.id || data?.itemId || data?.id || ''
}

// O resumo de um "Atualizar" para o toast. Com "Gravar sozinho" (044), o que
// foi gravado/ligado sai do "novo no Revisar" (so fica o que espera o dono).
export function syncSummary(result) {
  const counts = result?.counts || {}
  const auto = result?.auto_recorded || {}
  const recorded = auto.recorded || 0
  const linked = auto.linked || 0
  const fresh = Math.max((counts.new || 0) - recorded - linked, 0)
  const joined = (counts.merged || 0)
  const operations = result?.investments?.recorded || 0
  const parts = []
  if (recorded) parts.push(recorded === 1 ? '1 lançamento gravado' : `${recorded} lançamentos gravados`)
  if (linked) parts.push(linked === 1 ? '1 ligado ao que você lançou' : `${linked} ligados ao que você lançou`)
  if (fresh) parts.push(fresh === 1 ? '1 movimento novo no Revisar' : `${fresh} movimentos novos no Revisar`)
  if (joined) parts.push(joined === 1 ? '1 juntou-se a um aviso' : `${joined} juntaram-se a avisos`)
  if (operations) parts.push(operations === 1 ? '1 operação na carteira' : `${operations} operações na carteira`)
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

// "Busca automatica" (Ajustes; sync_hours no servidor): 0 desliga, nunca
// abaixo de 6 h (dono, 2026-10-27: a Pluggy so traz dado novo do banco de 6 em
// 6 a 24 h, e o app so le). Um valor fora da lista (gravado pela API) aparece
// tambem, para nao sumir.
export const MIN_SYNC_HOURS = 6
export const SYNC_HOURS_CHOICES = [0, 6, 12, 24]

export function syncHoursLabel(hours) {
  const value = Number(hours)
  if (!value) return 'Desligada'
  return `A cada ${value} h`
}

export function syncHoursChoices(current) {
  const values = [...SYNC_HOURS_CHOICES]
  const value = Number(current)
  if (Number.isInteger(value) && value >= MIN_SYNC_HOURS && value <= 24 && !values.includes(value)) {
    values.push(value)
    values.sort((a, b) => a - b)
  }
  return values.map((hours) => ({ value: hours, label: syncHoursLabel(hours) }))
}

// A conferencia de uma conta (check do servidor): o banco contra o app, so
// apontando. 'none' sem conferencia (sem mapeamento ou ainda sem busca),
// 'match' sem diferenca, 'drift' com algo so de um lado. O que espera no
// Aprovar nao e diferenca: so e dito.
export function checkSummary(check) {
  if (!check) return { state: 'none', text: '' }
  const bank = Number(check.bank_only_count || 0)
  const app = Number(check.app_only_count || 0)
  const awaiting = Number(check.awaiting_count || 0)
  const parts = []
  if (bank) parts.push(bank === 1 ? '1 só no banco' : `${bank} só no banco`)
  if (app) parts.push(app === 1 ? '1 só no app' : `${app} só no app`)
  if (awaiting) parts.push(awaiting === 1 ? '1 espera no Revisar' : `${awaiting} esperam no Revisar`)
  if (!bank && !app) {
    return { state: 'match', text: parts.length ? `Movimentos conferem · ${parts.join(' · ')}` : 'Movimentos conferem' }
  }
  return { state: 'drift', text: parts.join(' · ') }
}

// Por que um movimento esta so de um lado (o `reason` de cada linha da
// conferencia), em portugues.
const CHECK_REASONS = {
  awaiting: 'espera no Revisar',
  denied: 'recusado no Revisar',
  unmapped: 'a conta ainda sem destino',
  changed_after_edit: 'o banco mudou o valor depois que você editou',
  invoice_payment_missing: 'pagamento de fatura sem o pagamento no app',
  invoice_payment_linked: 'pagamento de fatura',
  different_amount_or_date: 'lançado com outro valor ou data',
  not_in_bank: 'o banco não tem',
}

export function checkReasonLabel(reason) {
  return CHECK_REASONS[reason] || ''
}

// De onde vem a diferenca de saldo (explanation do servidor, em centavos):
// so no banco, esperando no Revisar, so no app, e o que ja era diferente antes
// da conferencia (o saldo inicial no app, um lancamento antigo). Linhas de
// texto; [] sem diferenca.
export function balanceExplanation(explanation, money = (value) => String(value)) {
  if (!explanation || !explanation.difference) return []
  const lines = []
  const part = (cents, text) => {
    if (cents) lines.push(`${money(cents / 100)} ${text}`)
  }
  part(explanation.bank_only, 'de movimentos só no banco')
  part(explanation.awaiting, 'esperando no Revisar')
  part(explanation.app_only, 'de lançamentos só no app')
  part(explanation.before, 'de antes da conferência (confira o saldo inicial da conta)')
  return lines
}

// O texto de "Gravar sozinho": o que faz ligado, ou por que nao liga
// (auto_record_blockers do servidor).
export function autoRecordHint(settings) {
  if (!settings) return ''
  if (settings.auto_record) {
    return 'Os movimentos dos bancos conectados viram lançamentos sozinhos, a revisar no Extrato. Só espera uma transferência sem a outra ponta.'
  }
  const blockers = settings.auto_record_blockers || []
  if (blockers.length) return blockers.join(' ')
  return 'Ligado, o que a Pluggy traz é lançado sem passar pelo Aprovar; o que já espera lá vindo dela é lançado na hora.'
}

// A previa do historico, por conta: "12 a gravar · 3 a ligar · 1 só no app".
export function historyLine(account) {
  if (!account) return ''
  const parts = []
  const add = (count, one, many) => {
    if (count) parts.push(count === 1 ? one : many.replace('{n}', count))
  }
  add(account.to_record, '1 a gravar', '{n} a gravar')
  add(account.to_link, '1 a ligar ao que você lançou', '{n} a ligar ao que você lançou')
  add(account.linked, '1 já ligado', '{n} já ligados')
  add(account.waiting, '1 fica no Revisar', '{n} ficam no Revisar')
  add(account.app_only, '1 só no app (fica como está)', '{n} só no app (ficam como estão)')
  return parts.length ? parts.join(' · ') : 'Nada a fazer'
}

// A carteira da corretora contra a do app (investments do servidor).
export function portfolioSummary(investments) {
  if (!investments) return { state: 'none', text: '' }
  const mismatched = Number(investments.mismatched_count || 0)
  const held = (investments.held || []).length
  const parts = []
  if (mismatched) parts.push(mismatched === 1 ? '1 ativo com quantidade diferente' : `${mismatched} ativos com quantidade diferente`)
  if (held) parts.push(held === 1 ? '1 operação para você lançar' : `${held} operações para você lançar`)
  return parts.length ? { state: 'drift', text: parts.join(' · ') } : { state: 'match', text: 'Carteira confere' }
}

const HELD_REASONS = {
  type: 'renda fixa, Tesouro, custódia ou cupom: lance você',
  unknown_asset: 'ativo fora da lista da B3',
  incomplete: 'a corretora mandou sem quantidade ou preço',
}

export function heldReasonLabel(reason) {
  const text = String(reason || '')
  if (text.startsWith('corporate_action')) return 'antes de um evento corporativo do ativo'
  if (text.startsWith('refused')) return text.split(': ').slice(1).join(': ') || 'recusada'
  return HELD_REASONS[text] || text
}
