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
  CheckCircle2,
  ChevronRight,
  CreditCard,
  LineChart as LineChartIcon,
  ListChecks,
  Receipt,
  Repeat,
  Target,
  Wallet,
} from 'lucide-react'
import { accountsApi, budgetsApi, ccExpensesApi, creditCardsApi, recurringApi, transactionsApi } from '../lib/dataApi'
import { useOutbox } from '../lib/outbox'
import { PENDING, applyPendingToAccounts, pendingAsTransactions } from '../lib/outboxRules'
import { invalidateServerData, queryErrorMessage, useQuery } from '../lib/queries'
import PayInvoiceSheet from '../components/PayInvoiceSheet'
import {
  BUDGET_STATUS_LABELS,
  BUDGET_STATUS_TONES,
  BudgetProgressBar,
  budgetStatus,
} from '../components/BudgetProgress'
import {
  AlertMessage,
  AnimatedNumber,
  Badge,
  Button,
  DeltaBadge,
  EmptyState,
  FitValue,
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
  OTHER_COLOR,
  SERIES,
  useChartAnimation,
  axisProps,
  compactAxis,
} from '../components/charts'
import { formatCurrency, formatDateBR, formatSignedCurrency, getLocalDateString, monthKey, monthLabel, shiftMonth, shortMonthLabel } from '../lib/format'
import { MASKED_CURRENCY, usePrivateAxisFormatter, usePrivateFormatter, useValuesHidden } from '../lib/privacy'
import { accountBalanceBrl, activeAccounts, consolidatedBalance, isInvestmentInflow, isInvestmentOutflow, openingBalanceTotal } from '../lib/transactions'
import { toast } from '../lib/toast'

const HISTORY_MONTHS = 12
const INVOICE_MONTHS = 6
// Meses anteriores que formam a media do "Ritmo de gastos".
const PACE_MONTHS = 3

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

const NO_ITEMS = []

