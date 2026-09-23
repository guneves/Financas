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
  Receipt,
  Repeat,
  Wallet,
} from 'lucide-react'
import { apiFetch } from '../lib/api'
import { accountsApi, ccExpensesApi, creditCardsApi, recurringApi, transactionsApi } from '../lib/dataApi'
import { useDataVersion } from '../lib/newEntry'
import { EMPTY_PORTFOLIO } from '../lib/portfolio'
import PayInvoiceSheet from '../components/PayInvoiceSheet'
import {
  AlertMessage,
  Badge,
  Button,
  DeltaBadge,
  EmptyState,
  FitValue,
  MetricCard,
  PageHeader,
  Panel,
  PanelHeader,
  Skeleton,
  cx,
} from '../components/ui'
import {
  CHART,
  ChartTooltip,
  DonutChart,
  FLOW,
  LegendDot,
  SERIES,
  Sparkline,
  useChartAnimation,
  axisProps,
  compactAxis,
} from '../components/charts'
import { formatCurrency, formatDateBR, getLocalDateString, monthKey, monthLabel, shiftMonth, shortMonthLabel } from '../lib/format'
import { usePrivateAxisFormatter, usePrivateFormatter } from '../lib/privacy'
import { isInvestmentOutflow } from '../lib/transactions'

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

const shortMonth = shortMonthLabel

const isInvoicePayment = (transaction) => transaction.category?.startsWith('Pagamento Fatura')

const percentChange = (current, previous) => {
  if (!previous) return null
  return ((current - previous) / Math.abs(previous)) * 100
}

