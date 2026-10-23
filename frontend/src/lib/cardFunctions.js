// Porte: mudou um, muda o outro, com um teste de cada lado (par nativo:
// android/app/src/main/java/br/financas/app/rules/CardFunctions.kt e CardFunctionsTest.kt).
//
// As funcoes de um cartao (migration 041): credito, debito ou os dois.
//
// Credito e o de sempre: fatura, parcelas, debito automatico. Debito e uma conta
// (`debit_account_id`): a compra no debito e uma despesa comum nessa conta, sem
// fatura. Um cartao so debito (o Flash, um cartao de debito puro) tem
// `credit_enabled` 0 e nao aparece onde se escolhe cartao de credito (Cartoes,
// Aprovar, a fatura). Puro: testado em cardFunctions.test.js.

export const CARD_FUNCTION_ITEMS = [
  { value: 'CREDIT', label: 'Crédito' },
  { value: 'DEBIT', label: 'Débito' },
  { value: 'BOTH', label: 'Os dois' },
]

export const hasCredit = (card) => Boolean(card) && card.credit_enabled !== 0 && card.credit_enabled !== false

export const hasDebit = (card) => Boolean(card?.debit_account_id)

// Os cartoes onde uma compra vai para a fatura.
export const creditCards = (cards) => (cards || []).filter(hasCredit)

// 'CREDIT' | 'DEBIT' | 'BOTH' de um cartao gravado (o valor do seletor de Ajustes).
export function cardFunctionOf(card) {
  if (hasCredit(card) && hasDebit(card)) return 'BOTH'
  return hasDebit(card) && !hasCredit(card) ? 'DEBIT' : 'CREDIT'
}

export function cardFunctionLabel(card) {
  const value = cardFunctionOf(card)
  return value === 'BOTH' ? 'Crédito e débito' : value === 'DEBIT' ? 'Débito' : 'Crédito'
}

// Como a compra pode ser feita neste cartao, na ordem do seletor do "+ Novo".
export function cardMethods(card) {
  if (!card) return []
  const methods = []
  if (hasCredit(card)) methods.push('CREDIT')
  if (hasDebit(card)) methods.push('DEBIT')
  return methods
}

// O metodo que vale: o escolhido, se o cartao o tem; senao o primeiro dele.
export function resolveCardMethod(card, chosen) {
  const methods = cardMethods(card)
  return methods.includes(chosen) ? chosen : (methods[0] || 'CREDIT')
}

const dayOf = (value) => {
  const day = Number(value)
  return Number.isInteger(day) && day >= 1 && day <= 31 ? day : null
}

// O corpo de POST/PATCH /api/credit-cards a partir do formulario de Ajustes,
// ou { error } com o que falta. `form.functions` e 'CREDIT' | 'DEBIT' | 'BOTH'.
export function cardFormPayload(form) {
  const name = String(form?.name || '').trim()
  if (!name) return { error: 'Informe o nome do cartão.' }
  const functions = form.functions || 'CREDIT'
  const credit = functions !== 'DEBIT'
  const debit = functions !== 'CREDIT'
  const payload = { name, credit_enabled: credit, debit_account_id: debit ? form.debit_account_id || null : null }
  if (debit && !payload.debit_account_id) return { error: 'Escolha a conta de onde sai a compra no débito.' }
  if (credit) {
    const dueDay = dayOf(form.due_day)
    const closingDay = dayOf(form.closing_day)
    if (!dueDay || !closingDay) return { error: 'Informe o vencimento e o fechamento do cartão (dia de 1 a 31).' }
    payload.due_day = dueDay
    payload.closing_day = closingDay
  }
  if ('autopay_account_id' in (form || {})) {
    payload.autopay_account_id = credit ? form.autopay_account_id || null : null
  }
  return { payload }
}

// A compra no debito vira uma despesa na conta do cartao (POST /api/transactions).
export function debitPurchasePayload(card, { amount, date, categoryId, category, description }) {
  return {
    amount,
    date,
    category_id: categoryId,
    category,
    description,
    type: 'EXPENSE',
    account_id: card.debit_account_id,
  }
}