export default function Dashboard() {
  // Inicio e so a area bancaria: nada da carteira entra aqui, para o saldo
  // nao parecer dinheiro que da para gastar. Modo privado: os saldos somem;
  // fluxo, gastos e faturas ficam.
  const privateMoney = usePrivateFormatter(formatCurrency)
  const privateAxis = usePrivateAxisFormatter(compactAxis)
  const chartAnimation = useChartAnimation()
  const [dataError, setDataError] = useState('')
  const [isPayingCurrentInvoice, setIsPayingCurrentInvoice] = useState(false)
  // Pagamento aguardando confirmacao no sheet: { title, description, invoices, total }.
  const [payRequest, setPayRequest] = useState(null)
  const [payError, setPayError] = useState('')
  const [isRunningRecurring, setIsRunningRecurring] = useState(false)

  // Quatro queries independentes: uma que falha nao derruba as outras. As
  // movimentacoes mostram erro; cartoes, recorrencias e orcamento so escondem
  // o aviso ou a faixa que dependem deles.
  // Todas as compras do cartao, nao so as abertas: o ritmo de gastos do mes
  // passado precisa das compras que ja foram pagas.
  const movementsQuery = useQuery({
    queryKey: ['inicio', 'movimentos'],
    queryFn: async () => {
      const [transactions, ccExpenses, accounts] = await Promise.all([
        transactionsApi.list(),
        ccExpensesApi.list(),
        accountsApi.list({ include_archived: 1 }),
      ])
      return { transactions: transactions || [], ccExpenses: ccExpenses || [], allAccounts: accounts || [] }
    },
  })
  // Cartoes so para o aviso de debito automatico sem saldo.
  const cardsQuery = useQuery({ queryKey: ['inicio', 'cartoes'], queryFn: () => creditCardsApi.list() })
  // Recorrencias vencidas para o "Precisa de voce".
  const recurringQuery = useQuery({ queryKey: ['inicio', 'recorrencias'], queryFn: () => recurringApi.list() })
  // Orcamento do mes para a faixa de orcamento.
  const budgetMonth = monthKey(new Date())
  const budgetQuery = useQuery({ queryKey: ['inicio', 'orcamento', budgetMonth], queryFn: () => budgetsApi.month(budgetMonth) })

  // Lancamentos guardados no aparelho, ainda sem chegar ao servidor
  // (lib/outbox.js): entram nas contas e no mes como em Lancamentos, e o
  // saldo fica marcado como estimativa. O saldo e o historico leem a mesma
  // lista, entao a curva continua terminando no saldo do topo.
  const pending = useOutbox()
  const serverTransactions = movementsQuery.data?.transactions || NO_ITEMS
  const serverAccounts = movementsQuery.data?.allAccounts || NO_ITEMS
  const transactions = useMemo(() => {
    const waiting = pending.filter((item) => item.status === PENDING)
    if (!waiting.length) return serverTransactions
    const defaultAccountId = serverAccounts.find((account) => account.is_default)?.id || ''
    return [...pendingAsTransactions(waiting, { defaultAccountId }), ...serverTransactions]
  }, [serverTransactions, serverAccounts, pending])
  const ccExpenses = movementsQuery.data?.ccExpenses || NO_ITEMS
  // Todas as contas, arquivadas inclusive: o consolidado soma todas.
  const allAccounts = useMemo(() => applyPendingToAccounts(serverAccounts, pending), [serverAccounts, pending])
  const pendingInBalance = useMemo(
    () => pending.filter((item) => item.status === PENDING && item.kind !== 'CARD').length,
    [pending]
  )
  const cards = cardsQuery.data || NO_ITEMS
  const recurringItems = recurringQuery.data?.items || NO_ITEMS
  const budget = budgetQuery.data || null

  useEffect(() => {
    if (movementsQuery.error) {
      console.warn('Erro ao buscar movimentações:', movementsQuery.error)
      setDataError(queryErrorMessage(movementsQuery, 'Não foi possível carregar movimentações e faturas.'))
    }
  }, [movementsQuery.error])

  const fetchAllData = () => invalidateServerData()

  // Mesma conta da tela Recorrentes: soma do pending_count de cada recorrencia.
  const pendingRecurringCount = useMemo(
    () => recurringItems.reduce((total, item) => total + Number(item.pending_count || 0), 0),
    [recurringItems]
  )

  // Mesma chamada do botao "Lancar pendentes" de Recorrentes (idempotente).
  const handleRunRecurring = async () => {
    setIsRunningRecurring(true)
    setDataError('')
    try {
      const result = await recurringApi.run()
      toast(
        result?.created
          ? `${result.created} lançamento(s) recorrente(s) gerado(s).`
          : 'Nada pendente: todos os lançamentos recorrentes já estão em dia.',
        { tone: result?.created ? 'success' : 'info' }
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
  const nextKey = shiftMonth(currentKey, 1)

  const openCcExpenses = useMemo(() => ccExpenses.filter((expense) => expense.status === 'OPEN'), [ccExpenses])

  const accounts = useMemo(() => activeAccounts(allAccounts), [allAccounts])
  // A soma dos saldos de /api/accounts: inclui o saldo inicial de cada conta,
  // que a soma dos lancamentos deixava de fora (lib/transactions.js).
  const bankBalance = useMemo(() => consolidatedBalance(allAccounts), [allAccounts])

  // Entradas, saidas e saldo de fim de mes dos ultimos 12 meses. Investimento
  // fica a parte (lib/transactions.js): o aporte tira dinheiro da conta mas nao
  // e gasto, e o resgate devolve mas nao e receita. Todos mexem no saldo.
  const monthlyHistory = useMemo(() => {
    const keys = Array.from({ length: HISTORY_MONTHS }, (_, index) => shiftMonth(currentKey, index - (HISTORY_MONTHS - 1)))
    const firstKey = keys[0]
    const byKey = Object.fromEntries(keys.map((key) => [key, { income: 0, expense: 0, invested: 0, redeemed: 0 }]))
    // Saldo inicial das contas + tudo antes da janela: a curva termina no
    // mesmo saldo do topo da pagina.
    let openingBalance = openingBalanceTotal(allAccounts)

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
      if (isInvestmentInflow(transaction)) byKey[key].redeemed += amount
      else if (transaction.type === 'INCOME') byKey[key].income += amount
      else if (isInvestmentOutflow(transaction)) byKey[key].invested += amount
      else byKey[key].expense += amount
    })

    let running = openingBalance
    return keys.map((key) => {
      const { income, expense, invested, redeemed } = byKey[key]
      const net = income - expense - invested + redeemed
      running += net
      return {
        key,
        label: shortMonth(key),
        income: Number(income.toFixed(2)),
        // Desenhadas abaixo do zero: a posicao diz "saida" sem depender da cor.
        expense: -Number(expense.toFixed(2)),
        // Uma serie so, liquida (aportes menos resgates): abaixo do zero quando
        // saiu mais do que voltou, acima no mes em que o resgate foi maior.
        investment: -Number((invested - redeemed).toFixed(2)),
        invested: Number(invested.toFixed(2)),
        redeemed: Number(redeemed.toFixed(2)),
        net: Number(net.toFixed(2)),
        balance: Number(running.toFixed(2)),
      }
    })
  }, [transactions, allAccounts, currentKey])

  const flowSummary = useMemo(() => {
    const hasInvestment = (item) => item.invested !== 0 || item.redeemed !== 0
    const active = monthlyHistory.filter((item) => item.income !== 0 || item.expense !== 0 || hasInvestment(item))
    const income = monthlyHistory.reduce((acc, item) => acc + item.income, 0)
    const expense = monthlyHistory.reduce((acc, item) => acc - item.expense, 0)
    const investment = monthlyHistory.reduce((acc, item) => acc - item.investment, 0)
    const months = Math.max(active.length, 1)
    return {
      avgIncome: income / months,
      avgExpense: expense / months,
      avgInvestment: investment / months,
      // O que foi investido conta como poupado: so a despesa reduz a taxa. O
      // resgate ja ficou fora da receita.
      savingsRate: income > 0 ? ((income - expense) / income) * 100 : null,
      hasData: active.length > 0,
      // So existe investimento aqui se algum aporte ou resgate passou pelo
      // extrato; sem isso a media e a serie do grafico nem aparecem.
      hasInvestment: monthlyHistory.some(hasInvestment),
    }
  }, [monthlyHistory])

  const currentSpending = useMemo(() => buildSpending(transactions, ccExpenses, currentKey), [transactions, ccExpenses, currentKey])
  // Os meses anteriores, do mais recente para o mais antigo.
  const pastSpending = useMemo(
    () => Array.from({ length: PACE_MONTHS }, (_, index) => {
      const key = shiftMonth(currentKey, -(index + 1))
      return { key, ...buildSpending(transactions, ccExpenses, key) }
    }),
    [transactions, ccExpenses, currentKey]
  )
  const previousSpending = pastSpending[0]

  // Acumulado dia a dia: este mes (ate hoje) contra a media dos meses
  // anteriores no mesmo dia. Mes sem nenhum gasto e mes sem registro (antes de
  // comecar a usar o app) e fica fora da media, senao ela puxaria para baixo.
  // Mes mais curto que o dia de hoje entra pelo total dele.
  const spendingPace = useMemo(() => {
    const daysInCurrent = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate()
    const todayDay = today.getDate()
    const baseline = pastSpending.filter((month) => month.total > 0)
    const running = baseline.map(() => 0)
    let current = 0
    let currentToDate = 0
    let averageToDate = 0
    let monthsToDate = baseline.map(() => 0)
    const rows = []
    for (let day = 1; day <= Math.max(daysInCurrent, 31); day += 1) {
      current += currentSpending.byDay[day] || 0
      baseline.forEach((month, index) => {
        running[index] += month.byDay[day] || 0
      })
      const average = baseline.length > 0 ? running.reduce((acc, value) => acc + value, 0) / baseline.length : null
      if (day === todayDay) {
        currentToDate = current
        averageToDate = average || 0
        monthsToDate = [...running]
      }
      rows.push({
        day,
        current: day <= todayDay ? Number(current.toFixed(2)) : null,
        average: average === null ? null : Number(average.toFixed(2)),
      })
    }
    return {
      rows,
      todayDay,
      currentToDate,
      averageToDate,
      averageMonth: baseline.length > 0 ? baseline.reduce((acc, month) => acc + month.total, 0) / baseline.length : 0,
      months: baseline.map((month, index) => ({ key: month.key, toDate: monthsToDate[index] })),
    }
  }, [currentSpending, pastSpending])

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
        // Em reais, como a fatura. Sem cambio hoje nao da para dizer se cobre.
        const accountBalance = accountBalanceBrl(account)
        if (accountBalance === null) return null
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
      toast(`${paid === 1 ? 'Fatura paga' : `${paid} faturas pagas`} — ${formatCurrency(payRequest.total)} debitado.`)
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

  // Esqueleto ate as movimentacoes chegarem: sem elas os numeros de cima
  // piscariam zerados.
  if (movementsQuery.isPending) {
    return <DashboardSkeleton />
  }

  const daysRemainingInMonth = getDaysRemainingInMonth()
  const dailyAvailable = (bankBalance - currentMonthInvoice) / daysRemainingInMonth
  const paceMonths = spendingPace.months.length
  const paceDifference = spendingPace.currentToDate - spendingPace.averageToDate
  const spendingVsAverage = paceMonths > 0 ? percentChange(spendingPace.currentToDate, spendingPace.averageToDate) : null
  const paceAverageLabel = paceMonths > 1 ? `Média de ${paceMonths} meses` : `Mês de ${shortMonth(spendingPace.months[0]?.key)}`
  // Movimento do mes nas contas: receitas menos despesas, menos aportes, mais
  // resgates — o "Resultado" do fluxo de caixa. Aporte e resgate nao sao
  // despesa nem receita (lib/transactions.js) e aparecem a parte.
  const currentMonth = monthlyHistory[monthlyHistory.length - 1] || { income: 0, expense: 0, invested: 0, redeemed: 0, net: 0 }
  const monthIncome = currentMonth.income
  const monthExpense = -currentMonth.expense

  return (
    <div className="space-y-5">
      <h1 className="sr-only">Início</h1>
      {dataError ? (
        <AlertMessage tone="danger" message={`Movimentações indisponíveis no momento. Detalhe: ${dataError}`} />
      ) : null}


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

      {pendingInBalance ? (
        <AlertMessage
          tone="info"
          message={`Saldo estimado: ${pendingInBalance === 1 ? '1 lançamento guardado neste aparelho ainda não chegou' : `${pendingInBalance} lançamentos guardados neste aparelho ainda não chegaram`} ao servidor.`}
        />
      ) : null}

      <div className="grid grid-cols-1 gap-4 sm:gap-5 xl:grid-cols-12">
        <BalanceHero
          className="xl:col-span-8"
          total={bankBalance}
          accounts={accounts}
          monthName={monthLabel(currentKey)}
          result={currentMonth.net}
          income={monthIncome}
          expense={monthExpense}
          invested={currentMonth.invested}
          redeemed={currentMonth.redeemed}
        />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-5 xl:col-span-4 xl:grid-cols-1">
          <DailyTile
            value={dailyAvailable}
            day={today.getDate()}
            daysLeft={daysRemainingInMonth}
          />
          <NextInvoiceTile
            total={currentMonthInvoice}
            closingDate={nextClosingDate}
            payable={payableInvoices.length > 0}
            label={monthLabel(nextKey)}
          />
        </div>
      </div>

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
        budget={budget}
        payableTotal={payableTotal}
        onPayPayable={handlePayCurrentMonthInvoice}
      />

      <div className="stagger grid grid-cols-1 gap-5 xl:grid-cols-5">
        {/* A linha estica os dois paineis ate a altura de "Despesas por
            categoria"; o grafico cresce junto em vez de deixar um vazio embaixo. */}
        <Panel className="flex flex-col xl:col-span-3">
          <PanelHeader
            title={<PanelLink to="/lancamentos/extrato">Fluxo de caixa</PanelLink>}
            description={flowSummary.hasInvestment
              ? 'Receitas, despesas e investimentos (aportes menos resgates) lançados nas contas nos últimos 12 meses. Transferências entre contas não entram.'
              : 'Receitas e despesas das contas nos últimos 12 meses. Transferências entre contas não entram.'}
          />
          <div className="flex flex-1 flex-col p-5">
            {flowSummary.hasData ? (
              <>
                {/* Sem investimento no extrato sao tres numeros: a taxa ocupa a
                    linha inteira no celular para nao sobrar um buraco. */}
                <div className={cx('mb-4 grid grid-cols-2 gap-3', flowSummary.hasInvestment ? 'sm:grid-cols-4' : 'sm:grid-cols-3')}>
                  <InlineStat label="Média de receitas" value={formatCurrency(flowSummary.avgIncome)} />
                  <InlineStat label="Média de despesas" value={formatCurrency(flowSummary.avgExpense)} />
                  {flowSummary.hasInvestment ? (
                    <InlineStat
                      label={flowSummary.avgInvestment < 0 ? 'Média resgatada' : 'Média investida'}
                      value={formatCurrency(Math.abs(flowSummary.avgInvestment))}
                    />
                  ) : null}
                  <InlineStat
                    label="Taxa de poupança"
                    value={flowSummary.savingsRate === null ? '—' : `${flowSummary.savingsRate.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`}
                    valueClassName={flowSummary.savingsRate !== null && flowSummary.savingsRate < 0 ? 'text-rose-600' : 'text-emerald-700'}
                    className={flowSummary.hasInvestment ? '' : 'col-span-2 sm:col-span-1'}
                  />
                </div>
                {/* Legenda junto do grafico, nao no cabecalho: la ela espremia a
                    descricao numa coluna estreita. */}
                <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1">
                  <LegendDot color={FLOW.income} label="Receitas" />
                  <LegendDot color={FLOW.expense} label="Despesas" />
                  {flowSummary.hasInvestment ? <LegendDot color={FLOW.investment} label="Investimentos" /> : null}
                  <LegendDot color={FLOW.net} label="Resultado" shape="line" />
                </div>
                <div className="h-72 xl:h-auto xl:min-h-72 xl:flex-1">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={monthlyHistory} stackOffset="sign" margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid vertical={false} stroke={CHART.grid} />
                      <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" />
                      <YAxis tickFormatter={compactAxis} {...axisProps} width={56} />
                      <ReferenceLine y={0} stroke={CHART.axis} />
                      <Tooltip cursor={{ fill: 'rgb(var(--zinc-950) / 0.05)' }} content={<FlowTooltip />} />
                      <Bar dataKey="income" stackId="flow" fill={FLOW.income} maxBarSize={24} radius={[4, 4, 0, 0]} {...chartAnimation} />
                      <Bar dataKey="expense" stackId="flow" fill={FLOW.expense} maxBarSize={24} {...chartAnimation} />
                      {flowSummary.hasInvestment ? (
                        <Bar dataKey="investment" stackId="flow" fill={FLOW.investment} maxBarSize={24} radius={[4, 4, 0, 0]} {...chartAnimation} />
                      ) : null}
                      <Line
                        type="monotone"
                        dataKey="net"
                        stroke={FLOW.net}
                        strokeWidth={2}
                        dot={{ r: 3, fill: FLOW.net, strokeWidth: 2, stroke: 'rgb(var(--white))' }}
                        activeDot={{ r: 5, strokeWidth: 2, stroke: 'rgb(var(--white))' }}
                        {...chartAnimation}
                        animationBegin={160}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </>
            ) : (
              <EmptyState icon={Receipt} title="Sem movimentações" message="O fluxo aparece assim que houver receitas ou despesas lançadas." />
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

      <BudgetStrip budget={budget} />

      <div className="stagger grid grid-cols-1 gap-5 xl:grid-cols-5">
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
                        cursor={{ fill: 'rgb(var(--zinc-950) / 0.05)' }}
                        content={(
                          <ChartTooltip
                            names={{ value: 'Fatura' }}
                            labelFormatter={(_, payload) => monthLabel(payload?.[0]?.payload?.key)}
                          />
                        )}
                      />
                      <Bar dataKey="value" maxBarSize={28} radius={[4, 4, 0, 0]} {...chartAnimation}>
                        {invoiceProjection.map((item, index) => (
                          <Cell key={item.key} fill={SERIES[1]} fillOpacity={index === 0 ? 1 : 0.35} />
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
                  <AlertMessage tone="info">
                    <p className="font-semibold">{nextInvoiceItems.length} lançamento(s) em aberto</p>
                    <p className="mt-1 font-normal">O pagamento lança uma despesa na conta e baixa os itens da fatura.</p>
                  </AlertMessage>

                  <ul className="max-h-56 flex-1 divide-y divide-zinc-100 overflow-y-auto rounded-lg border border-zinc-200">
                    {nextInvoiceItems.map((item) => (
                      <li key={item.id} className="flex items-center justify-between gap-3 px-3 py-2">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-zinc-900">{item.description}</p>
                          <p className="truncate text-xs text-zinc-500">
                            {item.card_name || item.credit_cards?.name || 'Cartão'}
                            {item.installment_info && item.installment_info !== '1/1' ? ` · ${item.installment_info}` : ''}
                          </p>
                        </div>
                        <span className="whitespace-nowrap text-sm font-semibold text-zinc-950">
                          {formatCurrency(item.amount)}
                        </span>
                      </li>
                    ))}
                  </ul>

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

      <div className="stagger grid grid-cols-1 gap-5 xl:grid-cols-5">
        <Panel className="xl:col-span-3">
          <PanelHeader
            title="Ritmo de gastos"
            description={`Gasto acumulado dia a dia (conta corrente e compras no cartão), contra a média dos ${PACE_MONTHS} meses anteriores no mesmo dia do mês.`}
            actions={(
              <div className="text-right">
                <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Até hoje</p>
                <div className="flex items-center justify-end gap-2">
                  <DeltaBadge value={spendingVsAverage} inverse />
                  <p className="text-lg font-bold tabular text-zinc-950">{formatCurrency(spendingPace.currentToDate)}</p>
                </div>
              </div>
            )}
          />
          <div className="p-5">
            {currentSpending.total > 0 || paceMonths > 0 ? (
              <>
                {paceMonths > 0 ? (
                  <>
                    <p className="mb-3 text-sm text-zinc-600">
                      {Math.abs(paceDifference) < 0.005 ? (
                        <span className="font-semibold text-zinc-950">Na média</span>
                      ) : (
                        <span className={cx('font-semibold tabular', paceDifference > 0 ? 'text-rose-600' : 'text-emerald-700')}>
                          {formatCurrency(Math.abs(paceDifference))} {paceDifference > 0 ? 'acima' : 'abaixo'}
                        </span>
                      )}
                      {' '}do que você costuma gastar até o dia {spendingPace.todayDay}.
                      {' '}Um mês inteiro fecha, em média, em <span className="tabular">{formatCurrency(spendingPace.averageMonth)}</span>.
                    </p>
                    <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                      <InlineStat label={`${paceAverageLabel} até o dia ${spendingPace.todayDay}`} value={formatCurrency(spendingPace.averageToDate)} />
                      {paceMonths > 1 ? spendingPace.months.map((month) => (
                        <InlineStat key={month.key} label={`${shortMonth(month.key)} até o dia ${spendingPace.todayDay}`} value={formatCurrency(month.toDate)} />
                      )) : null}
                    </div>
                  </>
                ) : null}
                <div className="mb-3 flex flex-wrap gap-4">
                  <LegendDot color={SERIES[0]} label={`Este mês (${shortMonth(currentKey)})`} shape="line" />
                  {paceMonths > 0 ? <LegendDot color={OTHER_COLOR} label={paceAverageLabel} shape="line" /> : null}
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
                            names={{ current: 'Este mês', average: paceAverageLabel }}
                            labelFormatter={(day) => `Dia ${day}`}
                          />
                        )}
                      />
                      <Line
                        type="monotone"
                        dataKey="average"
                        stroke={OTHER_COLOR}
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4, strokeWidth: 2, stroke: 'rgb(var(--white))' }}
                        connectNulls={false}
                        {...chartAnimation}
                      />
                      <Line
                        type="monotone"
                        dataKey="current"
                        stroke={SERIES[0]}
                        strokeWidth={2.5}
                        dot={false}
                        activeDot={{ r: 5, strokeWidth: 2, stroke: 'rgb(var(--white))' }}
                        connectNulls={false}
                        {...chartAnimation}
                        animationBegin={80}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </>
            ) : (
              <EmptyState icon={Receipt} title="Nenhum gasto registrado" message="O ritmo aparece com os primeiros gastos deste mês ou dos anteriores." />
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
                      activeDot={{ r: 5, strokeWidth: 2, stroke: 'rgb(var(--white))' }}
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
    </div>
  )
}

// Bloco do saldo (direcao C): o numero que se abre o app para ver, o movimento
// do mes e as contas. So a area bancaria — a carteira fica em Investimentos,
// para o numero daqui ser o dinheiro que existe nas contas. Saldo e contas
// somem no modo privado; receitas, despesas, aportes e resgates do mes vem dos
// lancamentos, que ficam visiveis (lib/privacy.js).
function BalanceHero({ total, accounts, monthName, result, income, expense, invested, redeemed, className = '' }) {
  const hidden = useValuesHidden()
  const privateMoney = usePrivateFormatter(formatCurrency)

  return (
    <section
      aria-labelledby="saldo-em-conta"
      className={cx('flex min-w-0 flex-col gap-5 rounded-[1.75rem] bg-brand p-5 text-brand-ink sm:p-8', className)}
    >
      <div className="flex items-center gap-3">
        <h2 id="saldo-em-conta" className="flex-1 text-sm font-semibold text-brand-soft">Saldo em conta</h2>
        <span className="rounded-full bg-white/10 px-3 py-1 text-xs font-semibold">{sentenceCase(monthName)}</span>
      </div>

      <FitValue
        measure={hidden ? MASKED_CURRENCY : formatCurrency(total)}
        baseSize={56}
        minSize={30}
        className="font-extrabold tracking-tight"
      >
        <AnimatedNumber value={total} format={formatCurrency} masked={hidden} cacheKey="inicio|saldo" />
      </FitValue>

      <div className="flex flex-wrap gap-2">
        {/* O movimento do mes some com o olho (decisao 9): ao lado do saldo ele
            diz quanto o saldo andou. A cor sai junto, senao o sinal vaza. */}
        <span
          className={cx(
            'rounded-full px-3 py-1.5 text-sm font-bold tabular',
            hidden ? 'bg-white/10' : result >= 0 ? 'bg-emerald-400 text-on-accent' : 'bg-rose-200 text-rose-950'
          )}
        >
          {hidden ? MASKED_CURRENCY : formatSignedCurrency(result)} no mês
        </span>
        <span className="rounded-full bg-white/10 px-3 py-1.5 text-sm font-semibold tabular">Receitas {formatCurrency(income)}</span>
        <span className="rounded-full bg-white/10 px-3 py-1.5 text-sm font-semibold tabular">Despesas {formatCurrency(expense)}</span>
        {invested > 0 ? (
          <span className="rounded-full bg-white/10 px-3 py-1.5 text-sm font-semibold tabular">Aportes {formatCurrency(invested)}</span>
        ) : null}
        {redeemed > 0 ? (
          <span className="rounded-full bg-white/10 px-3 py-1.5 text-sm font-semibold tabular">Resgates {formatCurrency(redeemed)}</span>
        ) : null}
      </div>

      {accounts.length > 0 ? (
        <ul className="grid grid-cols-2 gap-2 sm:grid-cols-[repeat(auto-fit,minmax(10rem,1fr))]">
          {accounts.map((account) => {
            // Tudo em reais: a conta em moeda estrangeira aparece pelo valor
            // convertido, o mesmo que o total acima soma. Sem cambio hoje ela
            // fica fora do total, e o cartao diz isso.
            const balance = accountBalanceBrl(account)
            return (
              <li key={account.id} className="min-w-0 rounded-2xl bg-white/[0.08] px-4 py-3">
                <p className="truncate text-xs font-medium text-brand-soft" title={account.name}>{account.name}</p>
                {balance === null ? (
                  <p className="mt-0.5 whitespace-nowrap text-sm font-medium text-brand-soft">sem câmbio hoje</p>
                ) : (
                  <p className={cx('mt-0.5 whitespace-nowrap text-[15px] font-bold tabular', balance < 0 && 'text-rose-200')}>
                    {privateMoney(balance)}
                  </p>
                )}
              </li>
            )
          })}
        </ul>
      ) : null}
    </section>
  )
}

// "setembro de 2026" -> "Setembro de 2026" (o capitalize do CSS pega o "De").
const sentenceCase = (text = '') => text.charAt(0).toUpperCase() + text.slice(1)

function DailyTile({ value, day, daysLeft }) {
  const privateMoney = usePrivateFormatter(formatCurrency)
  return (
    <Panel className="flex flex-col justify-between gap-4 p-5 sm:p-6">
      <div>
        <p className="text-sm font-semibold text-zinc-600">Disponível por dia</p>
        <p className={cx('mt-1 whitespace-nowrap text-3xl font-extrabold tracking-tight tabular', value < 0 ? 'text-rose-600' : 'text-zinc-950')}>
          {privateMoney(value)}
        </p>
        <p className="mt-1 text-sm text-zinc-500">Saldo menos a próxima fatura, por {daysLeft} dia(s)</p>
      </div>
      <MonthProgress day={day} daysLeft={daysLeft} />
    </Panel>
  )
}

function NextInvoiceTile({ total, closingDate, payable, label }) {
  return (
    <Panel as={Link} to="/lancamentos/cartoes" interactive className="flex items-center gap-4 p-5 sm:p-6">
      <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-emerald-100 text-emerald-800">
        <CreditCard className="h-5 w-5" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-zinc-600">Fatura de {label}</p>
        <p className="mt-0.5 whitespace-nowrap text-2xl font-extrabold tracking-tight tabular text-zinc-950">{formatCurrency(total)}</p>
      </div>
      <div className="shrink-0 text-right text-sm text-zinc-600">
        {payable ? (
          <Badge tone="warning">Fechada</Badge>
        ) : closingDate ? (
          <>fecha<br /><b className="text-zinc-950 tabular">{formatDateBR(closingDate).slice(0, 5)}</b></>
        ) : null}
      </div>
    </Panel>
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
        const color = index < 5 || sorted.length <= 6 ? SERIES[index] : OTHER_COLOR
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

// Faixa do orcamento do mes: total gasto contra o planejado e as categorias que
// pedem atencao. Sem orcamento no mes, nao aparece.
function BudgetStrip({ budget }) {
  const items = budget?.items || []
  if (items.length === 0) return null

  const totals = budget.totals || {}
  const available = Number(totals.available) || 0
  const spent = Number(totals.spent) || 0
  const remaining = Number(totals.remaining) || 0
  const status = budgetStatus(spent, available)
  const percent = available > 0 ? (spent / available) * 100 : 0
  const statusRank = { OVER: 0, WARNING: 1, OK: 2 }
  const flagged = items
    .filter((item) => item.status !== 'OK')
    .sort((a, b) => statusRank[a.status] - statusRank[b.status] || b.percent - a.percent)
  const shown = flagged.slice(0, 4)
  const categoryName = (item) => (item.parent_name ? `${item.parent_name} › ${item.category_name}` : item.category_name)

  return (
    <Panel className="animate-fade-up">
      <PanelHeader
        title={<PanelLink to="/planejamento/orcamento">Orçamento do mês</PanelLink>}
        description="Gasto nas categorias com orçamento, contra o planejado (sobras acumuladas incluídas)."
        actions={<Badge tone={BUDGET_STATUS_TONES[status]}>{BUDGET_STATUS_LABELS[status]}</Badge>}
      />
      <div className="grid grid-cols-1 gap-5 p-5 lg:grid-cols-2">
        <div className="min-w-0">
          <p className="text-sm text-zinc-600">
            <span className="text-xl font-bold tabular text-zinc-950">{formatCurrency(spent)}</span>
            {' '}de <span className="tabular">{formatCurrency(available)}</span>
          </p>
          <BudgetProgressBar percent={percent} status={status} className="mt-3 h-2.5" />
          <p className={cx('mt-2 text-sm font-semibold tabular', remaining < 0 ? 'text-rose-600' : 'text-zinc-700')}>
            {remaining < 0 ? `Passou ${formatCurrency(-remaining)} do planejado` : `Restam ${formatCurrency(remaining)}`}
          </p>
        </div>
        {shown.length > 0 ? (
          <ul className="min-w-0 space-y-3">
            {shown.map((item) => (
              <li key={item.id}>
                <div className="flex items-center justify-between gap-3 text-sm">
                  <span className="truncate font-medium text-zinc-700" title={categoryName(item)}>{categoryName(item)}</span>
                  <span className="shrink-0 tabular text-zinc-600">
                    <span className={cx('font-semibold', item.status === 'OVER' ? 'text-rose-600' : 'text-zinc-950')}>
                      {formatCurrency(item.spent)}
                    </span>
                    {' '}/ {formatCurrency(item.available)}
                  </span>
                </div>
                <BudgetProgressBar percent={item.percent} status={item.status} className="mt-1.5 h-1.5" />
              </li>
            ))}
            {flagged.length > shown.length ? (
              <li className="text-sm text-zinc-500">
                <Link to="/planejamento/orcamento" className="underline-offset-2 hover:text-emerald-700 hover:underline">
                  +{flagged.length - shown.length} categoria(s) perto do limite ou acima
                </Link>
              </li>
            ) : null}
          </ul>
        ) : (
          <p className="flex items-center gap-2 self-center text-sm text-zinc-600">
            <Target className="h-4 w-4 shrink-0 text-zinc-400" />
            {items.length === 1 ? 'A categoria com orçamento está no plano.' : `As ${items.length} categorias com orçamento estão no plano.`}
          </p>
        )}
      </div>
    </Panel>
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
      className="group -my-2.5 inline-flex items-center gap-1 rounded-sm py-2.5 text-zinc-950 transition-colors hover:text-emerald-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2"
    >
      {children}
      <ChevronRight
        aria-hidden="true"
        className="h-4 w-4 text-zinc-400 transition-transform group-hover:translate-x-0.5 group-hover:text-emerald-600"
      />
    </Link>
  )
}

// "Precisa de atencao": so aparece quando ha algo a fazer. Um cartao por
// item, cada um com a sua acao; nenhum item e calculado aqui — todos vem do
// que o painel ja carrega.
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
  budget,
  payableTotal = 0,
  onPayPayable,
}) {
  // Saldo da conta (e o que falta, que o revela) somem no modo privado.
  const privateMoney = usePrivateFormatter(formatCurrency)
  const overBudget = (budget?.items || [])
    .filter((item) => item.status === 'OVER')
    .sort((a, b) => (b.spent - b.available) - (a.spent - a.available))
  const hasRecurring = pendingRecurringCount > 0
  const hasInvoice = invoiceItemCount > 0 && invoiceAmount > 0
  const hasPayable = !hasInvoice && payableTotal > 0
  const count = (hasRecurring ? 1 : 0) + (hasInvoice ? 1 : 0) + (hasPayable ? 1 : 0) + autopayShortfalls.length + overBudget.length
  if (count === 0) return null
  const categoryName = (item) => (item.parent_name ? `${item.parent_name} › ${item.category_name}` : item.category_name)

  return (
    <section aria-labelledby="precisa-de-atencao" className="animate-fade-up">
      <h2 id="precisa-de-atencao" className="mb-3 flex items-center gap-2 text-sm font-semibold text-zinc-600">
        <BellRing className="h-4 w-4" />
        Precisa de atenção · {count}
      </h2>
      <ul className="stagger grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {hasInvoice ? (
          <AttentionItem
            tone="danger"
            icon={CreditCard}
            title={`Fatura vencida: ${formatCurrency(invoiceAmount)}`}
            detail={`${invoiceDetail} · ${invoiceItemCount} lançamento(s)`}
            action={<Button type="button" size="sm" icon={CheckCircle2} loading={isPayingInvoice} onClick={onPayInvoice}>Pagar</Button>}
          />
        ) : null}
        {hasPayable ? (
          <AttentionItem
            tone="warning"
            icon={CreditCard}
            title={`Fatura fechada: ${formatCurrency(payableTotal)}`}
            detail="O pagamento já está liberado."
            action={<Button type="button" size="sm" icon={CheckCircle2} loading={isPayingInvoice} onClick={onPayPayable}>Pagar</Button>}
          />
        ) : null}
        {autopayShortfalls.map((entry) => (
          <AttentionItem
            key={entry.accountId}
            tone="danger"
            icon={Wallet}
            title={`Débito automático sem saldo: faltam ${privateMoney(entry.missing)}`}
            detail={`${entry.accountName} tem ${privateMoney(entry.balance)} para ${formatCurrency(entry.total)} a debitar · o primeiro em ${formatDateBR(entry.firstDue)}`}
            action={<AttentionLink to="/lancamentos/cartoes">Ver faturas</AttentionLink>}
          />
        ))}
        {hasRecurring ? (
          <AttentionItem
            tone="info"
            icon={Repeat}
            title={`${pendingRecurringCount} ${pendingRecurringCount === 1 ? 'recorrência vencida' : 'recorrências vencidas'}`}
            detail={<AttentionLink to="/planejamento/recorrentes">Ver recorrentes</AttentionLink>}
            action={<Button type="button" size="sm" icon={Repeat} loading={isRunningRecurring} onClick={onRunRecurring}>Lançar</Button>}
          />
        ) : null}
        {overBudget.map((item) => (
          <AttentionItem
            key={item.id}
            tone="warning"
            icon={Target}
            title={`${categoryName(item)} passou do orçamento`}
            detail={`${formatCurrency(item.spent)} de ${formatCurrency(item.available)}`}
            action={<AttentionLink to="/planejamento/orcamento">Ver orçamento</AttentionLink>}
          />
        ))}
      </ul>
    </section>
  )
}

const attentionTones = {
  danger: 'bg-rose-100 text-rose-700',
  warning: 'bg-amber-100 text-amber-800',
  info: 'bg-sky-100 text-sky-700',
}

function AttentionItem({ icon: Icon, title, detail, action, tone = 'warning' }) {
  return (
    <li className="flex min-w-0 flex-col gap-3 rounded-[1.25rem] border border-zinc-200/60 bg-white p-4">
      <span className={cx('flex h-9 w-9 items-center justify-center rounded-xl', attentionTones[tone])}>
        <Icon className="h-4 w-4" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-bold text-zinc-950">{title}</p>
        <div className="mt-1 text-sm text-zinc-600">{detail}</div>
      </div>
      <div>{action}</div>
    </li>
  )
}

function AttentionLink({ to, children }) {
  return (
    <Link to={to} className="inline-flex min-h-11 items-center gap-1 text-sm font-bold text-emerald-700 lg:min-h-9 underline-offset-2 hover:underline">
      {children}
      <ChevronRight className="h-4 w-4" aria-hidden="true" />
    </Link>
  )
}

// Tooltip do fluxo de caixa. As saidas sao desenhadas abaixo do zero e aparecem
// em modulo; o resultado mantem o sinal. A serie de investimento e liquida:
// abaixo do zero o mes investiu, acima resgatou, e o rotulo diz qual dos dois.
function FlowTooltip({ payload, ...props }) {
  const rows = payload?.map((item) => {
    if (item.dataKey === 'net' || item.value === null || item.value === undefined) return item
    const redeemed = item.dataKey === 'investment' && item.value > 0
    return { ...item, dataKey: redeemed ? 'redeemed' : item.dataKey, value: Math.abs(Number(item.value)) }
  })
  return (
    <ChartTooltip
      {...props}
      payload={rows}
      names={{ income: 'Receitas', expense: 'Despesas', investment: 'Investido', redeemed: 'Resgatado', net: 'Resultado' }}
      labelFormatter={(_, items) => monthLabel(items?.[0]?.payload?.key)}
    />
  )
}

function InlineStat({ label, value, valueClassName = 'text-zinc-950', className = '' }) {
  return (
    <div className={cx('rounded-lg border border-zinc-200/80 bg-zinc-50/60 px-3 py-2.5', className)}>
      <p className="text-xs font-semibold leading-4 text-zinc-500">{label}</p>
      <FitValue measure={value} baseSize={16} minSize={12} className={cx('mt-1 font-bold', valueClassName)}>{value}</FitValue>
    </div>
  )
}
