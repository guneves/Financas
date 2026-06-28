import { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import {
  AlertTriangle,
  CalendarDays,
  CheckCircle2,
  CreditCard,
  Landmark,
  ListChecks,
  PiggyBank,
  Receipt,
  Wallet,
} from 'lucide-react'
import { apiFetch } from '../lib/api'
import { ccExpensesApi, transactionsApi } from '../lib/dataApi'
import { EMPTY_PORTFOLIO } from '../lib/portfolio'
import { Badge, Button, EmptyState, MetricCard, PageHeader, Panel, PanelHeader, cx } from '../components/ui'

const CATEGORIES = ['Alimentação', 'Moradia', 'Transporte', 'Saúde', 'Educação', 'Lazer', 'Serviços', 'Outros']
const PAYMENT_METHOD_COLORS = {
  cash: '#18181b',
  credit: '#0284c7',
}

const formatCurrency = (value) => new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
}).format(Number(value || 0))

const getDaysRemainingInMonth = () => {
  const today = new Date()
  const lastDay = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate()
  return Math.max(lastDay - today.getDate() + 1, 1)
}

const getLocalDateString = (date = new Date()) => {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const parseInstallmentInfo = (value) => {
  if (!value || typeof value !== 'string' || !value.includes('/')) {
    return { current: 1, total: 1 }
  }

  const [current, total] = value.split('/').map(Number)
  return {
    current: Number.isFinite(current) ? current : 1,
    total: Number.isFinite(total) ? total : 1,
  }
}

const getPurchaseGroupKey = (expense) => {
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

export default function Dashboard() {
  const [portfolio, setPortfolio] = useState(null)
  const [portfolioError, setPortfolioError] = useState('')
  const [dataError, setDataError] = useState('')
  const [bankBalance, setBankBalance] = useState(0)
  const [currentMonthInvoice, setCurrentMonthInvoice] = useState(0)
  const [currentMonthInvoiceItems, setCurrentMonthInvoiceItems] = useState([])
  const [expensesByCategory, setExpensesByCategory] = useState([])
  const [installmentExpenses, setInstallmentExpenses] = useState([])
  const [isPayingCurrentInvoice, setIsPayingCurrentInvoice] = useState(false)

  useEffect(() => {
    fetchAllData()
  }, [])

  const fetchAllData = async () => {
    setDataError('')

    try {
      setPortfolioError('')
      const data = await apiFetch('/api/investments/portfolio')
      setPortfolio(data)
    } catch (error) {
      console.warn('Erro ao buscar portfólio:', error)
      setPortfolioError(error.message || 'Não foi possível carregar a carteira.')
      setPortfolio(EMPTY_PORTFOLIO)
    }

    const today = new Date()
    const currentMonth = today.getMonth() + 1
    const currentYear = today.getFullYear()

    let nextMonth = currentMonth + 1
    let nextYear = currentYear
    if (nextMonth > 12) {
      nextMonth = 1
      nextYear += 1
    }

    let transData = []
    let ccData = []

    try {
      const [transactions, creditExpenses] = await Promise.all([
        transactionsApi.list(),
        ccExpensesApi.list({ status: 'OPEN' }),
      ])
      transData = transactions || []
      ccData = creditExpenses || []
    } catch (error) {
      console.warn('Erro ao buscar movimentações:', error)
      setDataError(error.message || 'Não foi possível carregar movimentações e faturas.')
      setExpensesByCategory([])
      setCurrentMonthInvoiceItems([])
      setCurrentMonthInvoice(0)
      setInstallmentExpenses([])
      return
    }

    const categoryTotals = {}
    CATEGORIES.forEach((category) => {
      categoryTotals[category] = { cash: 0, credit: 0 }
    })

    const calculatedBalance = transData.reduce((acc, curr) => {
      return curr.type === 'INCOME'
        ? acc + parseFloat(curr.amount)
        : acc - parseFloat(curr.amount)
    }, 0)
    setBankBalance(calculatedBalance)

    const currentMonthCashExpenses = transData.filter((transaction) => {
      if (transaction.type !== 'EXPENSE') return false
      if (transaction.category?.startsWith('Pagamento Fatura ')) return false

      const [year, month] = transaction.date.split('-')
      return parseInt(month) === currentMonth && parseInt(year) === currentYear
    })

    currentMonthCashExpenses.forEach((transaction) => {
      const category = CATEGORIES.includes(transaction.category) ? transaction.category : 'Outros'
      categoryTotals[category].cash += parseFloat(transaction.amount)
    })

    const currentMonthPurchases = ccData
      .filter((expense) => {
        if (!expense.purchase_date) return false
        const [year, month] = expense.purchase_date.split('-')
        return parseInt(month) === currentMonth && parseInt(year) === currentYear
      })
      .reduce((acc, expense) => {
        const key = getPurchaseGroupKey(expense)
        if (!acc[key]) {
          acc[key] = {
            category: CATEGORIES.includes(expense.category) ? expense.category : 'Outros',
            totalPurchaseAmount: 0,
          }
        }
        acc[key].totalPurchaseAmount += parseFloat(expense.amount)
        return acc
      }, {})

    Object.values(currentMonthPurchases).forEach((purchase) => {
      categoryTotals[purchase.category].credit += purchase.totalPurchaseAmount
    })

    const currentMonthItems = ccData.filter((expense) => expense.invoice_month === nextMonth && expense.invoice_year === nextYear)
    const currentMonthTotal = currentMonthItems.reduce((acc, curr) => acc + parseFloat(curr.amount), 0)

    const openInstallments = ccData
      .map((expense) => {
        const installment = parseInstallmentInfo(expense.installment_info)
        return {
          ...expense,
          installmentCurrent: installment.current,
          installmentTotal: installment.total,
        }
      })
      .filter((expense) => expense.installmentTotal > 1)

    setCurrentMonthInvoiceItems(currentMonthItems)
    setCurrentMonthInvoice(currentMonthTotal)
    setInstallmentExpenses(openInstallments)

    const chartDataExpenses = Object.keys(categoryTotals)
      .map((category) => ({
        name: category,
        cash: Number(categoryTotals[category].cash.toFixed(2)),
        credit: Number(categoryTotals[category].credit.toFixed(2)),
        value: Number((categoryTotals[category].cash + categoryTotals[category].credit).toFixed(2)),
      }))
      .filter((item) => item.value > 0)
      .sort((a, b) => b.value - a.value)

    setExpensesByCategory(chartDataExpenses)
  }

  const handlePayCurrentMonthInvoice = async () => {
    if (currentMonthInvoiceItems.length === 0 || currentMonthInvoice <= 0) return

    const confirmed = window.confirm(`Deseja pagar a fatura total deste mês no valor de ${formatCurrency(currentMonthInvoice)}?`)
    if (!confirmed) return

    setIsPayingCurrentInvoice(true)

    try {
      await transactionsApi.create({
        type: 'EXPENSE',
        amount: Number(currentMonthInvoice.toFixed(2)),
        date: getLocalDateString(),
        category: 'Pagamento Fatura do Mês',
        description: 'Baixa da fatura total do mês pela dashboard',
      })

      const idsToUpdate = currentMonthInvoiceItems.map((item) => item.id)

      if (idsToUpdate.length > 0) {
        await ccExpensesApi.updateStatus(idsToUpdate, 'PAID')
      }

      await fetchAllData()
    } catch (error) {
      console.error('Erro ao pagar a fatura do mês:', error)
      alert('Não foi possível pagar a fatura do mês.')
    } finally {
      setIsPayingCurrentInvoice(false)
    }
  }

  const totalWealth = (bankBalance || 0) + (portfolio?.current_balance || 0)
  const daysRemainingInMonth = getDaysRemainingInMonth()
  const dailyAvailable = (bankBalance - currentMonthInvoice) / daysRemainingInMonth

  const expenseTotals = useMemo(() => {
    return expensesByCategory.reduce((acc, item) => {
      acc.cash += item.cash
      acc.credit += item.credit
      acc.total += item.value
      return acc
    }, { cash: 0, credit: 0, total: 0 })
  }, [expensesByCategory])

  const groupedInstallmentExpenses = useMemo(() => {
    const grouped = installmentExpenses.reduce((acc, item) => {
      const key = [
        item.card_id || 'sem-cartao',
        item.description || 'sem-descricao',
        item.purchase_date || 'sem-data',
        item.category || 'sem-categoria',
      ].join('|')

      if (!acc[key]) {
        acc[key] = {
          key,
          description: item.description,
          cardName: item.credit_cards?.name || 'Cartão',
          purchaseDate: item.purchase_date,
          category: item.category || 'Outros',
          installmentAmount: parseFloat(item.amount),
          remainingInstallments: 0,
          totalInstallments: item.installmentTotal,
          nextInvoiceMonth: item.invoice_month,
          nextInvoiceYear: item.invoice_year,
        }
      }

      acc[key].remainingInstallments += 1

      if (
        item.invoice_year < acc[key].nextInvoiceYear ||
        (item.invoice_year === acc[key].nextInvoiceYear && item.invoice_month < acc[key].nextInvoiceMonth)
      ) {
        acc[key].nextInvoiceMonth = item.invoice_month
        acc[key].nextInvoiceYear = item.invoice_year
      }

      return acc
    }, {})

    return Object.values(grouped).sort((a, b) => {
      if (a.nextInvoiceYear !== b.nextInvoiceYear) return a.nextInvoiceYear - b.nextInvoiceYear
      if (a.nextInvoiceMonth !== b.nextInvoiceMonth) return a.nextInvoiceMonth - b.nextInvoiceMonth
      return a.description.localeCompare(b.description)
    })
  }, [installmentExpenses])

  const installmentSummary = useMemo(() => {
    return groupedInstallmentExpenses.reduce((acc, item) => {
      acc.total += item.installmentAmount * item.remainingInstallments
      return acc
    }, { total: 0 })
  }, [groupedInstallmentExpenses])

  if (!portfolio) {
    return (
      <Panel className="p-6">
        <div className="h-28 animate-pulse rounded-lg bg-zinc-100" />
      </Panel>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Painel"
        title="Visão geral"
        description="Patrimônio, saldo disponível, despesas do mês e compromissos em aberto."
      />

      {portfolioError ? (
        <AlertMessage tone="warning" message={`Não foi possível carregar os investimentos agora. Detalhe: ${portfolioError}`} />
      ) : null}

      {dataError ? (
        <AlertMessage tone="danger" message={`Movimentações indisponíveis no momento. Detalhe: ${dataError}`} />
      ) : null}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={Landmark}
          tone="dark"
          title="Patrimônio total"
          value={formatCurrency(totalWealth)}
          subtitle="Conta corrente + investimentos"
        />
        <MetricCard
          icon={Wallet}
          tone={bankBalance >= 0 ? 'success' : 'danger'}
          title="Saldo em conta"
          value={formatCurrency(bankBalance)}
          valueClassName={bankBalance >= 0 ? 'text-zinc-950' : 'text-rose-600'}
          subtitle="Saldo real calculado"
        />
        <MetricCard
          icon={PiggyBank}
          tone="info"
          title="Investimentos"
          value={formatCurrency(portfolio.current_balance)}
          valueClassName="text-sky-700"
          subtitle="Valor atual da carteira"
        />
        <MetricCard
          icon={CalendarDays}
          tone={dailyAvailable >= 0 ? 'success' : 'danger'}
          title="Disponível por dia"
          value={formatCurrency(dailyAvailable)}
          valueClassName={dailyAvailable >= 0 ? 'text-emerald-700' : 'text-rose-600'}
          subtitle={`${daysRemainingInMonth} dia(s) restantes no mês`}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
        <Panel className="xl:col-span-3">
          <PanelHeader
            title="Despesas por categoria"
            description="Comparativo entre conta corrente e cartão no mês atual."
            actions={(
              <div className="text-right">
                <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Total</p>
                <p className="text-lg font-bold text-zinc-950">{formatCurrency(expenseTotals.total)}</p>
              </div>
            )}
          />

          <div className="p-5">
            {expensesByCategory.length > 0 ? (
              <div className="space-y-6">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <InlineStat label="Conta corrente" value={formatCurrency(expenseTotals.cash)} tone="neutral" />
                  <InlineStat label="Cartão de crédito" value={formatCurrency(expenseTotals.credit)} tone="info" />
                </div>

                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={expensesByCategory} layout="vertical" margin={{ top: 8, right: 18, left: 8, bottom: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e4e4e7" />
                      <XAxis type="number" tickFormatter={(value) => `${Math.round(value)}`} tick={{ fill: '#71717a', fontSize: 12 }} />
                      <YAxis dataKey="name" type="category" width={96} tick={{ fill: '#52525b', fontSize: 12 }} />
                      <Tooltip
                        formatter={(value, name) => [formatCurrency(value), name === 'cash' ? 'Conta corrente' : 'Cartão']}
                        labelFormatter={(label) => `Categoria: ${label}`}
                        contentStyle={{ borderRadius: 8, borderColor: '#d4d4d8' }}
                      />
                      <Legend formatter={(value) => value === 'cash' ? 'Conta corrente' : 'Cartão'} />
                      <Bar dataKey="cash" stackId="expenses" fill={PAYMENT_METHOD_COLORS.cash} radius={[4, 0, 0, 4]} />
                      <Bar dataKey="credit" stackId="expenses" fill={PAYMENT_METHOD_COLORS.credit} radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                <div className="space-y-3">
                  {expensesByCategory.map((item) => {
                    const percentage = expenseTotals.total > 0 ? (item.value / expenseTotals.total) * 100 : 0
                    return (
                      <div key={item.name} className="rounded-lg border border-zinc-200 p-4">
                        <div className="flex items-start justify-between gap-4">
                          <div className="min-w-0">
                            <p className="font-semibold text-zinc-900">{item.name}</p>
                            <div className="mt-2 flex flex-wrap gap-2">
                              {item.cash > 0 ? <Badge>Conta: {formatCurrency(item.cash)}</Badge> : null}
                              {item.credit > 0 ? <Badge tone="info">Cartão: {formatCurrency(item.credit)}</Badge> : null}
                            </div>
                          </div>
                          <p className="whitespace-nowrap text-base font-bold text-zinc-950">{formatCurrency(item.value)}</p>
                        </div>
                        <div className="mt-3 h-2 overflow-hidden rounded-full bg-zinc-100">
                          <div className="h-full rounded-full bg-emerald-500" style={{ width: `${Math.min(percentage, 100)}%` }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            ) : (
              <EmptyState
                icon={Receipt}
                title="Nenhuma despesa no mês"
                message="As categorias aparecem assim que houver movimentações ou compras abertas."
              />
            )}
          </div>
        </Panel>

        <div className="space-y-6 xl:col-span-2">
          <Panel>
            <PanelHeader
              title="Parcelamentos abertos"
              description="Compras agrupadas por cartão e compra original."
              actions={<Badge tone="warning">{formatCurrency(installmentSummary.total)}</Badge>}
            />

            <div className="p-5">
              {groupedInstallmentExpenses.length > 0 ? (
                <div className="max-h-[520px] space-y-3 overflow-y-auto pr-1">
                  {groupedInstallmentExpenses.map((expense) => (
                    <div key={expense.key} className="rounded-lg border border-zinc-200 p-4">
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <p className="truncate font-semibold text-zinc-900">{expense.description}</p>
                          <div className="mt-2 flex flex-wrap gap-2">
                            <Badge tone="info">{expense.cardName}</Badge>
                            <Badge>{expense.remainingInstallments}x de {formatCurrency(expense.installmentAmount)}</Badge>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="whitespace-nowrap font-bold text-zinc-950">
                            {formatCurrency(expense.installmentAmount * expense.remainingInstallments)}
                          </p>
                          <p className="mt-1 text-xs font-medium uppercase tracking-wide text-zinc-400">Restante</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState
                  icon={ListChecks}
                  title="Sem parcelamentos"
                  message="Compras parceladas abertas aparecerão neste painel."
                />
              )}
            </div>
          </Panel>

          <Panel>
            <PanelHeader
              title="Próxima fatura"
              description="Total aberto com vencimento no próximo ciclo."
              actions={(
                <p className={cx('text-xl font-bold', currentMonthInvoice > 0 ? 'text-rose-600' : 'text-emerald-700')}>
                  {formatCurrency(currentMonthInvoice)}
                </p>
              )}
            />

            <div className="p-5">
              {currentMonthInvoice > 0 ? (
                <div className="space-y-4">
                  <div className="flex items-start gap-3 rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                    <CreditCard className="mt-0.5 h-4 w-4 shrink-0" />
                    <div>
                      <p className="font-semibold">{currentMonthInvoiceItems.length} lançamento(s) em aberto</p>
                      <p className="mt-1 text-rose-600">O pagamento cria uma saída bancária e baixa os itens da fatura.</p>
                    </div>
                  </div>

                  <div className="max-h-52 space-y-2 overflow-y-auto pr-1">
                    {currentMonthInvoiceItems.map((item) => (
                      <div key={item.id} className="flex items-center justify-between gap-3 rounded-lg border border-zinc-200 px-3 py-2.5">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-zinc-900">{item.description}</p>
                          <p className="mt-0.5 text-xs text-zinc-500">
                            {item.credit_cards?.name || 'Cartão'}
                            {item.installment_info && item.installment_info !== '1/1' ? ` • ${item.installment_info}` : ''}
                          </p>
                        </div>
                        <span className="whitespace-nowrap text-sm font-bold text-zinc-950">
                          {formatCurrency(item.amount)}
                        </span>
                      </div>
                    ))}
                  </div>

                  <Button
                    type="button"
                    onClick={handlePayCurrentMonthInvoice}
                    loading={isPayingCurrentInvoice}
                    icon={CheckCircle2}
                    className="w-full"
                  >
                    Pagar fatura
                  </Button>
                </div>
              ) : (
                <EmptyState
                  icon={CheckCircle2}
                  title="Nenhuma fatura aberta"
                  message="Não há lançamentos previstos para o próximo ciclo."
                  className="min-h-40"
                />
              )}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  )
}

function AlertMessage({ tone, message }) {
  const classes = tone === 'danger'
    ? 'border-rose-200 bg-rose-50 text-rose-700'
    : 'border-amber-200 bg-amber-50 text-amber-800'

  return (
    <div className={cx('flex items-start gap-3 rounded-lg border px-4 py-3 text-sm font-medium', classes)}>
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{message}</span>
    </div>
  )
}

function InlineStat({ label, value, tone }) {
  const toneClass = tone === 'info' ? 'text-sky-700' : 'text-zinc-950'

  return (
    <div className="rounded-lg border border-zinc-200 px-4 py-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{label}</p>
      <p className={cx('mt-1 text-xl font-bold', toneClass)}>{value}</p>
    </div>
  )
}
