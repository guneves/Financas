import { useEffect, useMemo, useState } from 'react'
import {
  Banknote,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  CreditCard,
  Landmark,
  Plus,
  Receipt,
  Trash2,
  Wallet,
} from 'lucide-react'
import { ccExpensesApi, creditCardsApi, transactionsApi } from '../lib/dataApi'
import {
  Badge,
  Button,
  EmptyState,
  Field,
  IconButton,
  MetricCard,
  PageHeader,
  Panel,
  PanelHeader,
  SegmentedControl,
  cx,
} from '../components/ui'

const CATEGORY_OPTIONS = ['Receita', 'Investimento', 'Alimentação', 'Moradia', 'Transporte', 'Saúde', 'Educação', 'Lazer', 'Serviços', 'Outros']

function getNow() {
  return new Date()
}

function getLocalDateString(date = getNow()) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function formatDateBR(dateString) {
  if (!dateString) return ''
  const [year, month, day] = dateString.split('-')
  return `${day}/${month}/${year}`
}

function parseLocalDate(dateString) {
  if (!dateString) return null
  const [year, month, day] = dateString.split('-').map(Number)
  return new Date(year, month - 1, day)
}

function parseInstallmentInfo(value) {
  if (!value || typeof value !== 'string' || !value.includes('/')) {
    return { current: 1, total: 1 }
  }

  const [current, total] = value.split('/').map(Number)

  return {
    current: Number.isFinite(current) ? current : 1,
    total: Number.isFinite(total) ? total : 1,
  }
}

function getPurchaseGroupKey(expense) {
  const installment = parseInstallmentInfo(expense.installment_info)
  return [
    expense.card_id || 'sem-cartao',
    expense.description || 'sem-descricao',
    expense.purchase_date || 'sem-data',
    expense.category || 'sem-categoria',
    Number(parseFloat(expense.amount || 0).toFixed(2)),
    installment.total,
  ].join('|')
}

function formatInvoiceLabel(month, year) {
  return `${String(month).padStart(2, '0')}/${year}`
}

function formatCurrency(value) {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(Number(value || 0))
}

function readStoredJson(key, fallback) {
  try {
    const saved = localStorage.getItem(key)
    return saved ? JSON.parse(saved) : fallback
  } catch {
    localStorage.removeItem(key)
    return fallback
  }
}

function readStoredNumber(key, fallback = 0) {
  const parsed = Number(localStorage.getItem(key))
  return Number.isFinite(parsed) ? parsed : fallback
}

