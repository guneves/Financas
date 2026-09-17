import { useEffect, useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  AlertTriangle,
  ArrowDownCircle,
  ArrowUpCircle,
  Banknote,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  CreditCard,
  Landmark,
  Plus,
  Receipt,
  RefreshCw,
  Sparkles,
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
import { formatCurrency, formatDateBR } from '../lib/format'

const CATEGORY_OPTIONS = [
  'Receita',
  'Salário',
  'Freelance',
  'Investimento',
  'Alimentação',
  'Moradia',
  'Transporte',
  'Saúde',
  'Educação',
  'Lazer',
  'Serviços',
  'Mercado',
  'Outros',
]

const EXPENSE_CATEGORIES = CATEGORY_OPTIONS.filter((category) => !['Receita', 'Salário', 'Freelance'].includes(category))
const CATEGORY_COLORS = ['#059669', '#0284c7', '#f59e0b', '#e11d48', '#7c3aed', '#52525b', '#14b8a6', '#f97316']
const STORAGE_KEYS = {
  transactions: '@financeMVP:walletTransactions',
  cards: '@financeMVP:walletCards',
  ccExpenses: '@financeMVP:walletCcExpenses',
}

const compactCurrency = (value) => {
  const numeric = Number(value || 0)
  const absolute = Math.abs(numeric)

  if (absolute >= 1000) {
    const formatted = (absolute / 1000).toLocaleString('pt-BR', {
      maximumFractionDigits: absolute >= 10000 ? 0 : 1,
    })
    return `R$ ${numeric < 0 ? '-' : ''}${formatted}K`
  }

  return formatCurrency(numeric)
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

function getNow() {
  return new Date()
}

function getLocalDateString(date = getNow()) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function parseLocalDate(dateString) {
  if (!dateString) return null
  const [year, month, day] = String(dateString).split('-').map(Number)
  if (!year || !month || !day) return null
  return new Date(year, month - 1, day)
}

function formatInvoiceLabel(month, year) {
  return `${String(month).padStart(2, '0')}/${year}`
}

function monthKeyFromDate(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}

function monthLabelFromKey(key) {
  const [year, month] = key.split('-').map(Number)
  return new Date(year, month - 1, 1).toLocaleDateString('pt-BR', {
    month: 'short',
    year: '2-digit',
  })
}

function dateAtDay(day, monthOffset = 0) {
  const today = getNow()
  const base = new Date(today.getFullYear(), today.getMonth() + monthOffset, 1)
  const lastDay = new Date(base.getFullYear(), base.getMonth() + 1, 0).getDate()
  base.setDate(Math.min(Math.max(day, 1), lastDay))
  return getLocalDateString(base)
}

function getDaysRemainingInMonth() {
  const today = getNow()
  const lastDay = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate()
  return Math.max(lastDay - today.getDate() + 1, 1)
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

function isSameTransaction(existing, candidate) {
  return existing.type === candidate.type
    && existing.date === candidate.date
    && existing.description === candidate.description
    && Number(existing.amount || 0).toFixed(2) === Number(candidate.amount || 0).toFixed(2)
}

function isSamePurchase(existing, candidate) {
  return existing.card_id === candidate.card_id
    && existing.description === candidate.description
    && existing.purchase_date === candidate.purchase_date
    && existing.category === candidate.category
}

function buildMockTransactions() {
  return [
    {
      type: 'INCOME',
      amount: 8500,
      date: dateAtDay(1),
      category: 'Salário',
      description: 'Demo - salário mensal',
    },
    {
      type: 'INCOME',
      amount: 1250,
      date: dateAtDay(2),
      category: 'Freelance',
      description: 'Demo - projeto extra',
    },
    {
      type: 'EXPENSE',
      amount: 2250,
      date: dateAtDay(3),
      category: 'Moradia',
      description: 'Demo - aluguel',
    },
    {
      type: 'EXPENSE',
      amount: 486.7,
      date: dateAtDay(4),
      category: 'Mercado',
      description: 'Demo - mercado da semana',
    },
    {
      type: 'EXPENSE',
      amount: 178.9,
      date: dateAtDay(5),
      category: 'Transporte',
      description: 'Demo - combustível',
    },
    {
      type: 'INCOME',
      amount: 8400,
      date: dateAtDay(1, -1),
      category: 'Salário',
      description: 'Demo - salário mês anterior',
    },
    {
      type: 'EXPENSE',
      amount: 2130,
      date: dateAtDay(3, -1),
      category: 'Moradia',
      description: 'Demo - aluguel mês anterior',
    },
  ]
}

const MOCK_CARDS = [
  { name: 'Nubank Demo', due_day: 10, closing_day: 3 },
  { name: 'Inter Demo', due_day: 20, closing_day: 13 },
]

const MOCK_PURCHASES = [
  {
    cardName: 'Nubank Demo',
    category: 'Alimentação',
    description: 'Demo - supermercado no crédito',
    total_amount: 392.45,
    purchase_date: dateAtDay(2),
    installments: 1,
  },
  {
    cardName: 'Nubank Demo',
    category: 'Serviços',
    description: 'Demo - notebook parcelado',
    total_amount: 3600,
    purchase_date: dateAtDay(6),
    installments: 6,
  },
  {
    cardName: 'Inter Demo',
    category: 'Saúde',
    description: 'Demo - academia',
    total_amount: 129.9,
    purchase_date: dateAtDay(8),
    installments: 1,
  },
  {
    cardName: 'Inter Demo',
    category: 'Educação',
    description: 'Demo - curso online',
    total_amount: 900,
    purchase_date: dateAtDay(12),
    installments: 3,
  },
]

export default function Carteira() {
  const [activeTab, setActiveTab] = useState('CONTA')
  const [transactions, setTransactions] = useState(() => readStoredJson(STORAGE_KEYS.transactions, []))
  const [cards, setCards] = useState(() => readStoredJson(STORAGE_KEYS.cards, []))
  const [ccExpenses, setCcExpenses] = useState(() => readStoredJson(STORAGE_KEYS.ccExpenses, []))
  const [dataError, setDataError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(false)
  const [mockLoading, setMockLoading] = useState(false)
  const [expandedCards, setExpandedCards] = useState([])
  const [transForm, setTransForm] = useState({
    amount: '',
    date: getLocalDateString(),
    category: '',
    description: '',
    type: 'EXPENSE',
  })
  const [cardForm, setCardForm] = useState({ name: '', due_day: '', closing_day: '' })
  const [expenseForm, setExpenseForm] = useState({
    card_id: '',
    category: '',
    description: '',
    total_amount: '',
    purchase_date: getLocalDateString(),
    installments: '1',
  })

  useEffect(() => {
    fetchData()
  }, [])

  useEffect(() => {
    if (!expenseForm.card_id && cards[0]?.id) {
      setExpenseForm((current) => ({ ...current, card_id: cards[0].id }))
    }
  }, [cards, expenseForm.card_id])

  const fetchData = async () => {
    setDataError('')

    try {
      const [transactionsData, cardsData, cardExpensesData] = await Promise.all([
        transactionsApi.list(),
        creditCardsApi.list(),
        ccExpensesApi.list(),
      ])

      const safeTransactions = transactionsData || []
      const safeCards = cardsData || []
      const safeCardExpenses = cardExpensesData || []

      setTransactions(safeTransactions)
      setCards(safeCards)
      setCcExpenses(safeCardExpenses)

      localStorage.setItem(STORAGE_KEYS.transactions, JSON.stringify(safeTransactions))
      localStorage.setItem(STORAGE_KEYS.cards, JSON.stringify(safeCards))
      localStorage.setItem(STORAGE_KEYS.ccExpenses, JSON.stringify(safeCardExpenses))
    } catch (error) {
      console.warn('Erro ao carregar carteira:', error)
      setDataError(error.message || 'Não foi possível carregar a carteira.')
    }
  }

  const openCardExpenses = useMemo(() => {
    return ccExpenses.filter((expense) => expense.status !== 'PAID')
  }, [ccExpenses])

  const walletSummary = useMemo(() => {
    const today = getNow()
    const currentMonth = today.getMonth() + 1
    const currentYear = today.getFullYear()

    const totals = transactions.reduce((acc, transaction) => {
      const amount = Number(transaction.amount || 0)
      if (transaction.type === 'INCOME') {
        acc.balance += amount
        acc.income += amount
      } else {
        acc.balance -= amount
        acc.expense += amount
      }

      const date = parseLocalDate(transaction.date)
      if (date && date.getMonth() + 1 === currentMonth && date.getFullYear() === currentYear) {
        if (transaction.type === 'INCOME') acc.monthIncome += amount
        if (transaction.type === 'EXPENSE') acc.monthExpense += amount
      }

      return acc
    }, {
      balance: 0,
      income: 0,
      expense: 0,
      monthIncome: 0,
      monthExpense: 0,
    })

    const openCreditTotal = openCardExpenses.reduce((acc, expense) => acc + Number(expense.amount || 0), 0)
    const currentInvoiceTotal = openCardExpenses
      .filter((expense) => expense.invoice_month === currentMonth && expense.invoice_year === currentYear)
      .reduce((acc, expense) => acc + Number(expense.amount || 0), 0)
    const daysRemaining = getDaysRemainingInMonth()

    return {
      ...totals,
      openCreditTotal,
      currentInvoiceTotal,
      projectedBalance: totals.balance - openCreditTotal,
      availableAfterCurrentInvoice: totals.balance - currentInvoiceTotal,
      dailyAvailable: (totals.balance - currentInvoiceTotal) / daysRemaining,
      daysRemaining,
    }
  }, [openCardExpenses, transactions])

  const cashflowData = useMemo(() => {
    const today = getNow()
    const months = Array.from({ length: 6 }, (_, index) => {
      const date = new Date(today.getFullYear(), today.getMonth() - (5 - index), 1)
      const key = monthKeyFromDate(date)
      return {
        key,
        month: monthLabelFromKey(key),
        entradas: 0,
        saidas: 0,
      }
    })
    const byKey = Object.fromEntries(months.map((item) => [item.key, item]))

    transactions.forEach((transaction) => {
      const date = parseLocalDate(transaction.date)
      if (!date) return
      const key = monthKeyFromDate(date)
      if (!byKey[key]) return

      if (transaction.type === 'INCOME') {
        byKey[key].entradas += Number(transaction.amount || 0)
      } else {
        byKey[key].saidas += Number(transaction.amount || 0)
      }
    })

    return months.map((item) => ({
      ...item,
      entradas: Number(item.entradas.toFixed(2)),
      saidas: Number(item.saidas.toFixed(2)),
      saldo: Number((item.entradas - item.saidas).toFixed(2)),
    }))
  }, [transactions])

  const expensesByCategory = useMemo(() => {
    const today = getNow()
    const currentMonth = today.getMonth() + 1
    const currentYear = today.getFullYear()
    const grouped = {}

    transactions.forEach((transaction) => {
      if (transaction.type !== 'EXPENSE') return
      if (transaction.category?.startsWith('Pagamento Fatura')) return

      const date = parseLocalDate(transaction.date)
      if (!date || date.getMonth() + 1 !== currentMonth || date.getFullYear() !== currentYear) return

      const category = transaction.category || 'Outros'
      grouped[category] = (grouped[category] || 0) + Number(transaction.amount || 0)
    })

    const cardPurchases = openCardExpenses
      .filter((expense) => {
        const date = parseLocalDate(expense.purchase_date)
        return date && date.getMonth() + 1 === currentMonth && date.getFullYear() === currentYear
      })
      .reduce((acc, expense) => {
        const key = getPurchaseGroupKey(expense)
        if (!acc[key]) {
          acc[key] = {
            category: expense.category || 'Outros',
            total: 0,
          }
        }
        acc[key].total += Number(expense.amount || 0)
        return acc
      }, {})

    Object.values(cardPurchases).forEach((purchase) => {
      grouped[purchase.category] = (grouped[purchase.category] || 0) + purchase.total
    })

    return Object.entries(grouped)
      .map(([name, value]) => ({ name, value: Number(value.toFixed(2)) }))
      .filter((item) => item.value > 0)
      .sort((a, b) => b.value - a.value)
  }, [openCardExpenses, transactions])

  const invoicesByCard = useMemo(() => {
    const groupedByCard = openCardExpenses.reduce((acc, expense) => {
      const cardKey = expense.card_id || 'sem-cartao'
      const invoiceKey = `${expense.invoice_year}-${String(expense.invoice_month).padStart(2, '0')}`

      if (!acc[cardKey]) {
        acc[cardKey] = {
          cardId: expense.card_id,
          cardName: expense.credit_cards?.name || cards.find((card) => card.id === expense.card_id)?.name || 'Cartão',
          dueDay: expense.credit_cards?.due_day || cards.find((card) => card.id === expense.card_id)?.due_day,
          closingDay: expense.credit_cards?.closing_day || cards.find((card) => card.id === expense.card_id)?.closing_day,
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

      acc[cardKey].invoices[invoiceKey].total += Number(expense.amount || 0)

      const purchaseKey = getPurchaseGroupKey(expense)
      const installment = parseInstallmentInfo(expense.installment_info)
      if (!acc[cardKey].invoices[invoiceKey].purchases[purchaseKey]) {
        acc[cardKey].invoices[invoiceKey].purchases[purchaseKey] = {
          purchaseKey,
          card_id: expense.card_id,
          description: expense.description,
          category: expense.category || 'Outros',
          purchase_date: expense.purchase_date,
          amount: Number(expense.amount || 0),
          installmentCurrent: installment.current,
          installmentTotal: installment.total,
        }
      }

      return acc
    }, {})

    return Object.values(groupedByCard)
      .map((cardGroup) => ({
        ...cardGroup,
        invoices: Object.values(cardGroup.invoices)
          .sort((a, b) => {
            if (a.invoiceYear !== b.invoiceYear) return a.invoiceYear - b.invoiceYear
            return a.invoiceMonth - b.invoiceMonth
          })
          .map((invoice) => ({
            ...invoice,
            total: Number(invoice.total.toFixed(2)),
            purchases: Object.values(invoice.purchases).sort((a, b) => a.description.localeCompare(b.description)),
          })),
      }))
      .sort((a, b) => a.cardName.localeCompare(b.cardName))
  }, [cards, openCardExpenses])

  const upcomingInvoices = useMemo(() => {
    return invoicesByCard.flatMap((cardGroup) => (
      cardGroup.invoices.map((invoice) => ({
        ...invoice,
        cardId: cardGroup.cardId,
        cardName: cardGroup.cardName,
        dueDay: cardGroup.dueDay,
        closingDay: cardGroup.closingDay,
      }))
    )).sort((a, b) => {
      if (a.invoiceYear !== b.invoiceYear) return a.invoiceYear - b.invoiceYear
      if (a.invoiceMonth !== b.invoiceMonth) return a.invoiceMonth - b.invoiceMonth
      return a.cardName.localeCompare(b.cardName)
    })
  }, [invoicesByCard])

  const recentTransactions = useMemo(() => {
    return [...transactions]
      .sort((a, b) => {
        if (a.date !== b.date) return String(b.date).localeCompare(String(a.date))
        return String(b.created_at || '').localeCompare(String(a.created_at || ''))
      })
      .slice(0, 8)
  }, [transactions])

  const toggleCardExpenses = (cardId) => {
    setExpandedCards((current) => (
      current.includes(cardId)
        ? current.filter((id) => id !== cardId)
        : [...current, cardId]
    ))
  }

  const handleBankSubmit = async (event) => {
    event.preventDefault()
    const amount = Number(transForm.amount)
    if (!Number.isFinite(amount) || amount <= 0) {
      setDataError('Informe um valor válido.')
      return
    }

    setLoading(true)
    setDataError('')
    setNotice('')
    try {
      await transactionsApi.create({
        amount,
        date: transForm.date,
        category: transForm.category,
        description: transForm.description,
        type: transForm.type,
      })
      setTransForm({
        amount: '',
        date: getLocalDateString(),
        category: '',
        description: '',
        type: transForm.type,
      })
      await fetchData()
      setNotice('Lançamento bancário registrado.')
    } catch (error) {
      setDataError(error.message || 'Não foi possível criar o lançamento.')
    } finally {
      setLoading(false)
    }
  }

  const handleDueDayChange = (event) => {
    const due = parseInt(event.target.value, 10)
    let closing = ''
    if (!Number.isNaN(due)) {
      closing = due - 7
      if (closing <= 0) closing += 30
    }
    setCardForm({ ...cardForm, due_day: event.target.value, closing_day: String(closing) })
  }

  const handleCreateCard = async (event) => {
    event.preventDefault()
    const dueDay = Number(cardForm.due_day)
    const closingDay = Number(cardForm.closing_day)
    if (!cardForm.name.trim() || !Number.isInteger(dueDay) || !Number.isInteger(closingDay)) {
      setDataError('Preencha os dados do cartão corretamente.')
      return
    }

    setLoading(true)
    setDataError('')
    setNotice('')
    try {
      await creditCardsApi.create({
        name: cardForm.name,
        due_day: dueDay,
        closing_day: closingDay,
      })
      setCardForm({ name: '', due_day: '', closing_day: '' })
      await fetchData()
      setNotice('Cartão criado.')
    } catch (error) {
      setDataError(error.message || 'Não foi possível criar o cartão.')
    } finally {
      setLoading(false)
    }
  }

  const handleCCExpenseSubmit = async (event) => {
    event.preventDefault()
    const totalAmount = Number(expenseForm.total_amount)
    const installmentsCount = Number(expenseForm.installments)
    const purchaseDate = parseLocalDate(expenseForm.purchase_date)
    const selectedCard = cards.find((card) => card.id === expenseForm.card_id)

    if (
      !selectedCard
      || !purchaseDate
      || Number.isNaN(purchaseDate.getTime())
      || !Number.isFinite(totalAmount)
      || totalAmount <= 0
      || !Number.isInteger(installmentsCount)
      || installmentsCount <= 0
    ) {
      setDataError('Preencha a compra no cartão com valores válidos.')
      return
    }

    setLoading(true)
    setDataError('')
    setNotice('')
    try {
      // O parcelamento e a fatura de cada parcela sao calculados no backend
      // (POST /api/cc-expenses/purchases), junto do cartao que define a regra.
      await ccExpensesApi.createPurchase({
        card_id: expenseForm.card_id,
        category: expenseForm.category,
        description: expenseForm.description,
        total_amount: totalAmount,
        purchase_date: expenseForm.purchase_date,
        installments: installmentsCount,
      })
      setExpenseForm({
        card_id: cards[0]?.id || '',
        category: '',
        description: '',
        total_amount: '',
        purchase_date: getLocalDateString(),
        installments: '1',
      })
      await fetchData()
      setNotice('Compra no cartão registrada.')
    } catch (error) {
      setDataError(error.message || 'Não foi possível criar a compra no cartão.')
    } finally {
      setLoading(false)
    }
  }

  const handlePayInvoice = async (invoice) => {
    const confirmed = window.confirm(
      `Deseja pagar a fatura ${formatInvoiceLabel(invoice.invoiceMonth, invoice.invoiceYear)} do cartão ${invoice.cardName} no valor de ${formatCurrency(invoice.total)}?`
    )
    if (!confirmed) return

    setLoading(true)
    setDataError('')
    setNotice('')
    try {
      await transactionsApi.create({
        type: 'EXPENSE',
        amount: Number(invoice.total.toFixed(2)),
        date: getLocalDateString(),
        category: `Pagamento Fatura ${invoice.cardName}`,
        description: `Fatura ${formatInvoiceLabel(invoice.invoiceMonth, invoice.invoiceYear)}`,
      })

      await ccExpensesApi.updateInvoiceStatus({
        card_id: invoice.cardId,
        invoice_month: invoice.invoiceMonth,
        invoice_year: invoice.invoiceYear,
        status: 'PAID',
        current_status: 'OPEN',
      })

      await fetchData()
      setNotice('Fatura paga e saída bancária criada.')
    } catch (error) {
      setDataError(error.message || 'Não foi possível pagar a fatura.')
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteTransaction = async (transaction) => {
    if (!window.confirm(`Excluir "${transaction.description}" no valor de ${formatCurrency(transaction.amount)}?`)) return

    setDataError('')
    setNotice('')
    try {
      await transactionsApi.remove(transaction.id)
      await fetchData()
      setNotice('Lançamento excluído.')
    } catch (error) {
      setDataError(error.message || 'Não foi possível excluir a transação.')
    }
  }

  const handleDeleteCard = async (card) => {
    const confirmed = window.confirm(
      `Excluir o cartão "${card.name}"? Todas as faturas vinculadas a ele também serão apagadas.`
    )
    if (!confirmed) return

    setDataError('')
    setNotice('')
    try {
      await creditCardsApi.remove(card.id)
      await fetchData()
      setNotice('Cartão excluído.')
    } catch (error) {
      setDataError(error.message || 'Não foi possível excluir o cartão.')
    }
  }

  const handleDeleteCCPurchase = async (purchase) => {
    if (!window.confirm(`Excluir a compra "${purchase.description}" e todas as parcelas vinculadas?`)) return

    setDataError('')
    setNotice('')
    try {
      const candidates = await ccExpensesApi.candidates({
        card_id: purchase.card_id,
        description: purchase.description,
        purchase_date: purchase.purchase_date,
        category: purchase.category,
      })

      const idsToDelete = (candidates || [])
        .filter((item) => {
          const installment = parseInstallmentInfo(item.installment_info)
          return Number(parseFloat(item.amount || 0).toFixed(2)) === Number(parseFloat(purchase.amount || 0).toFixed(2))
            && installment.total === purchase.installmentTotal
        })
        .map((item) => item.id)

      if (idsToDelete.length === 0) {
        setDataError('Nenhuma parcela vinculada foi encontrada para essa compra.')
        return
      }

      await ccExpensesApi.removeMany(idsToDelete)
      await fetchData()
      setNotice('Compra excluída.')
    } catch (error) {
      setDataError(error.message || 'Não foi possível excluir a compra.')
    }
  }

  const handleCreateMockData = async () => {
    setMockLoading(true)
    setDataError('')
    setNotice('')

    try {
      let latestCards = await creditCardsApi.list()
      const createdCounts = {
        cards: 0,
        transactions: 0,
        expenses: 0,
      }

      for (const mockCard of MOCK_CARDS) {
        const exists = latestCards.some((card) => card.name === mockCard.name)
        if (!exists) {
          await creditCardsApi.create(mockCard)
          createdCounts.cards += 1
        }
      }

      latestCards = await creditCardsApi.list()
      const latestTransactions = await transactionsApi.list()
      const latestCardExpenses = await ccExpensesApi.list()

      for (const mockTransaction of buildMockTransactions()) {
        if (!latestTransactions.some((transaction) => isSameTransaction(transaction, mockTransaction))) {
          await transactionsApi.create(mockTransaction)
          createdCounts.transactions += 1
        }
      }

      const cardByName = Object.fromEntries(latestCards.map((card) => [card.name, card]))

      for (const mockPurchase of MOCK_PURCHASES) {
        const card = cardByName[mockPurchase.cardName]
        if (!card) continue

        const alreadySeeded = latestCardExpenses.some((expense) => isSamePurchase(expense, {
          card_id: card.id,
          description: mockPurchase.description,
          purchase_date: mockPurchase.purchase_date,
          category: mockPurchase.category,
        }))
        if (alreadySeeded) continue

        const created = await ccExpensesApi.createPurchase({
          card_id: card.id,
          category: mockPurchase.category,
          description: mockPurchase.description,
          total_amount: mockPurchase.total_amount,
          purchase_date: mockPurchase.purchase_date,
          installments: mockPurchase.installments,
        })
        createdCounts.expenses += created.length
      }

      await fetchData()
      setActiveTab('CARTOES')
      setExpandedCards(latestCards.map((card) => card.id))
      setNotice(
        `Dados demo aplicados: ${createdCounts.cards} cartão(ões), ${createdCounts.transactions} lançamento(s) bancário(s) e ${createdCounts.expenses} parcela(s) de cartão.`
      )
    } catch (error) {
      setDataError(error.message || 'Não foi possível criar os dados demo.')
    } finally {
      setMockLoading(false)
    }
  }

  const getInvoiceStatus = (year, month, dueDay) => {
    const today = getNow()
    const dueDate = new Date(year, month - 1, dueDay || 1)
    if (today > dueDate) return <Badge tone="danger">Em atraso</Badge>
    return <Badge tone="warning">Aberta</Badge>
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Carteira"
        title="Controle diário"
        description="Saldo em conta, recebimentos, despesas, cartões e faturas em aberto no mesmo fluxo."
        actions={(
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="secondary" icon={RefreshCw} onClick={fetchData}>
              Atualizar
            </Button>
            <Button type="button" variant="dark" icon={Sparkles} loading={mockLoading} onClick={handleCreateMockData}>
              Criar dados demo
            </Button>
          </div>
        )}
      />

      {dataError ? <AlertMessage tone="danger" message={dataError} /> : null}
      {notice ? <AlertMessage tone="success" message={notice} /> : null}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={Landmark}
          tone={walletSummary.balance >= 0 ? 'success' : 'danger'}
          title="Saldo atual"
          value={formatCurrency(walletSummary.balance)}
          valueClassName={walletSummary.balance >= 0 ? 'text-zinc-950' : 'text-rose-600'}
          subtitle={`${formatCurrency(walletSummary.monthIncome)} recebidos no mês`}
        />
        <MetricCard
          icon={Receipt}
          tone={walletSummary.monthExpense > 0 ? 'warning' : 'neutral'}
          title="Despesas do mês"
          value={formatCurrency(walletSummary.monthExpense)}
          valueClassName="text-zinc-950"
          subtitle="Saídas bancárias registradas"
        />
        <MetricCard
          icon={CreditCard}
          tone={walletSummary.openCreditTotal > 0 ? 'info' : 'success'}
          title="Cartões abertos"
          value={formatCurrency(walletSummary.openCreditTotal)}
          valueClassName={walletSummary.openCreditTotal > 0 ? 'text-sky-700' : 'text-emerald-700'}
          subtitle={`${upcomingInvoices.length} fatura(s) em aberto`}
        />
        <MetricCard
          icon={Wallet}
          tone={walletSummary.projectedBalance >= 0 ? 'dark' : 'danger'}
          title="Saldo projetado"
          value={formatCurrency(walletSummary.projectedBalance)}
          valueClassName={walletSummary.projectedBalance >= 0 ? 'text-zinc-950' : 'text-rose-600'}
          subtitle="Conta menos cartões abertos"
        />
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
        <Panel className="xl:col-span-3">
          <PanelHeader
            title="Fluxo dos últimos 6 meses"
            description="Entradas e saídas lançadas na conta corrente."
            actions={<Badge tone={walletSummary.dailyAvailable >= 0 ? 'success' : 'danger'}>{formatCurrency(walletSummary.dailyAvailable)} por dia</Badge>}
          />
          <div className="p-5">
            <div className="h-80 min-h-[320px] min-w-0">
              {cashflowData.some((item) => item.entradas > 0 || item.saidas > 0) ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={cashflowData} margin={{ top: 8, right: 12, left: 0, bottom: 8 }}>
                    <CartesianGrid vertical={false} stroke="#e4e4e7" />
                    <XAxis dataKey="month" tick={{ fill: '#71717a', fontSize: 12 }} tickLine={false} axisLine={false} />
                    <YAxis tickFormatter={compactCurrency} tick={{ fill: '#71717a', fontSize: 12 }} tickLine={false} axisLine={false} width={74} />
                    <Tooltip formatter={(value, name) => [formatCurrency(value), name === 'entradas' ? 'Entradas' : 'Saídas']} contentStyle={{ borderRadius: 8, borderColor: '#d4d4d8' }} />
                    <Bar dataKey="entradas" fill="#059669" radius={[5, 5, 0, 0]} maxBarSize={42} />
                    <Bar dataKey="saidas" fill="#e11d48" radius={[5, 5, 0, 0]} maxBarSize={42} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <EmptyState icon={Receipt} title="Sem fluxo registrado" message="Use os lançamentos ou os dados demo para preencher o gráfico." className="h-full min-h-0" />
              )}
            </div>
          </div>
        </Panel>

        <Panel className="xl:col-span-2">
          <PanelHeader
            title="Despesas por categoria"
            description="Conta corrente e compras no cartão feitas neste mês."
            actions={<Badge>{formatCurrency(expensesByCategory.reduce((acc, item) => acc + item.value, 0))}</Badge>}
          />
          <div className="p-5">
            {expensesByCategory.length > 0 ? (
              <div className="space-y-5">
                <div className="h-56 min-h-[224px] min-w-0">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={expensesByCategory} dataKey="value" nameKey="name" innerRadius={54} outerRadius={86} paddingAngle={2}>
                        {expensesByCategory.map((entry, index) => (
                          <Cell key={entry.name} fill={CATEGORY_COLORS[index % CATEGORY_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(value) => formatCurrency(value)} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="space-y-3">
                  {expensesByCategory.slice(0, 6).map((item, index) => (
                    <div key={item.name} className="flex items-center justify-between gap-3 text-sm">
                      <div className="flex min-w-0 items-center gap-2 font-medium text-zinc-700">
                        <span className="h-3 w-3 shrink-0 rounded-sm" style={{ backgroundColor: CATEGORY_COLORS[index % CATEGORY_COLORS.length] }} />
                        <span className="truncate">{item.name}</span>
                      </div>
                      <span className="font-semibold text-zinc-950">{formatCurrency(item.value)}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <EmptyState icon={Receipt} title="Sem despesas no mês" message="As categorias aparecem depois dos lançamentos." className="min-h-[19rem]" />
            )}
          </div>
        </Panel>
      </div>

      <Panel>
        <div className="flex flex-col gap-4 border-b border-zinc-100 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
          <PanelHeader
            title="Operações da carteira"
            description="Registre conta corrente, cartões e compras parceladas."
            className="border-b-0 p-0"
          />
          <SegmentedControl
            value={activeTab}
            onChange={setActiveTab}
            items={[
              { value: 'CONTA', label: 'Conta corrente', icon: Banknote },
              { value: 'CARTOES', label: 'Cartões e faturas', icon: CreditCard },
            ]}
          />
        </div>

        {activeTab === 'CONTA' ? (
          <div className="space-y-6 p-5">
            <form onSubmit={handleBankSubmit} className="grid grid-cols-1 gap-4 lg:grid-cols-12">
              <Field label="Tipo" className="lg:col-span-2">
                <select value={transForm.type} onChange={(event) => setTransForm({ ...transForm, type: event.target.value })} className="app-select">
                  <option value="EXPENSE">Despesa</option>
                  <option value="INCOME">Recebimento</option>
                </select>
              </Field>
              <Field label="Valor" className="lg:col-span-2">
                <input type="number" step="0.01" min="0.01" placeholder="0,00" value={transForm.amount} onChange={(event) => setTransForm({ ...transForm, amount: event.target.value })} className="app-input" required />
              </Field>
              <Field label="Data" className="lg:col-span-2">
                <input type="date" value={transForm.date} onChange={(event) => setTransForm({ ...transForm, date: event.target.value })} className="app-input" required />
              </Field>
              <Field label="Categoria" className="lg:col-span-2">
                <select value={transForm.category} onChange={(event) => setTransForm({ ...transForm, category: event.target.value })} className="app-select" required>
                  <option value="">Selecione...</option>
                  {CATEGORY_OPTIONS.map((category) => (
                    <option key={category} value={category}>{category}</option>
                  ))}
                </select>
              </Field>
              <Field label="Descrição" className="lg:col-span-3">
                <input type="text" placeholder="Ex: Mercado, salário, aluguel" value={transForm.description} onChange={(event) => setTransForm({ ...transForm, description: event.target.value })} className="app-input" required />
              </Field>
              <div className="flex items-end lg:col-span-1">
                <Button type="submit" icon={Plus} loading={loading} className="w-full">
                  Salvar
                </Button>
              </div>
            </form>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <InlineStat icon={ArrowUpCircle} label="Entradas totais" value={formatCurrency(walletSummary.income)} tone="success" />
              <InlineStat icon={ArrowDownCircle} label="Saídas totais" value={formatCurrency(walletSummary.expense)} tone="danger" />
              <InlineStat icon={Wallet} label="Após fatura atual" value={formatCurrency(walletSummary.availableAfterCurrentInvoice)} tone={walletSummary.availableAfterCurrentInvoice >= 0 ? 'neutral' : 'danger'} />
            </div>

            <Panel>
              <PanelHeader title="Extrato recente" description="Últimos recebimentos e despesas registrados." actions={<Badge>{transactions.length} registro(s)</Badge>} />
              {recentTransactions.length > 0 ? (
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
                      {recentTransactions.map((transaction) => (
                        <tr key={transaction.id}>
                          <td className="text-zinc-600">{formatDateBR(transaction.date)}</td>
                          <td className="font-medium text-zinc-800">{transaction.category}</td>
                          <td className="text-zinc-700">{transaction.description}</td>
                          <td>
                            {transaction.type === 'INCOME' ? <Badge tone="success">Recebimento</Badge> : <Badge tone="danger">Despesa</Badge>}
                          </td>
                          <td className={cx('font-bold', transaction.type === 'INCOME' ? 'text-emerald-700' : 'text-rose-600')}>
                            {transaction.type === 'INCOME' ? '+' : '-'} {formatCurrency(transaction.amount)}
                          </td>
                          <td className="text-right">
                            <IconButton label="Excluir lançamento" icon={Trash2} variant="danger" onClick={() => handleDeleteTransaction(transaction)} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="p-5">
                  <EmptyState icon={Receipt} title="Nenhum lançamento" message="Recebimentos e despesas aparecerão aqui." />
                </div>
              )}
            </Panel>
          </div>
        ) : null}

        {activeTab === 'CARTOES' ? (
          <div className="space-y-6 p-5">
            <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
              <Panel className="h-fit">
                <PanelHeader title="Cartões" description="Cadastre vencimento e fechamento." />
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
                  <Button type="submit" variant="dark" icon={Plus} loading={loading} className="w-full">
                    Salvar cartão
                  </Button>
                </form>

                <div className="border-t border-zinc-100 p-5">
                  {cards.length > 0 ? (
                    <div className="space-y-2">
                      {cards.map((card) => (
                        <div key={card.id} className="flex items-center justify-between gap-3 rounded-lg border border-zinc-200 px-3 py-3">
                          <div className="min-w-0">
                            <p className="truncate text-sm font-bold text-zinc-800">{card.name}</p>
                            <p className="mt-0.5 text-xs text-zinc-500">Vence dia {card.due_day} · Fecha dia {card.closing_day}</p>
                          </div>
                          <IconButton label="Excluir cartão" icon={Trash2} variant="danger" onClick={() => handleDeleteCard(card)} />
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState icon={CreditCard} title="Nenhum cartão" message="Cadastre um cartão para lançar compras." className="min-h-40" />
                  )}
                </div>
              </Panel>

              <Panel className="xl:col-span-2">
                <PanelHeader title="Compra no crédito" description="Registre compra à vista ou parcelada." />
                <div className="p-5">
                  {cards.length === 0 ? (
                    <EmptyState icon={CreditCard} title="Cadastre um cartão primeiro" message="Depois disso, o formulário de compras fica disponível." />
                  ) : (
                    <form onSubmit={handleCCExpenseSubmit} className="grid grid-cols-1 gap-4 md:grid-cols-2">
                      <Field label="Cartão">
                        <select value={expenseForm.card_id} onChange={(event) => setExpenseForm({ ...expenseForm, card_id: event.target.value })} className="app-select" required>
                          <option value="">Selecione...</option>
                          {cards.map((card) => (
                            <option key={card.id} value={card.id}>{card.name} (vence dia {card.due_day})</option>
                          ))}
                        </select>
                      </Field>
                      <Field label="Categoria">
                        <select value={expenseForm.category} onChange={(event) => setExpenseForm({ ...expenseForm, category: event.target.value })} className="app-select" required>
                          <option value="">Selecione...</option>
                          {EXPENSE_CATEGORIES.map((category) => (
                            <option key={category} value={category}>{category}</option>
                          ))}
                        </select>
                      </Field>
                      <Field label="Descrição">
                        <input type="text" placeholder="O que você comprou?" value={expenseForm.description} onChange={(event) => setExpenseForm({ ...expenseForm, description: event.target.value })} className="app-input" required />
                      </Field>
                      <Field label="Valor total">
                        <input type="number" step="0.01" min="0.01" placeholder="0,00" value={expenseForm.total_amount} onChange={(event) => setExpenseForm({ ...expenseForm, total_amount: event.target.value })} className="app-input" required />
                      </Field>
                      <Field label="Data da compra">
                        <input type="date" value={expenseForm.purchase_date} onChange={(event) => setExpenseForm({ ...expenseForm, purchase_date: event.target.value })} className="app-input" required />
                      </Field>
                      <Field label="Parcelas">
                        <input type="number" min="1" max="48" value={expenseForm.installments} onChange={(event) => setExpenseForm({ ...expenseForm, installments: event.target.value })} className="app-input" required />
                      </Field>
                      <Button type="submit" icon={Plus} loading={loading} className="md:col-span-2">
                        Registrar compra
                      </Button>
                    </form>
                  )}
                </div>
              </Panel>
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <InlineStat icon={CreditCard} label="Total aberto" value={formatCurrency(walletSummary.openCreditTotal)} tone="info" />
              <InlineStat icon={Receipt} label="Fatura do mês" value={formatCurrency(walletSummary.currentInvoiceTotal)} tone={walletSummary.currentInvoiceTotal > 0 ? 'danger' : 'success'} />
              <InlineStat icon={Wallet} label="Saldo projetado" value={formatCurrency(walletSummary.projectedBalance)} tone={walletSummary.projectedBalance >= 0 ? 'neutral' : 'danger'} />
            </div>

            {invoicesByCard.length > 0 ? (
              <div className="space-y-4">
                {invoicesByCard.map((cardGroup) => {
                  const isExpanded = expandedCards.includes(cardGroup.cardId)
                  const cardTotal = cardGroup.invoices.reduce((acc, invoice) => acc + invoice.total, 0)

                  return (
                    <Panel key={cardGroup.cardId} className="overflow-hidden">
                      <div className="flex flex-col gap-4 border-b border-zinc-100 px-5 py-4 md:flex-row md:items-center md:justify-between">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="text-lg font-bold text-zinc-950">{cardGroup.cardName}</h3>
                            <Badge tone="info">{cardGroup.invoices.length} fatura(s)</Badge>
                            <Badge tone="warning">{formatCurrency(cardTotal)}</Badge>
                          </div>
                          <p className="mt-1 text-sm text-zinc-500">Vence dia {cardGroup.dueDay} · Fecha dia {cardGroup.closingDay}</p>
                        </div>

                        <Button type="button" variant="secondary" icon={isExpanded ? ChevronUp : ChevronDown} onClick={() => toggleCardExpenses(cardGroup.cardId)}>
                          {isExpanded ? 'Ocultar' : 'Ver faturas'}
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
                                  <Button type="button" icon={CheckCircle} loading={loading} onClick={() => handlePayInvoice({ ...invoice, cardId: cardGroup.cardId, cardName: cardGroup.cardName })}>
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
                                      <IconButton label="Excluir compra" icon={Trash2} variant="danger" onClick={() => handleDeleteCCPurchase(purchase)} />
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
                <EmptyState icon={CreditCard} title="Nenhuma fatura aberta" message="As compras no crédito aparecerão agrupadas por cartão e vencimento." />
              </Panel>
            )}
          </div>
        ) : null}
      </Panel>
    </div>
  )
}

function AlertMessage({ tone = 'danger', message }) {
  const classes = tone === 'success'
    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
    : 'border-amber-200 bg-amber-50 text-amber-800'

  return (
    <div className={cx('flex items-start gap-3 rounded-lg border px-4 py-3 text-sm font-medium', classes)}>
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{message}</span>
    </div>
  )
}

function InlineStat({ icon: Icon, label, value, tone = 'neutral' }) {
  const toneClasses = {
    neutral: 'bg-zinc-100 text-zinc-700',
    success: 'bg-emerald-100 text-emerald-700',
    info: 'bg-sky-100 text-sky-700',
    danger: 'bg-rose-100 text-rose-700',
  }

  return (
    <div className="flex items-center gap-3 rounded-lg border border-zinc-200 bg-white px-4 py-3">
      <div className={cx('flex h-10 w-10 shrink-0 items-center justify-center rounded-lg', toneClasses[tone] || toneClasses.neutral)}>
        <Icon className="h-5 w-5" />
      </div>
      <div className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{label}</p>
        <p className="truncate text-lg font-bold text-zinc-950">{value}</p>
      </div>
    </div>
  )
}
