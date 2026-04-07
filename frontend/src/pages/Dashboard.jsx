import { useEffect, useMemo, useState } from 'react'
import { supabase } from '../lib/supabaseClient'
import { BarChart, Bar, CartesianGrid, Tooltip, ResponsiveContainer, Legend, XAxis, YAxis } from 'recharts'
import { Landmark, Wallet, PiggyBank, CreditCard, CalendarDays } from 'lucide-react'

const CATEGORIES = ['Alimentação', 'Moradia', 'Transporte', 'Saúde', 'Educação', 'Lazer', 'Serviços', 'Outros']
const PAYMENT_METHOD_COLORS = {
  cash: '#0f172a',
  credit: '#2563eb'
}

const formatCurrency = (value) => new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL'
}).format(Number(value || 0))

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
    total: Number.isFinite(total) ? total : 1
  }
}

const formatInvoiceLabel = (month, year) => {
  return `${String(month).padStart(2, '0')}/${year}`
}

export default function Dashboard() {
  const [portfolio, setPortfolio] = useState(null)
  const [bankBalance, setBankBalance] = useState(0)
  const [nextMonthInvoice, setNextMonthInvoice] = useState(0)
  const [currentMonthInvoice, setCurrentMonthInvoice] = useState(0)
  const [expensesByCategory, setExpensesByCategory] = useState([])
  const [installmentExpenses, setInstallmentExpenses] = useState([])

  useEffect(() => {
    fetchAllData()
  }, [])

  const fetchAllData = async () => {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session) return

    try {
      const response = await fetch('http://localhost:5000/api/investments/portfolio', {
        headers: { Authorization: `Bearer ${session.access_token}` }
      })
      const data = await response.json()
      setPortfolio(data)
    } catch (error) {
      console.error('Erro ao buscar portfólio:', error)
    }

    const today = new Date()
    const currentMonth = today.getMonth() + 1
    const currentYear = today.getFullYear()
    let nextMonth = currentMonth + 1
    let nextYear = currentYear

    if (nextMonth > 12) {
      nextMonth = 1
      nextYear++
    }

    const [{ data: transData }, { data: ccData }] = await Promise.all([
      supabase.from('transactions').select('*'),
      supabase.from('cc_expenses').select('*, credit_cards(name)').eq('status', 'OPEN')
    ])

    const categoryTotals = {}
    CATEGORIES.forEach((category) => {
      categoryTotals[category] = { cash: 0, credit: 0 }
    })

    let calculatedBalance = 0

    if (transData) {
      calculatedBalance = transData.reduce((acc, curr) => {
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
    }

    if (ccData) {
      const currentMonthCreditExpenses = ccData.filter((expense) => {
        return expense.invoice_month === currentMonth && expense.invoice_year === currentYear
      })

      currentMonthCreditExpenses.forEach((expense) => {
        const category = CATEGORIES.includes(expense.category) ? expense.category : 'Outros'
        categoryTotals[category].credit += parseFloat(expense.amount)
      })

      const nextMonthTotal = ccData
        .filter((expense) => expense.invoice_month === nextMonth && expense.invoice_year === nextYear)
        .reduce((acc, curr) => acc + parseFloat(curr.amount), 0)

      const currentMonthTotal = ccData
        .filter((expense) => expense.invoice_month === currentMonth && expense.invoice_year === currentYear)
        .reduce((acc, curr) => acc + parseFloat(curr.amount), 0)

      const openInstallments = ccData
        .map((expense) => {
          const installment = parseInstallmentInfo(expense.installment_info)
          return {
            ...expense,
            installmentCurrent: installment.current,
            installmentTotal: installment.total
          }
        })
        .filter((expense) => expense.installmentTotal > 1)
        .sort((a, b) => {
          if (a.invoice_year !== b.invoice_year) return a.invoice_year - b.invoice_year
          if (a.invoice_month !== b.invoice_month) return a.invoice_month - b.invoice_month
          return a.installmentCurrent - b.installmentCurrent
        })

      setCurrentMonthInvoice(currentMonthTotal)
      setNextMonthInvoice(nextMonthTotal)
      setInstallmentExpenses(openInstallments)
    }

    const chartDataExpenses = Object.keys(categoryTotals)
      .map((category) => ({
        name: category,
        cash: Number(categoryTotals[category].cash.toFixed(2)),
        credit: Number(categoryTotals[category].credit.toFixed(2)),
        value: Number((categoryTotals[category].cash + categoryTotals[category].credit).toFixed(2))
      }))
      .filter((item) => item.value > 0)
      .sort((a, b) => b.value - a.value)

    setExpensesByCategory(chartDataExpenses)
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

  const installmentSummary = useMemo(() => {
    return installmentExpenses.reduce((acc, item) => {
      acc.total += parseFloat(item.amount)
      return acc
    }, { total: 0 })
  }, [installmentExpenses])

  if (!portfolio) return <div className="text-slate-500 animate-pulse p-8">Calculando painel financeiro...</div>

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      <div>
        <h1 className="text-3xl font-bold text-slate-800">Visão Geral</h1>
        <p className="text-slate-500 mt-1">Seu patrimônio, despesas por categoria e acompanhamento das parcelas abertas no cartão.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="bg-slate-900 p-6 rounded-2xl shadow-lg border border-slate-800 flex items-center gap-4 min-h-[132px] lg:col-span-3">
          <div className="bg-blue-500 p-3 rounded-xl text-white"><Landmark size={24} /></div>
          <div className="w-full">
            <h3 className="text-xs font-medium text-slate-300">Patrimônio Total</h3>
            <p className="text-2xl font-bold text-white mt-1">{formatCurrency(totalWealth)}</p>
          </div>
        </div>

        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 flex items-center gap-4 min-h-[132px] lg:col-span-3">
          <div className="bg-slate-100 p-3 rounded-xl text-slate-600"><Wallet size={24} /></div>
          <div className="w-full">
            <h3 className="text-xs font-medium text-slate-500">Saldo em Conta</h3>
            <p className={`text-2xl font-bold mt-1 ${bankBalance >= 0 ? 'text-slate-900' : 'text-red-500'}`}>{formatCurrency(bankBalance)}</p>
          </div>
        </div>

        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 flex items-center gap-4 min-h-[132px] lg:col-span-3">
          <div className="bg-blue-50 p-3 rounded-xl text-blue-600"><PiggyBank size={24} /></div>
          <div className="w-full">
            <h3 className="text-xs font-medium text-slate-500">Investimentos</h3>
            <p className="text-2xl font-bold text-blue-600 mt-1">{formatCurrency(portfolio.current_balance)}</p>
          </div>
        </div>

        

        <div className="lg:col-span-3 flex flex-col gap-4">
          <div className="bg-emerald-50 p-9 rounded-2xl shadow-sm border border-emerald-100 flex items-center gap-3 min-h-[84px]">
            <div className="bg-emerald-100 p-2.5 rounded-xl text-emerald-700"><CalendarDays size={20} /></div>
            <div className="w-full">
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-emerald-800">Disponível por dia</h3>
              <p className={`text-base font-bold mt-0.5 ${dailyAvailable >= 0 ? 'text-emerald-700' : 'text-red-600'}`}>{formatCurrency(dailyAvailable)}</p>
              <p className="text-[10px] text-emerald-900/70 mt-1">{daysRemainingInMonth} dia(s) restantes no mês.</p>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100">
          <div className="flex items-start justify-between gap-4 mb-6">
            <div>
              <h2 className="text-lg font-bold text-slate-800">Despesas do Mês por Categoria</h2>
              <p className="text-sm text-slate-500 mt-1">Separadas entre dinheiro/conta e cartão de crédito.</p>
            </div>
            <div className="text-right">
              <p className="text-xs text-slate-500">Total do mês</p>
              <p className="text-lg font-bold text-slate-800">{formatCurrency(expenseTotals.total)}</p>
            </div>
          </div>

          {expensesByCategory.length > 0 ? (
            <div className="space-y-6">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <p className="text-sm text-slate-500">Em dinheiro / conta</p>
                  <p className="text-2xl font-bold text-slate-900 mt-1">{formatCurrency(expenseTotals.cash)}</p>
                </div>
                <div className="rounded-2xl border border-blue-200 bg-blue-50 p-4">
                  <p className="text-sm text-blue-700">No cartão de crédito</p>
                  <p className="text-2xl font-bold text-blue-700 mt-1">{formatCurrency(expenseTotals.credit)}</p>
                </div>
              </div>

              <div className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={expensesByCategory} layout="vertical" margin={{ top: 8, right: 16, left: 16, bottom: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" tickFormatter={(value) => `${Math.round(value)}`} />
                    <YAxis dataKey="name" type="category" width={90} />
                    <Tooltip
                      formatter={(value, name) => [formatCurrency(value), name === 'cash' ? 'Dinheiro / Conta' : 'Cartão de Crédito']}
                      labelFormatter={(label) => `Categoria: ${label}`}
                    />
                    <Legend formatter={(value) => value === 'cash' ? 'Dinheiro / Conta' : 'Cartão de Crédito'} />
                    <Bar dataKey="cash" stackId="expenses" fill={PAYMENT_METHOD_COLORS.cash} radius={[4, 0, 0, 4]} />
                    <Bar dataKey="credit" stackId="expenses" fill={PAYMENT_METHOD_COLORS.credit} radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              <div className="space-y-3">
                {expensesByCategory.map((item) => (
                  <div key={item.name} className="rounded-xl border border-slate-200 p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="font-semibold text-slate-800">{item.name}</p>
                        <div className="flex flex-wrap gap-2 mt-2">
                          {item.cash > 0 && (
                            <span className="inline-flex items-center rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700">
                              Dinheiro / Conta: {formatCurrency(item.cash)}
                            </span>
                          )}
                          {item.credit > 0 && (
                            <span className="inline-flex items-center rounded-full bg-blue-100 px-3 py-1 text-xs font-medium text-blue-700">
                              Cartão: {formatCurrency(item.credit)}
                            </span>
                          )}
                        </div>
                      </div>
                      <p className="text-base font-bold text-slate-900">{formatCurrency(item.value)}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="h-72 flex flex-col items-center justify-center text-slate-400">
              <p>Nenhuma despesa lançada neste mês.</p>
            </div>
          )}
        </div>

        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100">
          <div className="flex items-start justify-between gap-4 mb-6">
            <div>
              <h2 className="text-lg font-bold text-slate-800">Gastos Parcelados no Cartão</h2>
              <p className="text-sm text-slate-500 mt-1">Parcelas abertas das compras feitas no crédito.</p>
            </div>
            <div className="text-right">
              <p className="text-xs text-slate-500">Parcelado em aberto</p>
              <p className="text-lg font-bold text-slate-800">{formatCurrency(installmentSummary.total)}</p>
            </div>
          </div>


          {installmentExpenses.length > 0 ? (
            <div className="space-y-3 max-h-[520px] overflow-y-auto pr-1">
              {installmentExpenses.map((expense) => (
                <div key={expense.id} className="rounded-xl border border-slate-200 p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="font-semibold text-slate-800">{expense.description}</p>
                      <div className="flex flex-wrap gap-2 mt-2">
                        <span className="inline-flex items-center rounded-full bg-blue-100 px-3 py-1 text-xs font-medium text-blue-700">
                          {expense.credit_cards?.name || 'Cartão'}
                        </span>
                        <span className="inline-flex items-center rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700">
                          Parcela {expense.installmentCurrent}/{expense.installmentTotal}
                        </span>
                        <span className="inline-flex items-center rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-700">
                          Fatura {formatInvoiceLabel(expense.invoice_month, expense.invoice_year)}
                        </span>
                      </div>
                    </div>
                    <p className="text-base font-bold text-slate-900 whitespace-nowrap">{formatCurrency(expense.amount)}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="h-72 flex flex-col items-center justify-center text-slate-400 text-center">
              <p>Você não tem compras parceladas abertas no cartão.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