export default function Transactions() {
  const [activeTab, setActiveTab] = useState('CONTA')
  const [dataError, setDataError] = useState('')
  const [saving, setSaving] = useState(false)

  const [transactions, setTransactions] = useState(() => {
    return readStoredJson('@financeMVP:transactions', [])
  })
  const [balance, setBalance] = useState(() => {
    return readStoredNumber('@financeMVP:balance')
  })

  const [cards, setCards] = useState(() => {
    return readStoredJson('@financeMVP:cards', [])
  })
  const [ccExpenses, setCcExpenses] = useState(() => {
    return readStoredJson('@financeMVP:ccExpenses', [])
  })
  const [projectedBalanceGlobal, setProjectedBalanceGlobal] = useState(() => {
    return readStoredNumber('@financeMVP:projectedBalanceGlobal')
  })
  const [projectedBalanceNextMonth, setProjectedBalanceNextMonth] = useState(() => {
    return readStoredNumber('@financeMVP:projectedBalanceNextMonth')
  })

  const [transForm, setTransForm] = useState({ amount: '', date: '', category: '', description: '', type: 'EXPENSE' })
  const [cardForm, setCardForm] = useState({ name: '', due_day: '', closing_day: '' })
  const [expenseForm, setExpenseForm] = useState({ card_id: '', category: '', description: '', total_amount: '', purchase_date: '', installments: '1' })
  const [expandedCards, setExpandedCards] = useState([])

  const toggleCardExpenses = (cardId) => {
    setExpandedCards((prev) =>
      prev.includes(cardId) ? prev.filter((id) => id !== cardId) : [...prev, cardId]
    )
  }

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    setDataError('')

    try {
      const [tData, cData, ccData] = await Promise.all([
        transactionsApi.list(),
        creditCardsApi.list(),
        ccExpensesApi.list({ status: 'OPEN' }),
      ])

      const safeTransactions = tData || []
      const safeCards = cData || []
      const safeCreditExpenses = ccData || []

      setTransactions(safeTransactions)
      localStorage.setItem('@financeMVP:transactions', JSON.stringify(safeTransactions))

      const currentBalance = safeTransactions.reduce((acc, curr) => {
        const amount = Number(curr.amount || 0)
        return curr.type === 'INCOME' ? acc + amount : acc - amount
      }, 0)
      setBalance(currentBalance)
      localStorage.setItem('@financeMVP:balance', currentBalance.toString())

      setCards(safeCards)
      localStorage.setItem('@financeMVP:cards', JSON.stringify(safeCards))

      setCcExpenses(safeCreditExpenses)
      localStorage.setItem('@financeMVP:ccExpenses', JSON.stringify(safeCreditExpenses))

      const today = getNow()
      const currentMonth = today.getMonth() + 1
      const currentYear = today.getFullYear()

      let nextMonth = currentMonth + 1
      let nextYear = currentYear
      if (nextMonth > 12) {
        nextMonth = 1
        nextYear += 1
      }

      const totalOpenCredit = safeCreditExpenses.reduce((acc, curr) => acc + Number(curr.amount || 0), 0)
      const projGlobal = currentBalance - totalOpenCredit
      setProjectedBalanceGlobal(projGlobal)
      localStorage.setItem('@financeMVP:projectedBalanceGlobal', projGlobal.toString())

      const creditUpToNextMonth = safeCreditExpenses.reduce((acc, curr) => {
        const isPastOrCurrent = curr.invoice_year < currentYear || (curr.invoice_year === currentYear && curr.invoice_month <= currentMonth)
        const isNextMonth = curr.invoice_year === nextYear && curr.invoice_month === nextMonth

        if (isPastOrCurrent || isNextMonth) {
          return acc + Number(curr.amount || 0)
        }
        return acc
      }, 0)

      const projNextMonth = currentBalance - creditUpToNextMonth
      setProjectedBalanceNextMonth(projNextMonth)
      localStorage.setItem('@financeMVP:projectedBalanceNextMonth', projNextMonth.toString())
    } catch (error) {
      console.warn('Erro ao carregar movimentacoes:', error)
      setDataError(error.message || 'Nao foi possivel carregar os dados financeiros.')
    }
  }

  const openInvoicesByCard = useMemo(() => {
    const groupedByCard = ccExpenses.reduce((acc, expense) => {
      const cardKey = expense.card_id || 'sem-cartao'
      const invoiceKey = `${expense.invoice_year}-${String(expense.invoice_month).padStart(2, '0')}`

      if (!acc[cardKey]) {
        acc[cardKey] = {
          cardId: expense.card_id,
          cardName: expense.credit_cards?.name || 'Cartão',
          dueDay: expense.credit_cards?.due_day,
          closingDay: expense.credit_cards?.closing_day,
          invoices: {},
        }
      }

      if (!acc[cardKey].invoices[invoiceKey]) {
        acc[cardKey].invoices[invoiceKey] = {
          invoiceKey,
          invoiceMonth: expense.invoice_month,
          invoiceYear: expense.invoice_year,
          total: 0,
          purchases: {},
        }
      }

      acc[cardKey].invoices[invoiceKey].total += parseFloat(expense.amount)

      const purchaseKey = getPurchaseGroupKey(expense)
      const installment = parseInstallmentInfo(expense.installment_info)

      if (!acc[cardKey].invoices[invoiceKey].purchases[purchaseKey]) {
        acc[cardKey].invoices[invoiceKey].purchases[purchaseKey] = {
          purchaseKey,
          card_id: expense.card_id,
          description: expense.description,
          category: expense.category || 'Outros',
          purchase_date: expense.purchase_date,
          amount: parseFloat(expense.amount),
          installmentCurrent: installment.current,
          installmentTotal: installment.total,
        }
      }
      return acc
    }, {})

    return Object.values(groupedByCard)
      .map((cardGroup) => ({
        ...cardGroup,
        invoices: Object.values(cardGroup.invoices).sort((a, b) => {
          if (a.invoiceYear !== b.invoiceYear) return a.invoiceYear - b.invoiceYear
          return a.invoiceMonth - b.invoiceMonth
        }).map((invoice) => ({
          ...invoice,
          purchases: Object.values(invoice.purchases).sort((a, b) => a.description.localeCompare(b.description)),
        })),
      }))
      .sort((a, b) => a.cardName.localeCompare(b.cardName))
  }, [ccExpenses])

  const handleBankSubmit = async (event) => {
    event.preventDefault()
    const amount = Number(transForm.amount)
    if (!Number.isFinite(amount) || amount <= 0) {
      setDataError('Informe um valor bancario valido.')
      return
    }

    setSaving(true)
    setDataError('')
    try {
      await transactionsApi.create({
        amount,
        date: transForm.date,
        category: transForm.category,
        description: transForm.description,
        type: transForm.type,
      })
      setTransForm({ amount: '', date: '', category: '', description: '', type: 'EXPENSE' })
      await fetchData()
    } catch (error) {
      setDataError(error.message || 'Nao foi possivel criar o lancamento.')
    } finally {
      setSaving(false)
    }
  }

  const handleDueDayChange = (event) => {
    const due = parseInt(event.target.value)
    let closing = ''
    if (!Number.isNaN(due)) {
      closing = due - 7
      if (closing <= 0) closing += 30
    }
    setCardForm({ ...cardForm, due_day: event.target.value, closing_day: closing.toString() })
  }

  const handleCreateCard = async (event) => {
    event.preventDefault()
    const dueDay = Number(cardForm.due_day)
    const closingDay = Number(cardForm.closing_day)
    if (!cardForm.name.trim() || !Number.isInteger(dueDay) || !Number.isInteger(closingDay)) {
      setDataError('Preencha os dados do cartao corretamente.')
      return
    }

    setSaving(true)
    setDataError('')
    try {
      await creditCardsApi.create({
        name: cardForm.name,
        due_day: dueDay,
        closing_day: closingDay,
      })
      setCardForm({ name: '', due_day: '', closing_day: '' })
      await fetchData()
    } catch (error) {
      setDataError(error.message || 'Nao foi possivel criar o cartao.')
    } finally {
      setSaving(false)
    }
  }

  const handleCCExpenseSubmit = async (event) => {
    event.preventDefault()
    const totalAmount = Number(expenseForm.total_amount)
    const installmentsCount = Number(expenseForm.installments)
    const purchaseDate = parseLocalDate(expenseForm.purchase_date)
    const selectedCard = cards.find((card) => card.id === expenseForm.card_id)

    if (!selectedCard || !purchaseDate || Number.isNaN(purchaseDate.getTime()) || !Number.isFinite(totalAmount) || totalAmount <= 0 || !Number.isInteger(installmentsCount) || installmentsCount <= 0) {
      setDataError('Preencha a compra no cartao com valores validos.')
      return
    }

    const amountPerInstallment = totalAmount / installmentsCount

    const dueDay = selectedCard.due_day
    const closingDay = selectedCard.closing_day || (dueDay - 7 > 0 ? dueDay - 7 : 30 + (dueDay - 7))

    const purchaseDay = purchaseDate.getDate()

    let invoiceMonth = purchaseDate.getMonth() + 1
    let invoiceYear = purchaseDate.getFullYear()

    if (closingDay < dueDay) {
      if (purchaseDay >= closingDay) invoiceMonth += 1
    } else if (purchaseDay < closingDay) {
      invoiceMonth += 1
    } else {
      invoiceMonth += 2
    }

    while (invoiceMonth > 12) {
      invoiceMonth -= 12
      invoiceYear += 1
    }

    let currentMonth = invoiceMonth
    let currentYear = invoiceYear

    const inserts = []
    for (let i = 1; i <= installmentsCount; i += 1) {
      inserts.push({
        card_id: expenseForm.card_id,
        category: expenseForm.category,
        description: expenseForm.description,
        amount: amountPerInstallment.toFixed(2),
        purchase_date: expenseForm.purchase_date,
        invoice_month: currentMonth,
        invoice_year: currentYear,
        installment_info: `${i}/${installmentsCount}`,
        status: 'OPEN',
      })
      currentMonth += 1
      if (currentMonth > 12) {
        currentMonth = 1
        currentYear += 1
      }
    }

    setSaving(true)
    setDataError('')
    try {
      await ccExpensesApi.create(inserts)
      setExpenseForm({ card_id: cards[0]?.id || '', category: '', description: '', total_amount: '', purchase_date: '', installments: '1' })
      await fetchData()
    } catch (error) {
      setDataError(error.message || 'Nao foi possivel criar a compra no cartao.')
    } finally {
      setSaving(false)
    }
  }

  const handlePayInvoice = async (invoice, cardGroup) => {
    if (!window.confirm(`Deseja pagar a fatura ${formatInvoiceLabel(invoice.invoiceMonth, invoice.invoiceYear)} do cartão ${cardGroup.cardName} no valor de ${formatCurrency(invoice.total)}?`)) return

    setSaving(true)
    setDataError('')
    try {
      await transactionsApi.create({
        type: 'EXPENSE',
        amount: Number(invoice.total.toFixed(2)),
        date: getLocalDateString(),
        category: `Pagamento Fatura ${cardGroup.cardName}`,
        description: `Fatura ${formatInvoiceLabel(invoice.invoiceMonth, invoice.invoiceYear)}`,
      })

      await ccExpensesApi.updateInvoiceStatus({
        card_id: cardGroup.cardId,
        invoice_month: invoice.invoiceMonth,
        invoice_year: invoice.invoiceYear,
        status: 'PAID',
        current_status: 'OPEN',
      })

      await fetchData()
    } catch (error) {
      setDataError(error.message || 'Nao foi possivel pagar a fatura.')
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteTransaction = async (id) => {
    if (!window.confirm('Deseja realmente excluir esta transação? O saldo será recalculado.')) return
    try {
      await transactionsApi.remove(id)
      await fetchData()
    } catch (error) {
      setDataError(error.message || 'Nao foi possivel excluir a transacao.')
    }
  }

  const handleDeleteCCPurchase = async (purchase) => {
    if (!window.confirm(`Deseja excluir a compra "${purchase.description}" e eliminar todas as faturas vinculadas a ela?`)) return

    let candidates = []
    try {
      candidates = await ccExpensesApi.candidates({
        card_id: purchase.card_id,
        description: purchase.description,
        purchase_date: purchase.purchase_date,
        category: purchase.category,
      })
    } catch (error) {
      setDataError(error.message || 'Nao foi possivel localizar as faturas da compra.')
      return
    }

    const idsToDelete = (candidates || [])
      .filter((item) => {
        const installment = parseInstallmentInfo(item.installment_info)
        return Number(parseFloat(item.amount).toFixed(2)) === Number(parseFloat(purchase.amount).toFixed(2))
          && installment.total === purchase.installmentTotal
      })
      .map((item) => item.id)

    if (idsToDelete.length === 0) {
      alert('Nenhuma fatura vinculada foi encontrada para essa compra.')
      return
    }

    try {
      await ccExpensesApi.removeMany(idsToDelete)
      await fetchData()
    } catch (error) {
      setDataError(error.message || 'Nao foi possivel excluir a compra.')
    }
  }

  const handleDeleteCard = async (id, name) => {
    if (!window.confirm(`ATENÇÃO: Deseja realmente excluir o cartão "${name}"?\nIsso apagará TODAS as faturas vinculadas a ele. Esta ação não pode ser desfeita.`)) return

    try {
      await creditCardsApi.remove(id)
      await fetchData()
    } catch (error) {
      setDataError(error.message || 'Nao foi possivel excluir o cartao.')
    }
  }

  const getInvoiceStatus = (year, month, dueDay) => {
    const today = getNow()
    const dueDate = new Date(year, month - 1, dueDay)
    if (today > dueDate) return <Badge tone="danger">Em atraso</Badge>
    return <Badge tone="warning">Aberta</Badge>
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Operação"
        title="Movimentações"
        description="Lançamentos bancários, cartões e faturas em aberto."
        actions={(
          <SegmentedControl
            value={activeTab}
            onChange={setActiveTab}
            items={[
              { value: 'CONTA', label: 'Conta corrente', icon: Wallet },
              { value: 'CARTOES', label: 'Cartões', icon: CreditCard },
            ]}
          />
        )}
      />

      {dataError ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-800">
          {dataError}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <MetricCard
          icon={Landmark}
          tone={balance >= 0 ? 'success' : 'danger'}
          title="Saldo atual"
          value={formatCurrency(balance)}
          valueClassName={balance >= 0 ? 'text-zinc-950' : 'text-rose-600'}
          subtitle="Movimentações confirmadas"
        />
        <MetricCard
          icon={Banknote}
          tone={projectedBalanceNextMonth >= 0 ? 'info' : 'danger'}
          title="Projeção próximo mês"
          value={formatCurrency(projectedBalanceNextMonth)}
          valueClassName={projectedBalanceNextMonth >= 0 ? 'text-sky-700' : 'text-rose-600'}
          subtitle="Inclui faturas próximas"
        />
        <MetricCard
          icon={Receipt}
          tone={projectedBalanceGlobal >= 0 ? 'neutral' : 'danger'}
          title="Projeção global"
          value={formatCurrency(projectedBalanceGlobal)}
          valueClassName={projectedBalanceGlobal >= 0 ? 'text-zinc-950' : 'text-rose-600'}
          subtitle="Inclui parcelamentos futuros"
        />
      </div>

      {activeTab === 'CONTA' ? (
        <div className="space-y-6">
          <Panel>
            <PanelHeader title="Lançamento bancário" description="Registre entradas e saídas da conta corrente." />
            <form onSubmit={handleBankSubmit} className="grid grid-cols-1 gap-4 p-5 md:grid-cols-6">
              <Field label="Tipo">
                <select value={transForm.type} onChange={(event) => setTransForm({ ...transForm, type: event.target.value })} className="app-select">
                  <option value="EXPENSE">Saída bancária</option>
                  <option value="INCOME">Entrada bancária</option>
                </select>
              </Field>
              <Field label="Valor">
                <input type="number" step="0.01" placeholder="0,00" value={transForm.amount} onChange={(event) => setTransForm({ ...transForm, amount: event.target.value })} className="app-input" required />
              </Field>
              <Field label="Data">
                <input type="date" value={transForm.date} onChange={(event) => setTransForm({ ...transForm, date: event.target.value })} className="app-input" required />
              </Field>
              <Field label="Categoria">
                <select value={transForm.category} onChange={(event) => setTransForm({ ...transForm, category: event.target.value })} className="app-select" required>
                  <option value="">Selecione...</option>
                  {CATEGORY_OPTIONS.map((category) => (
                    <option key={category} value={category}>{category}</option>
                  ))}
                </select>
              </Field>
              <Field label="Descrição" className="md:col-span-1">
                <input type="text" placeholder="Ex: Mercado" value={transForm.description} onChange={(event) => setTransForm({ ...transForm, description: event.target.value })} className="app-input" required />
              </Field>
              <div className="flex items-end">
                <Button type="submit" icon={Plus} loading={saving} className="w-full">Lançar</Button>
              </div>
            </form>
          </Panel>

          <Panel>
            <PanelHeader
              title="Extrato da conta"
              description="Últimas movimentações registradas."
              actions={<Badge>{transactions.length} registro(s)</Badge>}
            />
            {transactions.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="app-table min-w-[760px]">
                  <thead>
                    <tr>
                      <th>Data</th>
                      <th>Categoria</th>
                      <th>Descrição</th>
                      <th>Tipo</th>
                      <th>Valor</th>
                      <th className="text-right">Ação</th>
                    </tr>
                  </thead>
                  <tbody>
                    {transactions.map((transaction) => (
                      <tr key={transaction.id}>
                        <td className="text-zinc-600">{formatDateBR(transaction.date)}</td>
                        <td className="font-medium text-zinc-800">{transaction.category}</td>
                        <td className="text-zinc-700">{transaction.description}</td>
                        <td>
                          {transaction.type === 'INCOME' ? <Badge tone="success">Entrada</Badge> : <Badge tone="danger">Saída</Badge>}
                        </td>
                        <td className={cx('font-bold', transaction.type === 'INCOME' ? 'text-emerald-700' : 'text-zinc-950')}>
                          {transaction.type === 'INCOME' ? '+' : '-'} {formatCurrency(transaction.amount)}
                        </td>
                        <td className="text-right">
                          <IconButton label="Excluir transação" icon={Trash2} variant="danger" onClick={() => handleDeleteTransaction(transaction.id)} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-5">
                <EmptyState icon={Receipt} title="Nenhuma movimentação" message="Os lançamentos bancários aparecerão no extrato." />
              </div>
            )}
          </Panel>
        </div>
      ) : null}

      {activeTab === 'CARTOES' ? (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
            <Panel className="h-fit">
              <PanelHeader title="Cartões" description="Vencimento e fechamento de cada cartão." />

              <form onSubmit={handleCreateCard} className="space-y-4 p-5">
                <Field label="Nome do cartão">
                  <input type="text" placeholder="Ex: Nubank" value={cardForm.name} onChange={(event) => setCardForm({ ...cardForm, name: event.target.value })} className="app-input" required />
                </Field>

                <div className="grid grid-cols-2 gap-3">
                  <Field label="Vencimento">
                    <input type="number" min="1" max="31" placeholder="Dia" value={cardForm.due_day} onChange={handleDueDayChange} className="app-input" required />
                  </Field>
                  <Field label="Fechamento">
                    <input type="number" min="1" max="31" placeholder="Dia" value={cardForm.closing_day} onChange={(event) => setCardForm({ ...cardForm, closing_day: event.target.value })} className="app-input" required />
                  </Field>
                </div>

                <Button type="submit" variant="dark" icon={Plus} loading={saving} className="w-full">Salvar cartão</Button>
              </form>

              <div className="border-t border-zinc-100 p-5">
                {cards.length > 0 ? (
                  <div className="space-y-2">
                    {cards.map((card) => (
                      <div key={card.id} className="flex items-center justify-between gap-3 rounded-lg border border-zinc-200 px-3 py-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-bold text-zinc-800">{card.name}</p>
                          <p className="mt-0.5 text-xs text-zinc-500">Vence dia {card.due_day} • Fecha dia {card.closing_day}</p>
                        </div>
                        <IconButton label="Excluir cartão" icon={Trash2} variant="danger" onClick={() => handleDeleteCard(card.id, card.name)} />
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyState icon={CreditCard} title="Nenhum cartão" message="Cadastre um cartão para lançar compras no crédito." className="min-h-40" />
                )}
              </div>
            </Panel>

            <Panel className="xl:col-span-2">
              <PanelHeader title="Compra no crédito" description="Lançamento parcelado por cartão e categoria." />

              <div className="p-5">
                {cards.length === 0 ? (
                  <EmptyState icon={CreditCard} title="Cadastre um cartão primeiro" message="Depois disso, o formulário de compras fica disponível." />
                ) : (
                  <form onSubmit={handleCCExpenseSubmit} className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <Field label="Cartão">
                      <select value={expenseForm.card_id} onChange={(event) => setExpenseForm({ ...expenseForm, card_id: event.target.value })} className="app-select" required>
                        <option value="">Selecione...</option>
                        {cards.map((card) => <option key={card.id} value={card.id}>{card.name} (vence dia {card.due_day})</option>)}
                      </select>
                    </Field>
                    <Field label="Categoria">
                      <select value={expenseForm.category} onChange={(event) => setExpenseForm({ ...expenseForm, category: event.target.value })} className="app-select" required>
                        <option value="">Selecione...</option>
                        {CATEGORY_OPTIONS.filter((category) => category !== 'Receita').map((category) => (
                          <option key={category} value={category}>{category}</option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Descrição">
                      <input type="text" placeholder="O que você comprou?" value={expenseForm.description} onChange={(event) => setExpenseForm({ ...expenseForm, description: event.target.value })} className="app-input" required />
                    </Field>
                    <Field label="Valor total">
                      <input type="number" step="0.01" placeholder="0,00" value={expenseForm.total_amount} onChange={(event) => setExpenseForm({ ...expenseForm, total_amount: event.target.value })} className="app-input" required />
                    </Field>
                    <Field label="Data da compra">
                      <input type="date" value={expenseForm.purchase_date} onChange={(event) => setExpenseForm({ ...expenseForm, purchase_date: event.target.value })} className="app-input" required />
                    </Field>
                    <Field label="Parcelas">
                      <input type="number" min="1" max="48" value={expenseForm.installments} onChange={(event) => setExpenseForm({ ...expenseForm, installments: event.target.value })} className="app-input" required />
                    </Field>
                    <Button type="submit" icon={Plus} loading={saving} className="md:col-span-2">Registrar compra</Button>
                  </form>
                )}
              </div>
            </Panel>
          </div>

          {openInvoicesByCard.length > 0 ? (
            <div className="space-y-4">
              {openInvoicesByCard.map((cardGroup) => {
                const isExpanded = expandedCards.includes(cardGroup.cardId)

                return (
                  <Panel key={cardGroup.cardId} className="overflow-hidden">
                    <div className="flex flex-col gap-4 border-b border-zinc-100 px-5 py-4 md:flex-row md:items-center md:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="text-lg font-bold text-zinc-950">{cardGroup.cardName}</h3>
                          <Badge tone="info">{cardGroup.invoices.length} fatura(s)</Badge>
                        </div>
                        <p className="mt-1 text-sm text-zinc-500">Vence dia {cardGroup.dueDay} • Fecha dia {cardGroup.closingDay}</p>
                      </div>

                      <Button
                        type="button"
                        variant="secondary"
                        icon={isExpanded ? ChevronUp : ChevronDown}
                        onClick={() => toggleCardExpenses(cardGroup.cardId)}
                      >
                        {isExpanded ? 'Ocultar' : 'Ver gastos'}
                      </Button>
                    </div>

                    {isExpanded ? (
                      <div className="divide-y divide-zinc-100">
                        {cardGroup.invoices.map((invoice) => (
                          <div key={invoice.invoiceKey} className="space-y-4 p-5">
                            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                              <div>
                                <p className="text-lg font-bold text-zinc-950">Fatura {formatInvoiceLabel(invoice.invoiceMonth, invoice.invoiceYear)}</p>
                                <div className="mt-2">{getInvoiceStatus(invoice.invoiceYear, invoice.invoiceMonth, cardGroup.dueDay)}</div>
                              </div>

                              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                                <div className="sm:text-right">
                                  <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Total</p>
                                  <p className="text-xl font-bold text-rose-600">{formatCurrency(invoice.total)}</p>
                                </div>
                                <Button type="button" icon={CheckCircle} loading={saving} onClick={() => handlePayInvoice(invoice, cardGroup)}>
                                  Pagar
                                </Button>
                              </div>
                            </div>

                            <div className="space-y-2">
                              {invoice.purchases.map((purchase) => (
                                <div key={purchase.purchaseKey} className="flex flex-col gap-3 rounded-lg border border-zinc-200 px-4 py-3 md:flex-row md:items-center md:justify-between">
                                  <div className="min-w-0">
                                    <p className="font-semibold text-zinc-900">{purchase.description}</p>
                                    <div className="mt-2 flex flex-wrap gap-2">
                                      <Badge tone="info">{purchase.category}</Badge>
                                      <Badge>Compra em {formatDateBR(purchase.purchase_date)}</Badge>
                                      <Badge tone="warning">Parcela {purchase.installmentCurrent}/{purchase.installmentTotal}</Badge>
                                    </div>
                                  </div>

                                  <div className="flex items-center justify-between gap-4 md:justify-end">
                                    <p className="whitespace-nowrap font-bold text-zinc-950">{formatCurrency(purchase.amount)}</p>
                                    <IconButton label="Excluir compra parcelada" icon={Trash2} variant="danger" onClick={() => handleDeleteCCPurchase(purchase)} />
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </Panel>
                )
              })}
            </div>
          ) : (
            <Panel className="p-5">
              <EmptyState icon={CreditCard} title="Nenhuma fatura aberta" message="As compras no crédito aparecerão agrupadas por cartão." />
            </Panel>
          )}
        </div>
      ) : null}
    </div>
  )
}
