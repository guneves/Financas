import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  BellRing,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  CreditCard,
  Landmark,
  LineChart as LineChartIcon,
  ListChecks,
  PiggyBank,
  Plus,
  Receipt,
  Repeat,
  Wallet,
} from 'lucide-react'
import { apiFetch } from '../lib/api'
import { accountsApi, ccExpensesApi, recurringApi, transactionsApi } from '../lib/dataApi'
import { useDataVersion, useNewEntry } from '../lib/newEntry'
import { EMPTY_PORTFOLIO } from '../lib/portfolio'
import {
  AlertMessage,
  Badge,
  Button,
  DeltaBadge,
  EmptyState,
  MetricCard,
  PageHeader,
  Panel,
  PanelHeader,
  Skeleton,
  cx,
} from '../components/ui'
import {
  ANIMATION,
  CHART,
  ChartTooltip,
  DonutChart,
  FLOW,
  LegendDot,
  SERIES,
  Sparkline,
  axisProps,
  compactCurrency,
} from '../components/charts'
import { formatCurrency, getLocalDateString, monthKey, monthLabel, shiftMonth } from '../lib/format'

const ACCOUNT_TYPE_LABELS = {
  CHECKING: 'Conta corrente',
  SAVINGS: 'Poupança',
  BROKERAGE: 'Corretora',
  CASH: 'Dinheiro',
  OTHER: 'Outra',
}

const HISTORY_MONTHS = 12
const INVOICE_MONTHS = 6

