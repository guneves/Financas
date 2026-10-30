import { useEffect, useMemo, useState, useSyncExternalStore } from 'react'
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
  Globe2,
  CreditCard,
  LineChart as LineChartIcon,
  ListChecks,
  Receipt,
  Repeat,
  Target,
  X,
} from 'lucide-react'
import { ccExpensesApi, recurringApi } from '../lib/dataApi'
import { dismissAttention, useAttentionItems, useDismissedAttention, useHome, useInicioBudget, useInicioMovements } from '../lib/attention'
import { invoiceMonthKey, isPastDue, overdueDetail as overdueDetailOf, undismissedItems } from '../lib/attentionRules'
import { AttentionCards } from '../components/Attention'
import { useOutbox } from '../lib/outbox'
import { ACCOUNT_KINDS, PENDING, pendingAsTransactions } from '../lib/outboxRules'
import { invalidateServerData, queryErrorMessage } from '../lib/queries'
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
  IconButton,
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
import { accountBalanceBrl, activeAccounts, bankingAccounts, blockedRecurringMessage, bankingTransactions, cardPurchaseKey, cardSignedAmount, isCardRefund, isInvestmentOutflow, isInvoicePayment } from '../lib/transactions'
import { toast } from '../lib/toast'
import { GLOBAL_ACCOUNT_LABEL, globalAccounts, withoutGlobal } from '../lib/globalAccount'
import { ownAmount } from '../lib/sharing'
import { flowPoint, flowSummary as flowSummaryOf, savingsRateText } from '../lib/homeFlow'

const INVOICE_MONTHS = 6
// Meses anteriores que formam a media do "Ritmo de gastos".
const PACE_MONTHS = 3

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

const shortMonth = shortMonthLabel

const percentChange = (current, previous) => {
  if (!previous) return null
  return ((current - previous) / Math.abs(previous)) * 100
}

