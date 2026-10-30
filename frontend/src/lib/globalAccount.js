// Porte: mudou um, muda o outro, com um teste de cada lado. Par nativo:
// android/.../rules/GlobalAccount.kt (GlobalAccountTest.kt), os mesmos casos de globalAccount.test.js.
//
// Conta global (dono, 2026-10-27): a conta em dolar (Wise) e a unica tela do app
// fora de reais. Ela mostra o saldo e o extrato na moeda da conta e, embaixo, um
// "≈ R$ …" pelo cambio de hoje (PTAX, services/fx.py) ou "sem câmbio hoje". Em
// qualquer outro lugar a conta aparece em reais (accountBalanceBrl()) em Ajustes;
// o saldo em contas do Inicio NAO a soma (dono, 2026-10-30).
//
// O Pix de uma conta em reais para ela e UMA transferencia (047): `amount` e o
// que saiu em reais, `transfer_amount` o que entrou em dolar. Sem
// `transfer_amount` (a conta virou global depois, e a Pluggy ainda nao trouxe o
// credito), o dolar e "a conferir" e fica fora do saldo — como no servidor.
// Modulo puro: testado com node --test.

export const GLOBAL_ACCOUNT_LABEL = 'Conta global'

export const accountCurrency = (account) => String(account?.currency || 'BRL').toUpperCase()

export const isGlobalAccount = (account) => Boolean(account) && accountCurrency(account) !== 'BRL'

// As contas globais ativas, na ordem da lista de contas.
export const globalAccounts = (accounts = []) =>
  accounts.filter((account) => isGlobalAccount(account) && !account.archived_at)

// As contas do "Saldo em conta": sem a global (dono, 2026-10-30). O total do
// servidor (`consolidated_balance`) tambem a deixa de fora, entao o total e a
// soma das contas listadas. A global so aparece na entrada "Conta global", na
// tela dela e em Ajustes > Contas.
export const withoutGlobal = (accounts = []) => accounts.filter((account) => !isGlobalAccount(account))

// A linha do extrato da conta global, vista dela: valor na moeda dela, com
// sinal (+ entra, − sai), ou `pending` quando o dolar de uma transferencia de
// reais ainda nao chegou. `counterpart` e a outra conta da transferencia.
export function globalStatementRow(row, accountId, accountsById = {}) {
  const amount = Number(row.amount) || 0
  if (row.type === 'TRANSFER') {
    if (row.transfer_account_id === accountId) {
      const received = row.transfer_amount === null || row.transfer_amount === undefined
        ? null
        : Number(row.transfer_amount) || 0
      return {
        ...row,
        direction: 1,
        native: received,
        pending: received === null,
        // O que saiu da outra conta, em reais: so para dizer de onde veio.
        source_amount: amount,
        counterpart: accountsById[row.account_id]?.name || null,
      }
    }
    return {
      ...row,
      direction: -1,
      native: amount,
      pending: false,
      counterpart: accountsById[row.transfer_account_id]?.name || null,
    }
  }
  return {
    ...row,
    direction: row.type === 'INCOME' ? 1 : -1,
    native: amount,
    pending: false,
    counterpart: null,
  }
}

export function globalStatement(rows = [], accountId, accountsById = {}) {
  return rows
    .filter((row) => row.account_id === accountId || row.transfer_account_id === accountId)
    .map((row) => globalStatementRow(row, accountId, accountsById))
}

// Entradas e saidas do extrato carregado, na moeda da conta (sem o "a conferir").
export function globalTotals(statement = []) {
  let cents = { in: 0, out: 0 }
  for (const row of statement) {
    if (row.pending || row.native === null) continue
    const value = Math.round(row.native * 100)
    cents = row.direction > 0 ? { ...cents, in: cents.in + value } : { ...cents, out: cents.out + value }
  }
  return { in: cents.in / 100, out: cents.out / 100, pending: statement.filter((row) => row.pending).length }
}

// A linha "≈ R$ …": o saldo em reais que o servidor ja converteu
// (`balance_brl`, PTAX de hoje), ou null sem cambio hoje.
export function brlHint(account) {
  if (!isGlobalAccount(account)) return null
  const value = account?.balance_brl
  return value === null || value === undefined ? null : Number(value) || 0
}

// O cambio do Pix (reais por dolar), para a linha do extrato: "R$ 5,50 por US$".
export function impliedRate(row) {
  if (!row || row.pending || !row.native || !row.source_amount) return null
  return Math.round((row.source_amount / row.native) * 10000) / 10000
}