const getDaysRemainingInMonth = () => {
  const today = new Date()
  const lastDay = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate()
  return Math.max(lastDay - today.getDate() + 1, 1)
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

// 'AAAA-MM' -> 'set/26'
const shortMonth = (key) => {
  const [year, month] = String(key).split('-').map(Number)
  const name = new Date(year, month - 1, 1).toLocaleDateString('pt-BR', { month: 'short' }).replace('.', '')
  return `${name}/${String(year).slice(2)}`
}

const isInvoicePayment = (transaction) => transaction.category?.startsWith('Pagamento Fatura')

const percentChange = (current, previous) => {
  if (!previous) return null
  return ((current - previous) / Math.abs(previous)) * 100
}

// Gasto de consumo de um mes, por dia e por categoria: saidas da conta (menos
// o pagamento de fatura, que ja e a soma das compras) + compras no cartao pelo
// valor total da compra, na data da compra.
function buildSpending(transactions, ccExpenses, key) {
  const byDay = {}
  const byCategory = {}
  const add = (day, category, channel, amount) => {
    byDay[day] = (byDay[day] || 0) + amount
    const name = category || 'Outros'
    if (!byCategory[name]) byCategory[name] = { cash: 0, credit: 0 }
    byCategory[name][channel] += amount
  }

  transactions.forEach((transaction) => {
    if (transaction.type !== 'EXPENSE' || isInvoicePayment(transaction)) return
    if (String(transaction.date).slice(0, 7) !== key) return
    add(Number(transaction.date.slice(8, 10)), transaction.category, 'cash', parseFloat(transaction.amount) || 0)
  })

  const purchases = {}
  ccExpenses.forEach((expense) => {
    if (String(expense.purchase_date || '').slice(0, 7) !== key) return
    const groupKey = getPurchaseGroupKey(expense)
    if (!purchases[groupKey]) {
      purchases[groupKey] = { day: Number(expense.purchase_date.slice(8, 10)), category: expense.category, amount: 0 }
    }
    purchases[groupKey].amount += parseFloat(expense.amount) || 0
  })
  Object.values(purchases).forEach((purchase) => add(purchase.day, purchase.category, 'credit', purchase.amount))

  const total = Object.values(byDay).reduce((acc, value) => acc + value, 0)
  return { byDay, byCategory, total }
}

export default function Dashboard() {
  const [portfolio, setPortfolio] = useState(null)
  const [portfolioError, setPortfolioError] = useState('')
  const [dataError, setDataError] = useState('')
  const [transactions, setTransactions] = useState([])
  const [ccExpenses, setCcExpenses] = useState([])
  const [accounts, setAccounts] = useState([])
  const [isPayingCurrentInvoice, setIsPayingCurrentInvoice] = useState(false)
  const [recurringItems, setRecurringItems] = useState([])
  const [isRunningRecurring, setIsRunningRecurring] = useState(false)
  const [notice, setNotice] = useState('')
  const { openNewEntry } = useNewEntry()
  // Recarrega depois de um "+ Novo" salvo no Layout.
  const dataVersion = useDataVersion()

  useEffect(() => {
    fetchAllData()
  }, [dataVersion])

  const fetchAllData = async () => {
    setDataError('')

    try {
      setPortfolioError('')
      const data = await apiFetch('/api/investments/portfolio?refresh_prices=false')
      setPortfolio(data)
    } catch (error) {
      console.warn('Erro ao buscar portfólio:', error)
      setPortfolioError(error.message || 'Não foi possível carregar a carteira.')
      setPortfolio(EMPTY_PORTFOLIO)
    }

    try {
      // Todas as compras do cartao, nao so as abertas: o ritmo de gastos do mes
      // passado precisa das compras que ja foram pagas.
      const [transactionData, creditExpenses, accountData] = await Promise.all([
        transactionsApi.list(),
        ccExpensesApi.list(),
        accountsApi.list(),
      ])
      setTransactions(transactionData || [])
      setCcExpenses(creditExpenses || [])
      setAccounts(accountData || [])
    } catch (error) {
      console.warn('Erro ao buscar movimentações:', error)
      setDataError(error.message || 'Não foi possível carregar movimentações e faturas.')
      setTransactions([])
      setCcExpenses([])
    }

    // Recorrencias vencidas para o "Precisa de voce". Falhar aqui so esconde o
    // aviso: nao deve derrubar o resto do painel.
    try {
      const recurringData = await recurringApi.list()
      setRecurringItems(recurringData?.items || [])
    } catch (error) {
      console.warn('Erro ao buscar recorrências:', error)
      setRecurringItems([])
    }
  }

  // Mesma conta da tela Recorrentes: soma do pending_count de cada recorrencia.
  const pendingRecurringCount = useMemo(
    () => recurringItems.reduce((total, item) => total + Number(item.pending_count || 0), 0),
    [recurringItems]
  )

  // Mesma chamada do botao "Lancar pendentes" de Recorrentes (idempotente).
  const handleRunRecurring = async () => {
    setIsRunningRecurring(true)
    setDataError('')
    setNotice('')
    try {
      const result = await recurringApi.run()
      setNotice(
        result?.created
          ? `${result.created} lançamento(s) recorrente(s) gerado(s).`
          : 'Nada pendente: todos os lançamentos recorrentes já estão em dia.'
      )
      await fetchAllData()
    } catch (error) {
      console.warn('Erro ao lançar recorrências:', error)
      setDataError(error.message || 'Não foi possível gerar os lançamentos recorrentes.')
    } finally {
      setIsRunningRecurring(false)
    }
  }

  const today = new Date()
  const currentKey = monthKey(today)
  const previousKey = shiftMonth(currentKey, -1)
  const nextKey = shiftMonth(currentKey, 1)

  const openCcExpenses = useMemo(() => ccExpenses.filter((expense) => expense.status === 'OPEN'), [ccExpenses])

  // TRANSFER nao entra: ela so move dinheiro entre contas proprias, o
  // consolidado nao muda. O saldo de cada conta vem de /api/accounts.
  const bankBalance = useMemo(() => transactions.reduce((acc, curr) => {
    if (curr.type === 'TRANSFER') return acc
    return curr.type === 'INCOME' ? acc + parseFloat(curr.amount) : acc - parseFloat(curr.amount)
  }, 0), [transactions])

  // Entradas, saidas e saldo de fim de mes dos ultimos 12 meses.
  const monthlyHistory = useMemo(() => {
    const keys = Array.from({ length: HISTORY_MONTHS }, (_, index) => shiftMonth(currentKey, index - (HISTORY_MONTHS - 1)))
    const firstKey = keys[0]
    const byKey = Object.fromEntries(keys.map((key) => [key, { income: 0, expense: 0 }]))
    let openingBalance = 0

    transactions.forEach((transaction) => {
      if (transaction.type === 'TRANSFER') return
      const amount = parseFloat(transaction.amount) || 0
      const signed = transaction.type === 'INCOME' ? amount : -amount
      const key = String(transaction.date).slice(0, 7)
      if (key < firstKey) {
        openingBalance += signed
        return
      }
      if (!byKey[key]) return
      if (transaction.type === 'INCOME') byKey[key].income += amount
      else byKey[key].expense += amount
    })

    let running = openingBalance
    return keys.map((key) => {
      const { income, expense } = byKey[key]
      running += income - expense
      return {
        key,
        label: shortMonth(key),
        income: Number(income.toFixed(2)),
        // Desenhada abaixo do zero: a posicao diz "saida" sem depender da cor.
        expense: -Number(expense.toFixed(2)),
        net: Number((income - expense).toFixed(2)),
        balance: Number(running.toFixed(2)),
      }
    })
  }, [transactions, currentKey])

  const flowSummary = useMemo(() => {
    const active = monthlyHistory.filter((item) => item.income !== 0 || item.expense !== 0)
    const income = monthlyHistory.reduce((acc, item) => acc + item.income, 0)
    const expense = monthlyHistory.reduce((acc, item) => acc - item.expense, 0)
    const months = Math.max(active.length, 1)
    return {
      avgIncome: income / months,
      avgExpense: expense / months,
      savingsRate: income > 0 ? ((income - expense) / income) * 100 : null,
      hasData: active.length > 0,
    }
  }, [monthlyHistory])

  const currentSpending = useMemo(() => buildSpending(transactions, ccExpenses, currentKey), [transactions, ccExpenses, currentKey])
  const previousSpending = useMemo(() => buildSpending(transactions, ccExpenses, previousKey), [transactions, ccExpenses, previousKey])

  // Acumulado dia a dia: este mes (ate hoje) contra o mes passado inteiro.
  const spendingPace = useMemo(() => {
    const daysInCurrent = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate()
    const daysInPrevious = new Date(today.getFullYear(), today.getMonth(), 0).getDate()
    const todayDay = today.getDate()
    let current = 0
    let previous = 0
    const rows = []
    for (let day = 1; day <= Math.max(daysInCurrent, daysInPrevious); day += 1) {
      current += currentSpending.byDay[day] || 0
      previous += previousSpending.byDay[day] || 0
      rows.push({
        day,
        current: day <= todayDay ? Number(current.toFixed(2)) : null,
        previous: day <= daysInPrevious ? Number(previous.toFixed(2)) : null,
      })
    }
    const previousAtSameDay = rows[Math.min(todayDay, daysInPrevious) - 1]?.previous || 0
    return { rows, todayDay, previousAtSameDay }
  }, [currentSpending, previousSpending])

  const categoryBreakdown = useMemo(() => {
    return Object.entries(currentSpending.byCategory)
      .map(([name, totals]) => {
        const value = totals.cash + totals.credit
        const previous = previousSpending.byCategory[name]
        const previousValue = previous ? previous.cash + previous.credit : 0
        return {
          name,
          value: Number(value.toFixed(2)),
          cash: totals.cash,
          credit: totals.credit,
          delta: percentChange(value, previousValue),
        }
      })
      .filter((item) => item.value > 0)
  }, [currentSpending, previousSpending])

  const nextInvoiceItems = useMemo(() => openCcExpenses.filter((expense) => {
    const [year, month] = nextKey.split('-').map(Number)
    return expense.invoice_month === month && expense.invoice_year === year
  }), [openCcExpenses, nextKey])

  const currentMonthInvoice = useMemo(
    () => nextInvoiceItems.reduce((acc, curr) => acc + parseFloat(curr.amount), 0),
    [nextInvoiceItems]
  )

  // Quanto ja esta comprometido nas proximas faturas, por mes de fatura.
  const invoiceProjection = useMemo(() => {
    const keys = Array.from({ length: INVOICE_MONTHS }, (_, index) => shiftMonth(nextKey, index))
    const byKey = Object.fromEntries(keys.map((key) => [key, 0]))
    openCcExpenses.forEach((expense) => {
      const key = `${expense.invoice_year}-${String(expense.invoice_month).padStart(2, '0')}`
      if (key in byKey) byKey[key] += parseFloat(expense.amount) || 0
    })
    return keys.map((key) => ({ key, label: shortMonth(key), value: Number(byKey[key].toFixed(2)) }))
  }, [openCcExpenses, nextKey])

  const groupedInstallmentExpenses = useMemo(() => {
    const grouped = openCcExpenses.reduce((acc, expense) => {
      const installment = parseInstallmentInfo(expense.installment_info)
      if (installment.total <= 1) return acc

      const key = [
        expense.card_id || 'sem-cartao',
        expense.description || 'sem-descricao',
        expense.purchase_date || 'sem-data',
        expense.category || 'sem-categoria',
      ].join('|')

      if (!acc[key]) {
        acc[key] = {
          key,
          description: expense.description,
          cardName: expense.card_name || expense.credit_cards?.name || 'Cartão',
          installmentAmount: parseFloat(expense.amount),
          remainingInstallments: 0,
          totalInstallments: installment.total,
          nextInvoiceMonth: expense.invoice_month,
          nextInvoiceYear: expense.invoice_year,
        }
      }

      acc[key].remainingInstallments += 1

      if (
        expense.invoice_year < acc[key].nextInvoiceYear ||
        (expense.invoice_year === acc[key].nextInvoiceYear && expense.invoice_month < acc[key].nextInvoiceMonth)
      ) {
        acc[key].nextInvoiceMonth = expense.invoice_month
        acc[key].nextInvoiceYear = expense.invoice_year
      }

      return acc
    }, {})

    return Object.values(grouped).sort((a, b) => {
      if (a.nextInvoiceYear !== b.nextInvoiceYear) return a.nextInvoiceYear - b.nextInvoiceYear
      if (a.nextInvoiceMonth !== b.nextInvoiceMonth) return a.nextInvoiceMonth - b.nextInvoiceMonth
      return String(a.description).localeCompare(String(b.description))
    })
  }, [openCcExpenses])

  const installmentTotal = groupedInstallmentExpenses.reduce(
    (acc, item) => acc + item.installmentAmount * item.remainingInstallments,
    0
  )

  const handlePayCurrentMonthInvoice = async () => {
    if (nextInvoiceItems.length === 0 || currentMonthInvoice <= 0) return

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

      const idsToUpdate = nextInvoiceItems.map((item) => item.id)

      if (idsToUpdate.length > 0) {
        await ccExpensesApi.updateStatus(idsToUpdate, 'PAID')
      }

      await fetchAllData()
    } catch (error) {
      console.warn('Erro ao pagar a fatura do mês:', error)
      setDataError(error.message || 'Não foi possível pagar a fatura do mês.')
    } finally {
      setIsPayingCurrentInvoice(false)
    }
  }

  if (!portfolio) {
    return <DashboardSkeleton />
  }

  const investmentsNetBalance = portfolio?.current_net_balance ?? portfolio?.current_balance ?? 0
  const totalWealth = (bankBalance || 0) + investmentsNetBalance
  const daysRemainingInMonth = getDaysRemainingInMonth()
  const dailyAvailable = (bankBalance - currentMonthInvoice) / daysRemainingInMonth
  const previousMonthBalance = monthlyHistory[monthlyHistory.length - 2]?.balance
  const spendingVsLastMonth = percentChange(currentSpending.total, spendingPace.previousAtSameDay)
  const maxAccountBalance = Math.max(...accounts.map((account) => Math.abs(Number(account.balance) || 0)), 1)

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Painel"
        title="Início"
        description="Patrimônio, saldo disponível, despesas do mês e compromissos em aberto."
        meta={<Badge tone="success">{monthLabel(currentKey)}</Badge>}
        actions={(
          <Button type="button" icon={Plus} onClick={() => openNewEntry()}>
            Novo
          </Button>
        )}
      />

      {portfolioError ? (
        <AlertMessage tone="warning" message={`Não foi possível carregar os investimentos agora. Detalhe: ${portfolioError}`} />
      ) : null}

      {dataError ? (
        <AlertMessage tone="danger" message={`Movimentações indisponíveis no momento. Detalhe: ${dataError}`} />
      ) : null}

      {notice ? <AlertMessage tone="success" message={notice} onDismiss={() => setNotice('')} /> : null}

      <NeedsAttention
        pendingRecurringCount={pendingRecurringCount}
        onRunRecurring={handleRunRecurring}
        isRunningRecurring={isRunningRecurring}
        invoiceAmount={currentMonthInvoice}
        invoiceItemCount={nextInvoiceItems.length}
        invoiceMonthLabel={monthLabel(nextKey)}
        onPayInvoice={handlePayCurrentMonthInvoice}
        isPayingInvoice={isPayingCurrentInvoice}
      />

      <div className="stagger grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={Landmark}
          tone="dark"
          title="Patrimônio total"
          amount={totalWealth}
          format={formatCurrency}
          subtitle="Conta corrente + investimentos"
          chart={<WealthSplit cash={bankBalance} investments={investmentsNetBalance} />}
        />
        <MetricCard
          icon={Wallet}
          tone={bankBalance >= 0 ? 'success' : 'danger'}
          title="Saldo em conta"
          amount={bankBalance}
          format={formatCurrency}
          valueClassName={bankBalance >= 0 ? 'text-zinc-950' : 'text-rose-600'}
          delta={<DeltaBadge value={percentChange(bankBalance, previousMonthBalance)} />}
          subtitle="vs. fim do mês passado"
          chart={<Sparkline data={monthlyHistory} dataKey="balance" color={SERIES[0]} />}
        />
        <MetricCard
          icon={PiggyBank}
          tone="info"
          title="Investimentos"
          amount={investmentsNetBalance}
          format={formatCurrency}
          valueClassName="text-sky-700"
          subtitle="Saldo líquido estimado"
        />
        <MetricCard
          icon={CalendarDays}
          tone={dailyAvailable >= 0 ? 'success' : 'danger'}
          title="Disponível por dia"
          amount={dailyAvailable}
          format={formatCurrency}
          valueClassName={dailyAvailable >= 0 ? 'text-emerald-700' : 'text-rose-600'}
          subtitle={`${daysRemainingInMonth} dia(s) restantes no mês`}
          footer={(
            <MonthProgress day={today.getDate()} daysLeft={daysRemainingInMonth} />
          )}
        />
      </div>

      <div className="stagger grid grid-cols-1 gap-6 xl:grid-cols-5">
        <Panel className="xl:col-span-3">
          <PanelHeader
            title={<PanelLink to="/lancamentos/extrato">Fluxo de caixa</PanelLink>}
            description="Entradas e saídas da conta nos últimos 12 meses. Transferências entre contas não entram."
            actions={(
              <div className="flex flex-wrap items-center gap-3">
                <LegendDot color={FLOW.income} label="Entradas" />
                <LegendDot color={FLOW.expense} label="Saídas" />
                <LegendDot color={FLOW.net} label="Resultado" shape="line" />
              </div>
            )}
          />
          <div className="p-5">
            {flowSummary.hasData ? (
              <>
                <div className="mb-4 grid grid-cols-3 gap-3">
                  <InlineStat label="Média de entradas" value={formatCurrency(flowSummary.avgIncome)} />
                  <InlineStat label="Média de saídas" value={formatCurrency(flowSummary.avgExpense)} />
                  <InlineStat
                    label="Taxa de poupança"
                    value={flowSummary.savingsRate === null ? '—' : `${flowSummary.savingsRate.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`}
                    valueClassName={flowSummary.savingsRate !== null && flowSummary.savingsRate < 0 ? 'text-rose-600' : 'text-emerald-700'}
                  />
                </div>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={monthlyHistory} stackOffset="sign" margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid vertical={false} stroke={CHART.grid} />
                      <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" />
                      <YAxis tickFormatter={compactCurrency} {...axisProps} width={76} />
                      <ReferenceLine y={0} stroke={CHART.axis} />
                      <Tooltip
                        cursor={{ fill: 'rgba(24,24,27,0.04)' }}
                        content={(
                          <ChartTooltip
                            absolute
                            names={{ income: 'Entradas', expense: 'Saídas', net: 'Resultado' }}
                            labelFormatter={(_, payload) => monthLabel(payload?.[0]?.payload?.key)}
                          />
                        )}
                      />
                      <Bar dataKey="income" stackId="flow" fill={FLOW.income} maxBarSize={24} radius={[4, 4, 0, 0]} {...ANIMATION} />
                      <Bar dataKey="expense" stackId="flow" fill={FLOW.expense} maxBarSize={24} radius={[4, 4, 0, 0]} {...ANIMATION} />
                      <Line
                        type="monotone"
                        dataKey="net"
                        stroke={FLOW.net}
                        strokeWidth={2}
                        dot={{ r: 3, fill: FLOW.net, strokeWidth: 2, stroke: '#fff' }}
                        activeDot={{ r: 5, strokeWidth: 2, stroke: '#fff' }}
                        {...ANIMATION}
                        animationBegin={300}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </>
            ) : (
              <EmptyState icon={Receipt} title="Sem movimentações" message="O fluxo aparece assim que houver entradas ou saídas lançadas." />
            )}
          </div>
        </Panel>

        <Panel className="xl:col-span-2">
          <PanelHeader
            title="Evolução do saldo"
            description="Saldo consolidado no fim de cada mês."
            actions={<Badge tone={bankBalance >= 0 ? 'success' : 'danger'}>{formatCurrency(bankBalance)}</Badge>}
          />
          <div className="p-5">
            {flowSummary.hasData ? (
              <div className="h-[22rem]">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={monthlyHistory} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="balanceFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={SERIES[0]} stopOpacity={0.2} />
                        <stop offset="100%" stopColor={SERIES[0]} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid vertical={false} stroke={CHART.grid} />
                    <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" minTickGap={16} />
                    <YAxis tickFormatter={compactCurrency} {...axisProps} width={76} />
                    <ReferenceLine y={0} stroke={CHART.axis} />
                    <Tooltip
                      cursor={{ stroke: CHART.axis }}
                      content={(
                        <ChartTooltip
                          names={{ balance: 'Saldo' }}
                          labelFormatter={(_, payload) => monthLabel(payload?.[0]?.payload?.key)}
                        />
                      )}
                    />
                    <Area
                      type="monotone"
                      dataKey="balance"
                      stroke={SERIES[0]}
                      strokeWidth={2}
                      fill="url(#balanceFill)"
                      dot={false}
                      activeDot={{ r: 5, strokeWidth: 2, stroke: '#fff' }}
                      {...ANIMATION}
                      animationDuration={1200}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <EmptyState icon={LineChartIcon} title="Sem histórico" message="O saldo mês a mês aparece depois dos primeiros lançamentos." />
            )}
          </div>
        </Panel>
      </div>

      <div className="stagger grid grid-cols-1 gap-6 xl:grid-cols-5">
        <Panel className="xl:col-span-3">
          <PanelHeader
            title="Ritmo de gastos"
            description="Gasto acumulado dia a dia: conta corrente e compras no cartão, contra o mês passado."
            actions={(
              <div className="text-right">
                <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Até hoje</p>
                <div className="flex items-center justify-end gap-2">
                  <DeltaBadge value={spendingVsLastMonth} inverse />
                  <p className="text-lg font-bold tabular text-zinc-950">{formatCurrency(currentSpending.total)}</p>
                </div>
              </div>
            )}
          />
          <div className="p-5">
            {currentSpending.total > 0 || previousSpending.total > 0 ? (
              <>
                <div className="mb-3 flex flex-wrap gap-4">
                  <LegendDot color={SERIES[0]} label={`Este mês (${shortMonth(currentKey)})`} shape="line" />
                  <LegendDot color="#a1a1aa" label={`Mês passado (${shortMonth(previousKey)})`} shape="line" />
                </div>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={spendingPace.rows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                      <CartesianGrid vertical={false} stroke={CHART.grid} />
                      <XAxis dataKey="day" {...axisProps} interval={4} />
                      <YAxis tickFormatter={compactCurrency} {...axisProps} width={76} />
                      <ReferenceLine
                        x={spendingPace.todayDay}
                        stroke={CHART.axis}
                        label={{ value: 'hoje', position: 'insideTopRight', fill: CHART.tick, fontSize: 11 }}
                      />
                      <Tooltip
                        cursor={{ stroke: CHART.axis }}
                        content={(
                          <ChartTooltip
                            names={{ current: 'Este mês', previous: 'Mês passado' }}
                            labelFormatter={(day) => `Dia ${day}`}
                          />
                        )}
                      />
                      <Line
                        type="monotone"
                        dataKey="previous"
                        stroke="#a1a1aa"
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4, strokeWidth: 2, stroke: '#fff' }}
                        connectNulls={false}
                        {...ANIMATION}
                      />
                      <Line
                        type="monotone"
                        dataKey="current"
                        stroke={SERIES[0]}
                        strokeWidth={2.5}
                        dot={false}
                        activeDot={{ r: 5, strokeWidth: 2, stroke: '#fff' }}
                        connectNulls={false}
                        {...ANIMATION}
                        animationDuration={1200}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </>
            ) : (
              <EmptyState icon={Receipt} title="Nenhum gasto registrado" message="O ritmo aparece com os primeiros gastos deste mês ou do anterior." />
            )}
          </div>
        </Panel>

        <Panel className="xl:col-span-2">
          <PanelHeader
            title={<PanelLink to="/planejamento/orcamento">Despesas por categoria</PanelLink>}
            description="Mês atual. A seta compara com o mês passado inteiro."
          />
          <div className="p-5">
            {categoryBreakdown.length > 0 ? (
              <div className="space-y-5">
                <DonutChart data={categoryBreakdown} centerLabel="No mês" legend={false} height={200} />
                <CategoryList items={categoryBreakdown} />
              </div>
            ) : (
              <EmptyState
                icon={Receipt}
                title="Nenhuma despesa no mês"
                message="As categorias aparecem assim que houver movimentações ou compras no cartão."
              />
            )}
          </div>
        </Panel>
      </div>

      {accounts.length > 0 ? (
        <Panel className="animate-fade-up">
          <PanelHeader
            title={<PanelLink to="/ajustes#contas">Saldo por conta</PanelLink>}
            description="O consolidado acima é a soma destas contas."
            actions={<Badge>{accounts.length} conta(s)</Badge>}
          />
          <div className="stagger grid grid-cols-1 gap-px bg-zinc-100 sm:grid-cols-2 lg:grid-cols-4">
            {accounts.map((account) => {
              const balance = Number(account.balance) || 0
              return (
                <div key={account.id} className="bg-white px-5 py-4 transition-colors hover:bg-zinc-50/70">
                  <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
                    {ACCOUNT_TYPE_LABELS[account.type] || account.type}
                  </p>
                  <p className="mt-1 font-medium text-zinc-900">{account.name}</p>
                  <p className={cx('mt-1 text-lg font-bold tabular', balance >= 0 ? 'text-zinc-950' : 'text-rose-600')}>
                    {formatCurrency(balance)}
                  </p>
                  <div className="mt-2 h-1 overflow-hidden rounded-full bg-zinc-100">
                    <div
                      className={cx('bar-grow h-full rounded-full', balance >= 0 ? 'bg-emerald-500' : 'bg-rose-500')}
                      style={{ width: `${(Math.abs(balance) / maxAccountBalance) * 100}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </Panel>
      ) : null}

      <div className="stagger grid grid-cols-1 gap-6 xl:grid-cols-5">
        <Panel className="xl:col-span-3">
          <PanelHeader
            title={<PanelLink to="/lancamentos/cartoes">Próximas faturas</PanelLink>}
            description="O que já está comprometido no cartão para os próximos meses, parcelas incluídas."
            actions={(
              <p className={cx('text-xl font-bold tabular', currentMonthInvoice > 0 ? 'text-rose-600' : 'text-emerald-700')}>
                {formatCurrency(currentMonthInvoice)}
              </p>
            )}
          />

          <div className="grid grid-cols-1 gap-6 p-5 lg:grid-cols-2">
            <div>
              {invoiceProjection.some((item) => item.value > 0) ? (
                <div className="h-60">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={invoiceProjection} margin={{ top: 20, right: 4, left: 0, bottom: 0 }}>
                      <CartesianGrid vertical={false} stroke={CHART.grid} />
                      <XAxis dataKey="label" {...axisProps} />
                      <YAxis tickFormatter={compactCurrency} {...axisProps} width={70} />
                      <Tooltip
                        cursor={{ fill: 'rgba(24,24,27,0.04)' }}
                        content={(
                          <ChartTooltip
                            names={{ value: 'Fatura' }}
                            labelFormatter={(_, payload) => monthLabel(payload?.[0]?.payload?.key)}
                          />
                        )}
                      />
                      <Bar dataKey="value" maxBarSize={28} radius={[4, 4, 0, 0]} {...ANIMATION}>
                        {invoiceProjection.map((item, index) => (
                          <Cell key={item.key} fill={index === 0 ? SERIES[1] : '#f6c3ad'} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <EmptyState icon={CreditCard} title="Nada comprometido" message="Sem compras abertas nos próximos meses." className="h-60 min-h-0" />
              )}
              <p className="mt-2 text-xs text-zinc-600">
                Em destaque, a fatura de {monthLabel(nextKey)}.
              </p>
            </div>

            <div className="flex flex-col">
              {currentMonthInvoice > 0 ? (
                <div className="flex flex-1 flex-col gap-4">
                  <div className="flex items-start gap-3 rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                    <CreditCard className="mt-0.5 h-4 w-4 shrink-0" />
                    <div>
                      <p className="font-semibold">{nextInvoiceItems.length} lançamento(s) em aberto</p>
                      <p className="mt-1 text-rose-600">O pagamento lança uma despesa na conta e baixa os itens da fatura.</p>
                    </div>
                  </div>

                  <div className="max-h-44 flex-1 space-y-2 overflow-y-auto pr-1">
                    {nextInvoiceItems.map((item) => (
                      <div key={item.id} className="flex items-center justify-between gap-3 rounded-lg border border-zinc-200 px-3 py-2.5 transition-colors hover:bg-zinc-50">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-zinc-900">{item.description}</p>
                          <p className="mt-0.5 text-xs text-zinc-600">
                            {item.card_name || item.credit_cards?.name || 'Cartão'}
                            {item.installment_info && item.installment_info !== '1/1' ? ` • ${item.installment_info}` : ''}
                          </p>
                        </div>
                        <span className="whitespace-nowrap text-sm font-bold tabular text-zinc-950">
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
                  className="h-full min-h-40"
                />
              )}
            </div>
          </div>
        </Panel>

        <Panel className="xl:col-span-2">
          <PanelHeader
            title={<PanelLink to="/lancamentos/cartoes">Parcelamentos abertos</PanelLink>}
            description="Compras agrupadas por cartão e compra original."
            actions={<Badge tone="warning">{formatCurrency(installmentTotal)}</Badge>}
          />

          <div className="p-5">
            {groupedInstallmentExpenses.length > 0 ? (
              <div className="stagger max-h-[420px] space-y-3 overflow-y-auto pr-1">
                {groupedInstallmentExpenses.map((expense) => {
                  const paid = expense.totalInstallments - expense.remainingInstallments
                  const progress = expense.totalInstallments > 0 ? (paid / expense.totalInstallments) * 100 : 0
                  return (
                    <div key={expense.key} className="rounded-lg border border-zinc-200 p-4 transition hover:border-zinc-300 hover:shadow-card">
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <p className="truncate font-semibold text-zinc-900">{expense.description}</p>
                          <div className="mt-2 flex flex-wrap gap-2">
                            <Badge tone="info">{expense.cardName}</Badge>
                            <Badge>{expense.remainingInstallments}x de {formatCurrency(expense.installmentAmount)}</Badge>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="whitespace-nowrap font-bold tabular text-zinc-950">
                            {formatCurrency(expense.installmentAmount * expense.remainingInstallments)}
                          </p>
                          <p className="mt-1 text-xs font-medium uppercase tracking-wide text-zinc-400">Restante</p>
                        </div>
                      </div>
                      <div className="mt-3 flex items-center gap-3">
                        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-zinc-100">
                          <div className="bar-grow h-full rounded-full bg-amber-500" style={{ width: `${progress}%` }} />
                        </div>
                        <span className="text-xs font-semibold tabular text-zinc-600">
                          {paid}/{expense.totalInstallments} pagas
                        </span>
                      </div>
                    </div>
                  )
                })}
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
      </div>
    </div>
  )
}

// Barra fina conta x investimentos dentro do card de patrimonio.
function WealthSplit({ cash, investments }) {
  const positiveCash = Math.max(cash, 0)
  const positiveInvestments = Math.max(investments, 0)
  const total = positiveCash + positiveInvestments
  if (total <= 0) return null
  const cashShare = (positiveCash / total) * 100

  return (
    <div className="flex h-full flex-col justify-end gap-2 px-1">
      <div className="flex h-2 gap-0.5 overflow-hidden rounded-full">
        <div className="bar-grow h-full rounded-l-full" style={{ width: `${cashShare}%`, backgroundColor: SERIES[0] }} />
        <div className="bar-grow h-full flex-1 rounded-r-full" style={{ backgroundColor: SERIES[2], animationDelay: '120ms' }} />
      </div>
      <div className="flex justify-between text-xs">
        <LegendDot color={SERIES[0]} label={`Conta ${cashShare.toFixed(0)}%`} />
        <LegendDot color={SERIES[2]} label={`Investido ${(100 - cashShare).toFixed(0)}%`} />
      </div>
    </div>
  )
}

function MonthProgress({ day, daysLeft }) {
  const total = day + daysLeft - 1
  const progress = (day / total) * 100
  return (
    <div className="flex items-center gap-3">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-zinc-100">
        <div className="bar-grow h-full rounded-full bg-zinc-800" style={{ width: `${progress}%` }} />
      </div>
      <span className="text-xs font-semibold tabular text-zinc-600">{progress.toFixed(0)}% do mês</span>
    </div>
  )
}

function CategoryList({ items }) {
  const sorted = [...items].sort((a, b) => b.value - a.value)
  const total = sorted.reduce((acc, item) => acc + item.value, 0)
  // Mesma ordem de cor da rosca: a cor segue o ranking do mes, e "Outros"
  // agrupa a partir da sexta categoria.
  return (
    <ul className="stagger space-y-2">
      {sorted.map((item, index) => {
        const color = index < 5 || sorted.length <= 6 ? SERIES[index] : '#a1a1aa'
        const cashShare = item.value > 0 ? (item.cash / item.value) * 100 : 0
        return (
          <li key={item.name} className="rounded-lg px-2 py-1.5 transition-colors hover:bg-zinc-50">
            <div className="flex items-center justify-between gap-3 text-sm">
              <span className="flex min-w-0 items-center gap-2 font-medium text-zinc-700">
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: color }} />
                <span className="truncate">{item.name}</span>
              </span>
              <span className="flex shrink-0 items-center gap-2">
                <DeltaBadge value={item.delta} inverse />
                <span className="font-semibold tabular text-zinc-950">{formatCurrency(item.value)}</span>
              </span>
            </div>
            <div className="mt-1.5 flex items-center gap-2">
              <div className="h-1 flex-1 overflow-hidden rounded-full bg-zinc-100">
                <div className="bar-grow h-full rounded-full" style={{ width: `${total > 0 ? (item.value / total) * 100 : 0}%`, backgroundColor: color }} />
              </div>
              <span className="w-24 text-right text-[11px] text-zinc-400">
                {item.credit > 0 && item.cash > 0
                  ? `${cashShare.toFixed(0)}% conta`
                  : item.credit > 0 ? 'cartão' : 'conta'}
              </span>
            </div>
          </li>
        )
      })}
    </ul>
  )
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-4 w-20" />
        <Skeleton className="h-8 w-56" />
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((index) => <Skeleton key={index} className="h-36" />)}
      </div>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
        <Skeleton className="h-96 xl:col-span-3" />
        <Skeleton className="h-96 xl:col-span-2" />
      </div>
    </div>
  )
}

// Titulo de painel que leva para a tela do assunto. A seta indica o link sem
// transformar o titulo em botao.
function PanelLink({ to, children }) {
  return (
    <Link
      to={to}
      className="group inline-flex items-center gap-1 rounded-sm text-zinc-950 transition-colors hover:text-emerald-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2"
    >
      {children}
      <ChevronRight
        aria-hidden="true"
        className="h-4 w-4 text-zinc-400 transition-transform group-hover:translate-x-0.5 group-hover:text-emerald-600"
      />
    </Link>
  )
}

// "Precisa de voce": so aparece quando ha algo a fazer.
function NeedsAttention({
  pendingRecurringCount,
  onRunRecurring,
  isRunningRecurring,
  invoiceAmount,
  invoiceItemCount,
  invoiceMonthLabel,
  onPayInvoice,
  isPayingInvoice,
}) {
  const hasRecurring = pendingRecurringCount > 0
  const hasInvoice = invoiceItemCount > 0 && invoiceAmount > 0
  if (!hasRecurring && !hasInvoice) return null

  return (
    <section aria-labelledby="precisa-de-voce" className="animate-fade-up rounded-xl border border-amber-200 bg-amber-50/60 p-4">
      <h2 id="precisa-de-voce" className="flex items-center gap-2 text-sm font-semibold text-amber-900">
        <BellRing className="h-4 w-4" />
        Precisa de você
      </h2>
      <ul className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
        {hasRecurring ? (
          <AttentionItem
            icon={Repeat}
            title={`${pendingRecurringCount} ${pendingRecurringCount === 1 ? 'recorrência vencida' : 'recorrências vencidas'}`}
            detail={(
              <Link to="/planejamento/recorrentes" className="underline-offset-2 hover:text-emerald-700 hover:underline">
                Ver recorrentes
              </Link>
            )}
            action={(
              <Button type="button" size="lg" icon={Repeat} loading={isRunningRecurring} onClick={onRunRecurring}>
                Lançar
              </Button>
            )}
          />
        ) : null}
        {hasInvoice ? (
          <AttentionItem
            icon={CreditCard}
            title={`Fatura em aberto: ${formatCurrency(invoiceAmount)}`}
            detail={`${invoiceMonthLabel} · ${invoiceItemCount} lançamento(s)`}
            action={(
              <Button type="button" size="lg" icon={CheckCircle2} loading={isPayingInvoice} onClick={onPayInvoice}>
                Pagar
              </Button>
            )}
          />
        ) : null}
      </ul>
    </section>
  )
}

function AttentionItem({ icon: Icon, title, detail, action }) {
  return (
    <li className="flex items-center justify-between gap-3 rounded-lg border border-amber-200/80 bg-white px-4 py-3">
      <div className="flex min-w-0 items-center gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-100 text-amber-700">
          <Icon className="h-4 w-4" />
        </span>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-zinc-900">{title}</p>
          <p className="mt-0.5 text-sm text-zinc-600">{detail}</p>
        </div>
      </div>
      <div className="shrink-0">{action}</div>
    </li>
  )
}

function InlineStat({ label, value, valueClassName = 'text-zinc-950' }) {
  return (
    <div className="rounded-lg border border-zinc-200/80 bg-zinc-50/60 px-3 py-2.5">
      <p className="truncate text-[11px] font-semibold uppercase tracking-wide text-zinc-500">{label}</p>
      <p className={cx('mt-0.5 truncate text-base font-bold tabular', valueClassName)}>{value}</p>
    </div>
  )
}