// Gasto de consumo de um mes, por dia e por categoria: saidas da conta (menos
// o pagamento de fatura, que ja e a soma das compras, e os aportes em
// investimento) + compras no cartao pelo valor total da compra, na data da compra.
// So a parte do dono (lib/sharing.js): o que era de outra pessoa nao e gasto dele.
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
    const own = ownAmount(transaction)
    if (own > 0) add(Number(transaction.date.slice(8, 10)), transaction.category, 'cash', own)
  })

  const purchases = {}
  ccExpenses.forEach((expense) => {
    if (String(expense.purchase_date || '').slice(0, 7) !== key) return
    const groupKey = cardPurchaseKey(expense)
    if (!purchases[groupKey]) {
      purchases[groupKey] = { day: Number(expense.purchase_date.slice(8, 10)), category: expense.category, amount: 0 }
    }
    // O estorno (033) abate a categoria no dia dele.
    purchases[groupKey].amount += isCardRefund(expense) ? cardSignedAmount(expense) : ownAmount(expense)
  })
  Object.values(purchases).forEach((purchase) => {
    if (purchase.amount !== 0) add(purchase.day, purchase.category, 'credit', purchase.amount)
  })

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

  // Queries independentes: uma que falha nao derruba as outras. O saldo, o
  // fluxo e a proxima fatura vem de /api/home e os avisos de /api/attention,
  // somados no servidor; o historico (movimentacoes) so alimenta os paineis
  // que ainda o leem aqui (categorias, ritmo, parcelamentos, projecao).
  const homeQuery = useHome()
  // Todas as compras do cartao, nao so as abertas: o ritmo de gastos do mes
  // passado precisa das compras que ja foram pagas.
  const movementsQuery = useInicioMovements()
  // Orcamento do mes para a faixa de orcamento.
  const budgetMonth = monthKey(new Date())
  const budgetQuery = useInicioBudget(budgetMonth)
  // "Precisa de atencao", o mesmo pedido do sino do cabecalho.
  const attention = useAttentionItems()
  const dismissedAttention = useDismissedAttention()

  // Lancamentos guardados no aparelho, ainda sem chegar ao servidor
  // (lib/outbox.js): entram nas contas e no mes (applyPendingToHome, em
  // useHome) e nos paineis como em Lancamentos, e o saldo fica marcado como
  // estimativa. O saldo e o historico leem os mesmos pendentes, entao a curva
  // continua terminando no saldo do topo.
  const pending = useOutbox()
  const home = homeQuery.data
  const serverTransactions = movementsQuery.data?.transactions || NO_ITEMS
  const serverAccounts = movementsQuery.data?.allAccounts || NO_ITEMS
  // Vistos da area bancaria (bankingTransactions): a conta Corretora fica de
  // fora, e a transferencia para ela e um aporte.
  const transactions = useMemo(() => {
    const waiting = pending.filter((item) => item.status === PENDING)
    const defaultAccountId = serverAccounts.find((account) => account.is_default)?.id || ''
    const all = waiting.length ? [...pendingAsTransactions(waiting, { defaultAccountId }), ...serverTransactions] : serverTransactions
    return bankingTransactions(all, serverAccounts)
  }, [serverTransactions, serverAccounts, pending])
  const ccExpenses = movementsQuery.data?.ccExpenses || NO_ITEMS
  const pendingInBalance = useMemo(
    // Compra no cartao, operacao e provento pendentes nao mexem em conta.
    () => pending.filter((item) => item.status === PENDING && ACCOUNT_KINDS.includes(item.kind)).length,
    [pending]
  )
  const budget = budgetQuery.data || null

  useEffect(() => {
    const failed = homeQuery.error ? homeQuery : movementsQuery.error ? movementsQuery : null
    if (failed) {
      console.warn('Erro ao buscar movimentações:', failed.error)
      setDataError(queryErrorMessage(failed, 'Não foi possível carregar movimentações e faturas.'))
    }
  }, [homeQuery.error, movementsQuery.error])

  const fetchAllData = () => invalidateServerData()

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
      if (result?.blocked?.length) setDataError(blockedRecurringMessage(result.blocked))
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
  const todayText = getLocalDateString(today)

  const openCcExpenses = useMemo(() => ccExpenses.filter((expense) => expense.status === 'OPEN'), [ccExpenses])

  // Todas as contas de /api/home (arquivadas inclusive), com os pendentes.
  const allAccounts = home?.accounts || NO_ITEMS
  const accounts = useMemo(() => activeAccounts(allAccounts), [allAccounts])
  // Saldo em contas: a soma do servidor, sem a Corretora (services/home.py).
  const bankBalance = home?.consolidated_balance || 0

  // Entradas, saidas e saldo de fim de mes dos ultimos 12 meses (services/home.py).
  // Cada gasto entra no dia em que acontece — a compra no cartao no mes da
  // compra, nao no pagamento da fatura. Investimento e o que era de outra
  // pessoa ficam a parte; o saldo e o das contas de verdade.
  const monthlyHistory = useMemo(() => (home?.flow || NO_ITEMS).map(flowPoint), [home])

  // As medias e a taxa de poupanca (lib/homeFlow.js, testada; o par nativo e
  // rules/HomeFlow.kt).
  const flowSummary = useMemo(() => flowSummaryOf(monthlyHistory), [monthlyHistory])

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

  // A proxima fatura de cada cartao: a que vence primeiro, de hoje em diante
  // (services/card_invoices.py) — a mesma regra do sino e da tela Cartoes. "A
  // fatura do mes que vem" deixava de fora quem fecha antes de vencer no mesmo
  // mes (fecha 3, vence 10): a de novembro, fechada, so aparecia vencida.
  const nextInvoices = home?.next_invoices || NO_ITEMS
  // As compras delas, na ordem das faturas, para a lista do painel.
  const nextInvoiceItems = useMemo(() => nextInvoices.flatMap((invoice) => openCcExpenses.filter((item) => (
    item.card_id === invoice.card_id && item.invoice_month === invoice.invoice_month && item.invoice_year === invoice.invoice_year
  ))), [nextInvoices, openCcExpenses])
  const nextInvoiceTotal = home?.next_invoices_total || 0
  // Os meses delas: com cartoes de ciclos diferentes, pode ser mais de um.
  const nextInvoiceMonths = useMemo(() => [...new Set(nextInvoices.map(invoiceMonthKey))].sort(), [nextInvoices])

  // So fatura fechada pode ser paga (o servidor recusa as outras). Uma por
  // cartao: cada uma vira um pagamento proprio.
  const payableInvoices = useMemo(() => nextInvoices
    .filter((invoice) => invoice.payable)
    .map(({ card_id, invoice_month, invoice_year, total }) => ({ card_id, invoice_month, invoice_year, total })), [nextInvoices])

  const payableTotal = payableInvoices.reduce((acc, invoice) => acc + invoice.total, 0)

  // "Precisa de atencao" so cobra fatura vencida: passou do dia do vencimento
  // e continua em aberto (services/attention.py).
  const overdueItem = attention.find((item) => item.kind === 'INVOICE_OVERDUE')
  const overdueInvoices = overdueItem?.invoices || NO_ITEMS
  const overdueTotal = overdueItem?.total || 0
  const overdueDetail = overdueDetailOf(overdueInvoices)

  const shownAttention = useMemo(() => undismissedItems(attention, dismissedAttention), [attention, dismissedAttention])

  const nextClosingDate = home?.next_closing_date || null

  // Quanto ja esta comprometido nas proximas faturas, por mes de fatura, a
  // partir do mes da primeira delas. A vencida fica fora: ela e o aviso de
  // fatura vencida. Em destaque, os meses das proximas faturas.
  const invoiceProjection = useMemo(() => {
    const keys = Array.from({ length: INVOICE_MONTHS }, (_, index) => shiftMonth(nextInvoiceMonths[0] || currentKey, index))
    const byKey = Object.fromEntries(keys.map((key) => [key, 0]))
    openCcExpenses.forEach((expense) => {
      if (isPastDue(expense.invoice_due_date, todayText)) return
      const key = invoiceMonthKey(expense)
      if (key in byKey) byKey[key] += cardSignedAmount(expense)
    })
    return keys.map((key) => ({
      key,
      label: shortMonth(key),
      value: Number(byKey[key].toFixed(2)),
      next: nextInvoiceMonths.includes(key),
    }))
  }, [openCcExpenses, nextInvoiceMonths, currentKey, todayText])

  const groupedInstallmentExpenses = useMemo(() => {
    const grouped = openCcExpenses.reduce((acc, expense) => {
      const installment = parseInstallmentInfo(expense.installment_info)
      if (installment.total <= 1) return acc

      // A compra e o client_id (lib/transactions.js): duas compras parceladas
      // iguais sao dois parcelamentos.
      const key = cardPurchaseKey(expense)

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
      title: payableInvoices.length === 1 ? 'Pagar fatura' : 'Pagar faturas',
      description: payableInvoices.length === 1
        ? 'A fatura fechada que vence a seguir.'
        : `${payableInvoices.length} faturas fechadas, a próxima de cada cartão.`,
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
  if (homeQuery.isPending || movementsQuery.isPending) {
    return <DashboardSkeleton />
  }

  const paceMonths = spendingPace.months.length
  const paceDifference = spendingPace.currentToDate - spendingPace.averageToDate
  const spendingVsAverage = paceMonths > 0 ? percentChange(spendingPace.currentToDate, spendingPace.averageToDate) : null
  const paceAverageLabel = paceMonths > 1 ? `Média de ${paceMonths} meses` : `Mês de ${shortMonth(spendingPace.months[0]?.key)}`
  // O mes atual do fluxo de caixa (o cartao no dia da compra). Aporte,
  // resgate e outras pessoas nao sao despesa nem receita do dono e aparecem a
  // parte no "Resumo do mes".
  const summary = home?.summary || { income: 0, expense: 0, invested: 0, redeemed: 0, others_net: 0 }

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
          accounts={bankingAccounts(accounts)}
          monthName={monthLabel(currentKey)}
        />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-5 xl:col-span-4 xl:grid-cols-1">
          <MonthSummary
            income={summary.income}
            expense={summary.expense}
            invested={summary.invested}
            redeemed={summary.redeemed}
            others={summary.others_net}
          />
          <NextInvoiceTile
            total={nextInvoiceTotal}
            closingDate={nextClosingDate}
            payable={payableInvoices.length > 0}
            label={nextInvoiceMonths.length === 1
              ? `Fatura de ${monthLabel(nextInvoiceMonths[0])}`
              : nextInvoiceMonths.length > 1 ? 'Próximas faturas' : 'Próxima fatura'}
          />
        </div>
      </div>

      <NeedsAttention
        items={shownAttention}
        onRunRecurring={handleRunRecurring}
        isRunningRecurring={isRunningRecurring}
        onPayInvoice={handlePayOverdueInvoices}
        isPayingInvoice={isPayingCurrentInvoice}
        onPayPayable={handlePayCurrentMonthInvoice}
      />

      <div className="stagger grid grid-cols-1 gap-5 xl:grid-cols-5">
        {/* A linha estica os dois paineis ate a altura de "Despesas por
            categoria"; o grafico cresce junto em vez de deixar um vazio embaixo. */}
        <Panel className="flex flex-col xl:col-span-3">
          <PanelHeader
            title={<PanelLink to="/lancamentos/extrato">Fluxo de caixa</PanelLink>}
            description={[
              flowSummary.hasInvestment
                ? 'Receitas, despesas e investimentos (aportes menos resgates) dos últimos 12 meses.'
                : 'Receitas e despesas dos últimos 12 meses.',
              'Compras no cartão entram no mês da compra; pagamento de fatura e transferências entre contas não entram.',
              flowSummary.hasOthers ? 'O que foi de outras pessoas fica à parte.' : '',
            ].filter(Boolean).join(' ')}
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
                    value={savingsRateText(flowSummary.savingsRate)}
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
                  {flowSummary.hasOthers ? <LegendDot color={FLOW.others} label="Outras pessoas" /> : null}
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
                      {flowSummary.hasOthers ? (
                        <Bar dataKey="others" stackId="flow" fill={FLOW.others} maxBarSize={24} radius={[4, 4, 0, 0]} {...chartAnimation} />
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
                {formatCurrency(nextInvoiceTotal)}
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
                        {invoiceProjection.map((item) => (
                          <Cell key={item.key} fill={SERIES[1]} fillOpacity={item.next ? 1 : 0.35} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <EmptyState icon={CreditCard} title="Nada comprometido" message="Sem compras abertas nos próximos meses." className="h-60 min-h-0" />
              )}
              {nextInvoiceMonths.length ? (
                <p className="mt-2 text-xs text-zinc-600">
                  {nextInvoiceMonths.length === 1
                    ? `Em destaque, a fatura de ${monthLabel(nextInvoiceMonths[0])}.`
                    : 'Em destaque, a próxima fatura de cada cartão.'}
                </p>
              ) : null}
            </div>

            <div className="flex flex-col">
              {nextInvoiceTotal > 0 ? (
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

// Bloco do saldo (direcao C): o numero que se abre o app para ver e as
// contas. So a area bancaria — a carteira fica em Investimentos, para o numero
// daqui ser o dinheiro que existe nas contas. O movimento do mes fica no
// "Resumo do mes", ao lado. Saldo e contas somem no modo privado.
function BalanceHero({ total, accounts, monthName, className = '' }) {
  const hidden = useValuesHidden()
  const privateMoney = usePrivateFormatter(formatCurrency)
  const wide = useIsSm()
  // A conta global nao e "Saldo em conta": so a entrada "Conta global" abaixo.
  const listed = withoutGlobal(accounts)

  // No celular o bloco e a primeira coisa que se ve ao abrir o app: numero
  // menor e as contas numa faixa que rola de lado, para o resto de Inicio
  // aparecer sem rolar.
  return (
    <section
      aria-labelledby="saldo-em-conta"
      className={cx('flex min-w-0 flex-col gap-3 rounded-3xl bg-brand p-4 text-brand-ink sm:gap-5 sm:rounded-[1.75rem] sm:p-8', className)}
    >
      <div className="flex items-center gap-3">
        <h2 id="saldo-em-conta" className="flex-1 text-sm font-semibold text-brand-soft">Saldo em conta</h2>
        <span className="rounded-full bg-white/10 px-2.5 py-0.5 text-xs font-semibold sm:px-3 sm:py-1">{sentenceCase(monthName)}</span>
      </div>

      <FitValue
        measure={hidden ? MASKED_CURRENCY : formatCurrency(total)}
        baseSize={wide ? 56 : 38}
        minSize={wide ? 30 : 24}
        className="font-extrabold tracking-tight"
      >
        <AnimatedNumber value={total} format={formatCurrency} masked={hidden} cacheKey="inicio|saldo" />
      </FitValue>

      {/* mt-auto: no desktop o bloco estica ate a altura do "Resumo do mes" e
          as contas descem para o pe dele.
          scroll-px-4: o snap alinha cada conta a borda da area de snap, que
          ignora o padding; sem ele a primeira conta "encaixa" em 16 px e a
          faixa abre rolada, colada na borda do bloco. */}
      {listed.length > 0 ? (
        <ul className="-mx-4 mt-auto flex snap-x scroll-px-4 gap-2 overflow-x-auto px-4 [scrollbar-width:none] sm:mx-0 sm:grid sm:grid-cols-[repeat(auto-fit,minmax(10rem,1fr))] sm:overflow-visible sm:px-0">
          {listed.map((account) => {
            const balance = accountBalanceBrl(account)
            return (
              <li key={account.id} className="min-w-[8.5rem] max-w-[60%] shrink-0 snap-start rounded-2xl bg-white/[0.08] px-3 py-2 sm:min-w-0 sm:max-w-none sm:px-4 sm:py-3">
                <p className="truncate text-xs font-medium text-brand-soft" title={account.name}>{account.name}</p>
                {balance === null ? (
                  <p className="mt-0.5 whitespace-nowrap text-sm font-medium text-brand-soft">sem câmbio hoje</p>
                ) : (
                  <p className={cx('mt-0.5 whitespace-nowrap text-sm font-bold tabular sm:text-[15px]', balance < 0 && 'text-rose-200')}>
                    {privateMoney(balance)}
                  </p>
                )}
              </li>
            )
          })}
        </ul>
      ) : null}
      {/* A conta em dolar nao entra no total nem na lista acima: so esta entrada
          e a tela dela (lib/globalAccount.js). */}
      {globalAccounts(accounts).length > 0 ? (
        <Link
          to="/inicio/conta-global"
          className="-my-1 inline-flex min-h-11 items-center gap-1.5 self-start rounded-xl text-sm font-semibold text-brand-soft hover:text-brand-ink"
        >
          <Globe2 className="h-4 w-4" aria-hidden="true" />
          {GLOBAL_ACCOUNT_LABEL}
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </Link>
      ) : null}
    </section>
  )
}

const SM_QUERY = '(min-width: 640px)'

function subscribeSm(onChange) {
  const media = window.matchMedia(SM_QUERY)
  media.addEventListener('change', onChange)
  return () => media.removeEventListener('change', onChange)
}

function useIsSm() {
  return useSyncExternalStore(subscribeSm, () => window.matchMedia(SM_QUERY).matches, () => true)
}

// "setembro de 2026" -> "Setembro de 2026" (o capitalize do CSS pega o "De").
const sentenceCase = (text = '') => text.charAt(0).toUpperCase() + text.slice(1)

// O mes em linhas: rotulo, valor e uma dica. Os numeros sao os do fluxo de
// caixa do mes atual (GET /api/home, `summary`) — receitas e despesas so a parte do
// dono, o cartao no dia da compra. Investido e outras pessoas so aparecem
// quando houve. No modo privado todos os valores somem, e a cor do resultado
// sai junto, senao o sinal vaza.
function MonthSummary({ income, expense, invested, redeemed, others }) {
  const hidden = useValuesHidden()
  const privateMoney = usePrivateFormatter(formatCurrency)
  const result = income - expense
  const rows = [
    {
      label: 'Resultado do mês',
      value: hidden ? MASKED_CURRENCY : formatSignedCurrency(result),
      tone: hidden ? 'text-zinc-950' : result < 0 ? 'text-rose-600' : 'text-emerald-700',
      hint: 'Suas receitas menos suas despesas',
      lead: true,
    },
    { label: 'Entrou', value: privateMoney(income), hint: 'Receitas do mês' },
    { label: 'Saiu', value: privateMoney(expense), hint: 'Despesas e compras no cartão' },
    invested !== 0 || redeemed !== 0
      ? {
          label: 'Investido',
          value: privateMoney(invested - redeemed),
          hint: `Aportes ${privateMoney(invested)} · Resgates ${privateMoney(redeemed)}`,
        }
      : null,
    // Liquido: abaixo do zero o dono pagou mais por elas do que recebeu delas.
    // O rotulo diz o sentido; o valor vai sem sinal.
    others !== 0
      ? {
          label: others < 0 ? 'Você pagou para outras pessoas' : 'Outras pessoas te pagaram',
          value: privateMoney(Math.abs(others)),
          hint: (
            <Link to="/lancamentos/a-receber" className="font-semibold text-emerald-700 underline-offset-2 hover:underline">
              Ver em A receber
            </Link>
          ),
        }
      : null,
  ].filter(Boolean)

  return (
    <Panel className="p-5 sm:p-6">
      <h2 className="text-sm font-semibold text-zinc-600">Resumo do mês</h2>
      <dl className="mt-3 divide-y divide-zinc-100">
        {rows.map((row) => (
          <div key={row.label} className="flex items-baseline justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
            <div className="min-w-0">
              <dt className="text-sm font-semibold text-zinc-950">{row.label}</dt>
              <dd className="mt-0.5 text-xs text-zinc-500">{row.hint}</dd>
            </div>
            <dd
              className={cx(
                'shrink-0 whitespace-nowrap text-right font-bold tabular',
                row.lead ? 'text-xl font-extrabold tracking-tight' : 'text-[15px]',
                row.tone || 'text-zinc-950'
              )}
            >
              {row.value}
            </dd>
          </div>
        ))}
      </dl>
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
        <p className="text-sm font-semibold text-zinc-600">{label}</p>
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
    .filter((item) => item.status === 'OVER' || item.status === 'WARNING')
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
      {/* O saldo, o resumo do mes e a proxima fatura, no lugar de cada um. */}
      <div className="grid grid-cols-1 gap-4 sm:gap-5 xl:grid-cols-12">
        <Skeleton className="h-56 rounded-3xl xl:col-span-8" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-5 xl:col-span-4 xl:grid-cols-1">
          <Skeleton className="h-52" />
          <Skeleton className="h-24" />
        </div>
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
// item, cada um com a sua acao (components/Attention.jsx). O X dispensa os
// avisos de agora neste aparelho: o mesmo caso nao volta aqui, um novo volta,
// e todos continuam no sino do cabecalho.
function NeedsAttention({
  items,
  onRunRecurring,
  isRunningRecurring,
  onPayInvoice,
  isPayingInvoice,
  onPayPayable,
}) {
  if (items.length === 0) return null
  const dismiss = () => {
    dismissAttention(items.map((item) => item.key))
    toast('Avisos dispensados. Eles continuam no sino, no topo da tela.', { tone: 'info' })
  }

  return (
    <section aria-labelledby="precisa-de-atencao" className="animate-fade-up">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 id="precisa-de-atencao" className="flex items-center gap-2 text-sm font-semibold text-zinc-600">
          <BellRing className="h-4 w-4" />
          Precisa de atenção · {items.length}
        </h2>
        <IconButton size="sm" icon={X} label="Dispensar avisos" onClick={dismiss} />
      </div>
      <AttentionCards
        items={items}
        actions={{
          INVOICE_OVERDUE: <Button type="button" size="sm" icon={CheckCircle2} loading={isPayingInvoice} onClick={onPayInvoice}>Pagar</Button>,
          INVOICE_PAYABLE: <Button type="button" size="sm" icon={CheckCircle2} loading={isPayingInvoice} onClick={onPayPayable}>Pagar</Button>,
          RECURRING: <Button type="button" size="sm" icon={Repeat} loading={isRunningRecurring} onClick={onRunRecurring}>Lançar</Button>,
        }}
      />
    </section>
  )
}

// Tooltip do fluxo de caixa. As saidas sao desenhadas abaixo do zero e aparecem
// em modulo; o resultado mantem o sinal. A serie de investimento e liquida:
// abaixo do zero o mes investiu, acima resgatou, e o rotulo diz qual dos dois.
// Outras pessoas tambem e liquida: abaixo do zero o dono pagou mais por elas
// do que recebeu delas.
function FlowTooltip({ payload, ...props }) {
  const rows = payload?.map((item) => {
    if (item.dataKey === 'net' || item.value === null || item.value === undefined) return item
    const redeemed = item.dataKey === 'investment' && item.value > 0
    const othersBack = item.dataKey === 'others' && item.value > 0
    const dataKey = redeemed ? 'redeemed' : othersBack ? 'othersBack' : item.dataKey
    return { ...item, dataKey, value: Math.abs(Number(item.value)) }
  })
  return (
    <ChartTooltip
      {...props}
      payload={rows}
      names={{
        income: 'Receitas',
        expense: 'Despesas',
        investment: 'Investido',
        redeemed: 'Resgatado',
        others: 'Pago por outras pessoas',
        othersBack: 'Recebido de outras pessoas',
        net: 'Resultado',
      }}
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