// Gasto de consumo de um mes, por dia e por categoria: saidas da conta (menos
// o pagamento de fatura, que ja e a soma das compras, e os aportes em
// investimento) + compras no cartao pelo valor total da compra, na data da compra.
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
    if (transaction.type !== 'EXPENSE' || isInvoicePayment(transaction) || isInvestmentOutflow(transaction)) return
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
  // Modo privado: saldos, patrimonio e carteira somem; fluxo, gastos e faturas ficam.
  const privateMoney = usePrivateFormatter(formatCurrency)
  const privateAxis = usePrivateAxisFormatter(compactAxis)
  const chartAnimation = useChartAnimation()
  const [portfolio, setPortfolio] = useState(null)
  const [portfolioError, setPortfolioError] = useState('')
  const [dataError, setDataError] = useState('')
  const [transactions, setTransactions] = useState([])
  const [ccExpenses, setCcExpenses] = useState([])
  const [accounts, setAccounts] = useState([])
  const [cards, setCards] = useState([])
  const [isPayingCurrentInvoice, setIsPayingCurrentInvoice] = useState(false)
  // Pagamento aguardando confirmacao no sheet: { title, description, invoices, total }.
  const [payRequest, setPayRequest] = useState(null)
  const [payError, setPayError] = useState('')
  const [recurringItems, setRecurringItems] = useState([])
  const [isRunningRecurring, setIsRunningRecurring] = useState(false)
  const [notice, setNotice] = useState('')
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

    // Cartoes so para o aviso de debito automatico sem saldo; falhar esconde o aviso.
    try {
      setCards((await creditCardsApi.list()) || [])
    } catch (error) {
      console.warn('Erro ao buscar cartões:', error)
      setCards([])
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

  // Entradas, saidas e saldo de fim de mes dos ultimos 12 meses. As saidas se
  // dividem em despesa e aporte: investir tira dinheiro da conta, mas nao e gasto.
  const monthlyHistory = useMemo(() => {
    const keys = Array.from({ length: HISTORY_MONTHS }, (_, index) => shiftMonth(currentKey, index - (HISTORY_MONTHS - 1)))
    const firstKey = keys[0]
    const byKey = Object.fromEntries(keys.map((key) => [key, { income: 0, expense: 0, investment: 0 }]))
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
      else if (isInvestmentOutflow(transaction)) byKey[key].investment += amount
      else byKey[key].expense += amount
    })

    let running = openingBalance
    return keys.map((key) => {
      const { income, expense, investment } = byKey[key]
      running += income - expense - investment
      return {
        key,
        label: shortMonth(key),
        income: Number(income.toFixed(2)),
        // Desenhadas abaixo do zero: a posicao diz "saida" sem depender da cor.
        expense: -Number(expense.toFixed(2)),
        investment: -Number(investment.toFixed(2)),
        net: Number((income - expense - investment).toFixed(2)),
        balance: Number(running.toFixed(2)),
      }
    })
  }, [transactions, currentKey])

  const flowSummary = useMemo(() => {
    const active = monthlyHistory.filter((item) => item.income !== 0 || item.expense !== 0 || item.investment !== 0)
    const income = monthlyHistory.reduce((acc, item) => acc + item.income, 0)
    const expense = monthlyHistory.reduce((acc, item) => acc - item.expense, 0)
    const investment = monthlyHistory.reduce((acc, item) => acc - item.investment, 0)
    const months = Math.max(active.length, 1)
    return {
      avgIncome: income / months,
      avgExpense: expense / months,
      avgInvestment: investment / months,
      // O que foi investido conta como poupado: so a despesa reduz a taxa.
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

  // So fatura fechada pode ser paga (o servidor recusa as outras). Uma por
  // cartao: cada uma vira um pagamento proprio.
  const payableInvoices = useMemo(() => {
    const byCard = {}
    nextInvoiceItems.forEach((item) => {
      if (item.invoice_closed !== true) return
      if (!byCard[item.card_id]) {
        byCard[item.card_id] = { card_id: item.card_id, invoice_month: item.invoice_month, invoice_year: item.invoice_year, total: 0 }
      }
      byCard[item.card_id].total += parseFloat(item.amount)
    })
    return Object.values(byCard)
  }, [nextInvoiceItems])

  const payableTotal = payableInvoices.reduce((acc, invoice) => acc + invoice.total, 0)

  // "Precisa de voce" so cobra fatura vencida: passou do dia do vencimento e
  // continua em aberto. A data vem do servidor (invoice_due_date).
  const overdueInvoices = useMemo(() => {
    const todayText = getLocalDateString()
    const byInvoice = {}
    openCcExpenses.forEach((item) => {
      if (!item.invoice_due_date || item.invoice_due_date >= todayText) return
      const key = `${item.card_id}|${item.invoice_year}-${item.invoice_month}`
      if (!byInvoice[key]) {
        byInvoice[key] = {
          card_id: item.card_id,
          card_name: item.credit_cards?.name || 'Cartão',
          invoice_month: item.invoice_month,
          invoice_year: item.invoice_year,
          due_date: item.invoice_due_date,
          total: 0,
          count: 0,
        }
      }
      byInvoice[key].total += parseFloat(item.amount)
      byInvoice[key].count += 1
    })
    return Object.values(byInvoice).sort((a, b) => a.due_date.localeCompare(b.due_date))
  }, [openCcExpenses])

  const overdueTotal = overdueInvoices.reduce((acc, invoice) => acc + invoice.total, 0)
  const overdueItemCount = overdueInvoices.reduce((acc, invoice) => acc + invoice.count, 0)
  const overdueDetail = overdueInvoices.length === 1
    ? `${overdueInvoices[0].card_name} · venceu em ${formatDateBR(overdueInvoices[0].due_date)}`
    : `${overdueInvoices.length} faturas · a mais antiga venceu em ${formatDateBR(overdueInvoices[0]?.due_date)}`

  // Debito automatico que a conta nao cobre: faturas de cartoes com debito
  // automatico que vencem nos proximos 31 dias, somadas por conta e comparadas
  // ao saldo de hoje. O debito acontece mesmo assim (deixa a conta negativa),
  // entao o aviso e para transferir antes. Fatura ainda aberta entra pelo
  // total atual, que ainda pode crescer.
  const autopayShortfalls = useMemo(() => {
    const todayText = getLocalDateString()
    const limit = new Date()
    limit.setDate(limit.getDate() + 31)
    const limitText = getLocalDateString(limit)
    const autopayByCard = Object.fromEntries(
      cards.filter((card) => card.autopay_account_id).map((card) => [card.id, card.autopay_account_id])
    )
    const byAccount = {}
    openCcExpenses.forEach((item) => {
      const accountId = autopayByCard[item.card_id]
      const due = item.invoice_due_date
      if (!accountId || !due || due < todayText || due > limitText) return
      if (!byAccount[accountId]) byAccount[accountId] = { accountId, total: 0, firstDue: due }
      byAccount[accountId].total += parseFloat(item.amount) || 0
      if (due < byAccount[accountId].firstDue) byAccount[accountId].firstDue = due
    })
    return Object.values(byAccount)
      .map((entry) => {
        const account = accounts.find((row) => row.id === entry.accountId)
        if (!account || account.archived_at) return null
        const accountBalance = Number(account.balance) || 0
        return accountBalance < entry.total
          ? { ...entry, accountName: account.name, balance: accountBalance, missing: entry.total - accountBalance }
          : null
      })
      .filter(Boolean)
      .sort((a, b) => a.firstDue.localeCompare(b.firstDue))
  }, [cards, accounts, openCcExpenses])

  const nextClosingDate = useMemo(() => nextInvoiceItems
    .filter((item) => item.invoice_closed !== true && item.invoice_closing_date)
    .map((item) => item.invoice_closing_date)
    .sort()[0] || null, [nextInvoiceItems])

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

  const handlePayCurrentMonthInvoice = () => {
    if (payableInvoices.length === 0 || payableTotal <= 0) return
    setPayError('')
    setPayRequest({
      title: 'Pagar fatura do mês',
      description: payableInvoices.length === 1
        ? 'Fatura fechada deste mês.'
        : `${payableInvoices.length} faturas fechadas deste mês, uma por cartão.`,
      invoices: payableInvoices,
      total: payableTotal,
    })
  }

  const handlePayOverdueInvoices = () => {
    if (overdueInvoices.length === 0) return
    setPayError('')
    setPayRequest({
      title: overdueInvoices.length === 1 ? 'Pagar fatura vencida' : `Pagar ${overdueInvoices.length} faturas vencidas`,
      description: overdueDetail,
      invoices: overdueInvoices,
      total: overdueTotal,
    })
  }

  // Um pedido por fatura. Sem conta escolhida, o servidor usa a do debito
  // automatico de cada cartao ou a conta padrao.
  const confirmPayInvoices = async (accountId) => {
    if (!payRequest) return
    setIsPayingCurrentInvoice(true)
    setPayError('')
    setNotice('')
    try {
      for (const invoice of payRequest.invoices) {
        await ccExpensesApi.payInvoice({
          card_id: invoice.card_id,
          invoice_month: invoice.invoice_month,
          invoice_year: invoice.invoice_year,
          account_id: accountId || undefined,
        })
      }
      const paid = payRequest.invoices.length
      setPayRequest(null)
      setNotice(`${paid === 1 ? 'Fatura paga' : `${paid} faturas pagas`} — ${formatCurrency(payRequest.total)} debitado.`)
      await fetchAllData()
    } catch (error) {
      console.warn('Erro ao pagar fatura:', error)
      setPayError(error.message || 'Não foi possível pagar a fatura.')
      // Algumas faturas podem ter sido pagas antes do erro.
      await fetchAllData()
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
        title="Início"
        description="Patrimônio, saldo disponível, despesas do mês e compromissos em aberto."
        meta={<Badge>{monthLabel(currentKey)}</Badge>}
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
        invoiceAmount={overdueTotal}
        invoiceItemCount={overdueItemCount}
        invoiceDetail={overdueDetail}
        onPayInvoice={handlePayOverdueInvoices}
        isPayingInvoice={isPayingCurrentInvoice}
        autopayShortfalls={autopayShortfalls}
      />

      <PayInvoiceSheet
        open={Boolean(payRequest)}
        onClose={() => setPayRequest(null)}
        title={payRequest?.title}
        description={payRequest?.description}
        total={payRequest?.total || 0}
        accounts={accounts}
        allowPerCard
        saving={isPayingCurrentInvoice}
        error={payError}
        onConfirm={confirmPayInvoices}
      />

      <div className="stagger grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={Landmark}
          tone="dark"
          title="Patrimônio total"
          sensitive
          amount={totalWealth}
          format={formatCurrency}
          subtitle="Conta corrente + investimentos"
          chart={<WealthSplit cash={bankBalance} investments={investmentsNetBalance} />}
        />
        <MetricCard
          icon={Wallet}
          tone={bankBalance >= 0 ? 'success' : 'danger'}
          title="Saldo em conta"
          sensitive
          amount={bankBalance}
          format={formatCurrency}
          valueClassName={bankBalance >= 0 ? 'text-zinc-950' : 'text-rose-600'}
          delta={<DeltaBadge value={percentChange(bankBalance, previousMonthBalance)} />}
          subtitle="vs. fim do mês passado"
          chart={<Sparkline data={monthlyHistory} dataKey="balance" color={SERIES[0]} formatter={privateMoney} />}
        />
        <MetricCard
          icon={PiggyBank}
          title="Investimentos"
          sensitive
          amount={investmentsNetBalance}
          format={formatCurrency}
          subtitle="Saldo líquido estimado"
        />
        <MetricCard
          icon={CalendarDays}
          tone={dailyAvailable >= 0 ? 'neutral' : 'danger'}
          title="Disponível por dia"
          sensitive
          amount={dailyAvailable}
          format={formatCurrency}
          valueClassName={dailyAvailable >= 0 ? 'text-zinc-950' : 'text-rose-600'}
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
            description="Entradas, despesas e aportes da conta nos últimos 12 meses. Transferências entre contas não entram."
          />
          <div className="p-5">
            {flowSummary.hasData ? (
              <>
                <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <InlineStat label="Média de entradas" value={formatCurrency(flowSummary.avgIncome)} />
                  <InlineStat label="Média de despesas" value={formatCurrency(flowSummary.avgExpense)} />
                  <InlineStat label="Média investida" value={formatCurrency(flowSummary.avgInvestment)} />
                  <InlineStat
                    label="Taxa de poupança"
                    value={flowSummary.savingsRate === null ? '—' : `${flowSummary.savingsRate.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`}
                    valueClassName={flowSummary.savingsRate !== null && flowSummary.savingsRate < 0 ? 'text-rose-600' : 'text-emerald-700'}
                  />
                </div>
                {/* Legenda junto do grafico, nao no cabecalho: la ela espremia a
                    descricao numa coluna estreita. */}
                <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1">
                  <LegendDot color={FLOW.income} label="Entradas" />
                  <LegendDot color={FLOW.expense} label="Despesas" />
                  <LegendDot color={FLOW.investment} label="Investimentos" />
                  <LegendDot color={FLOW.net} label="Resultado" shape="line" />
                </div>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={monthlyHistory} stackOffset="sign" margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid vertical={false} stroke={CHART.grid} />
                      <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" />
                      <YAxis tickFormatter={compactAxis} {...axisProps} width={56} />
                      <ReferenceLine y={0} stroke={CHART.axis} />
                      <Tooltip
                        cursor={{ fill: 'rgba(24,24,27,0.04)' }}
                        content={(
                          <ChartTooltip
                            absolute
                            names={{ income: 'Entradas', expense: 'Despesas', investment: 'Investimentos', net: 'Resultado' }}
                            labelFormatter={(_, payload) => monthLabel(payload?.[0]?.payload?.key)}
                          />
                        )}
                      />
                      <Bar dataKey="income" stackId="flow" fill={FLOW.income} maxBarSize={24} radius={[4, 4, 0, 0]} {...chartAnimation} />
                      <Bar dataKey="expense" stackId="flow" fill={FLOW.expense} maxBarSize={24} {...chartAnimation} />
                      <Bar dataKey="investment" stackId="flow" fill={FLOW.investment} maxBarSize={24} radius={[4, 4, 0, 0]} {...chartAnimation} />
                      <Line
                        type="monotone"
                        dataKey="net"
                        stroke={FLOW.net}
                        strokeWidth={2}
                        dot={{ r: 3, fill: FLOW.net, strokeWidth: 2, stroke: '#fff' }}
                        activeDot={{ r: 5, strokeWidth: 2, stroke: '#fff' }}
                        {...chartAnimation}
                        animationBegin={160}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </>
            ) : (
              <EmptyState icon={Receipt} title="Sem movimentações" message="O fluxo aparece assim que houver entradas, despesas ou aportes lançados." />
            )}
          </div>
        </Panel>

        <Panel className="xl:col-span-2">
          <PanelHeader
            title="Evolução do saldo"
            description="Saldo consolidado no fim de cada mês."
            actions={<Badge tone={bankBalance >= 0 ? 'neutral' : 'danger'}>{privateMoney(bankBalance)}</Badge>}
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
                    <YAxis tickFormatter={privateAxis} {...axisProps} width={56} />
                    <ReferenceLine y={0} stroke={CHART.axis} />
                    <Tooltip
                      cursor={{ stroke: CHART.axis }}
                      content={(
                        <ChartTooltip
                          names={{ balance: 'Saldo' }}
                          valueFormatter={privateMoney}
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
                      {...chartAnimation}
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

      <div className="stagger grid grid-cols-1 items-start gap-6 xl:grid-cols-5">
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
                      <YAxis tickFormatter={compactAxis} {...axisProps} width={56} />
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
                        {...chartAnimation}
                      />
                      <Line
                        type="monotone"
                        dataKey="current"
                        stroke={SERIES[0]}
                        strokeWidth={2.5}
                        dot={false}
                        activeDot={{ r: 5, strokeWidth: 2, stroke: '#fff' }}
                        connectNulls={false}
                        {...chartAnimation}
                        animationBegin={80}
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
          <div className="stagger grid grid-cols-1 gap-px bg-zinc-100 sm:grid-cols-[repeat(auto-fit,minmax(13rem,1fr))]">
            {accounts.map((account) => {
              const balance = Number(account.balance) || 0
              return (
                <div key={account.id} className="bg-white px-5 py-4 transition-colors hover:bg-zinc-50/70">
                  <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
                    {ACCOUNT_TYPE_LABELS[account.type] || account.type}
                  </p>
                  <p className="mt-1 font-medium text-zinc-900">{account.name}</p>
                  <p className={cx('mt-1 text-lg font-bold tabular', balance >= 0 ? 'text-zinc-950' : 'text-rose-600')}>
                    {privateMoney(balance)}
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
              <p className="text-xl font-bold tabular text-zinc-950">
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
                      <YAxis tickFormatter={compactAxis} {...axisProps} width={56} />
                      <Tooltip
                        cursor={{ fill: 'rgba(24,24,27,0.04)' }}
                        content={(
                          <ChartTooltip
                            names={{ value: 'Fatura' }}
                            labelFormatter={(_, payload) => monthLabel(payload?.[0]?.payload?.key)}
                          />
                        )}
                      />
                      <Bar dataKey="value" maxBarSize={28} radius={[4, 4, 0, 0]} {...chartAnimation}>
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

                  {payableInvoices.length === 0 && nextClosingDate ? (
                    <p className="text-xs text-zinc-600">
                      A fatura fecha em {formatDateBR(nextClosingDate)}; o pagamento é liberado depois do fechamento.
                    </p>
                  ) : null}
                  <Button
                    type="button"
                    onClick={handlePayCurrentMonthInvoice}
                    loading={isPayingCurrentInvoice}
                    disabled={payableInvoices.length === 0}
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
            actions={<Badge>{formatCurrency(installmentTotal)}</Badge>}
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
                            <Badge>{expense.cardName}</Badge>
                            <Badge>{expense.remainingInstallments}x de {formatCurrency(expense.installmentAmount)}</Badge>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="whitespace-nowrap font-bold tabular text-zinc-950">
                            {formatCurrency(expense.installmentAmount * expense.remainingInstallments)}
                          </p>
                          <p className="mt-1 text-xs font-medium uppercase tracking-wide text-zinc-500">Restante</p>
                        </div>
                      </div>
                      <div className="mt-3 flex items-center gap-3">
                        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-zinc-100">
                          <div className="bar-grow h-full rounded-full bg-zinc-800" style={{ width: `${progress}%` }} />
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
              <span className="w-24 text-right text-xs text-zinc-500">
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
  invoiceDetail,
  onPayInvoice,
  isPayingInvoice,
  autopayShortfalls = [],
}) {
  // Saldo da conta (e o que falta, que o revela) somem no modo privado.
  const privateMoney = usePrivateFormatter(formatCurrency)
  const hasRecurring = pendingRecurringCount > 0
  const hasInvoice = invoiceItemCount > 0 && invoiceAmount > 0
  if (!hasRecurring && !hasInvoice && autopayShortfalls.length === 0) return null

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
            title={`Fatura vencida: ${formatCurrency(invoiceAmount)}`}
            detail={`${invoiceDetail} · ${invoiceItemCount} lançamento(s)`}
            action={(
              <Button type="button" size="lg" icon={CheckCircle2} loading={isPayingInvoice} onClick={onPayInvoice}>
                Pagar
              </Button>
            )}
          />
        ) : null}
        {autopayShortfalls.map((entry) => (
          <AttentionItem
            key={entry.accountId}
            icon={Wallet}
            title={`Débito automático sem saldo: faltam ${privateMoney(entry.missing)}`}
            detail={`${entry.accountName} tem ${privateMoney(entry.balance)} para ${formatCurrency(entry.total)} a debitar · o primeiro em ${formatDateBR(entry.firstDue)}`}
            action={(
              <Link to="/lancamentos/cartoes" className="text-sm font-semibold text-emerald-700 underline-offset-2 hover:underline">
                Ver faturas
              </Link>
            )}
          />
        ))}
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
      <p className="text-xs font-semibold leading-4 text-zinc-500">{label}</p>
      <FitValue measure={value} baseSize={16} minSize={12} className={cx('mt-1 font-bold', valueClassName)}>{value}</FitValue>
    </div>
  )
}
