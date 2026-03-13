import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabaseClient'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { TrendingUp, Landmark, Wallet, PiggyBank, CreditCard } from 'lucide-react'

// Categorias Pré-definidas em Código
const CATEGORIES = ['Alimentação', 'Moradia', 'Transporte', 'Saúde', 'Educação', 'Lazer', 'Serviços', 'Outros']
const CATEGORY_COLORS = ['#f97316', '#3b82f6', '#10b981', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#64748b']

export default function Dashboard() {
  const [portfolio, setPortfolio] = useState(null)
  const [bankBalance, setBankBalance] = useState(0)
  const [nextMonthInvoice, setNextMonthInvoice] = useState(0)
  const [expensesByCategory, setExpensesByCategory] = useState([])
  
  useEffect(() => {
    fetchAllData()
  }, [])

  const fetchAllData = async () => {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session) return

    // 1. Busca os Investimentos do Flask
    try {
      const response = await fetch('http://localhost:5000/api/investments/portfolio', {
        headers: { 'Authorization': `Bearer ${session.access_token}` }
      })
      const data = await response.json()
      setPortfolio(data)
    } catch (error) {
      console.error("Erro ao buscar portfólio:", error)
    }

    // Datas base para cálculos mensais
    const today = new Date()
    const currentMonth = today.getMonth() + 1
    const currentYear = today.getFullYear()
    let nextMonth = currentMonth + 1
    let nextYear = currentYear
    if (nextMonth > 12) { nextMonth = 1; nextYear++ }

    // 2. Busca Transações Bancárias e agrupa por Categoria
    const { data: transData } = await supabase.from('transactions').select('*')
    if (transData) {
      // Saldo da conta
      const calcBalance = transData.reduce((acc, curr) => curr.type === 'INCOME' ? acc + parseFloat(curr.amount) : acc - parseFloat(curr.amount), 0)
      setBankBalance(calcBalance)

      // Calcula despesas do mês atual por categoria
      const currentMonthExpenses = transData.filter(t => {
        if (t.type !== 'EXPENSE') return false
        const [year, month] = t.date.split('-') // Formato YYYY-MM-DD
        return parseInt(month) === currentMonth && parseInt(year) === currentYear
      })

      const categoryTotals = {}
      CATEGORIES.forEach(c => categoryTotals[c] = 0)

      currentMonthExpenses.forEach(t => {
        // Se a categoria da transação não estiver na lista (dados antigos), joga para 'Outros'
        const cat = CATEGORIES.includes(t.category) ? t.category : 'Outros'
        categoryTotals[cat] += parseFloat(t.amount)
      })

      const chartDataExpenses = Object.keys(categoryTotals)
        .filter(k => categoryTotals[k] > 0)
        .map(k => ({ name: k, value: categoryTotals[k] }))
      
      setExpensesByCategory(chartDataExpenses)
    }

    // 3. Busca Faturas do Cartão para o Próximo Mês
    const { data: ccData } = await supabase.from('cc_expenses').select('amount, invoice_month, invoice_year, status').eq('status', 'OPEN')
    if (ccData) {
      const nextMonthTotal = ccData
        .filter(exp => exp.invoice_month === nextMonth && exp.invoice_year === nextYear)
        .reduce((acc, curr) => acc + parseFloat(curr.amount), 0)
      setNextMonthInvoice(nextMonthTotal)
    }
  }

  if (!portfolio) return <div className="text-slate-500 animate-pulse p-8">Calculando painel financeiro...</div>

  const totalWealth = bankBalance + portfolio.current_balance;
  const invChartData = Object.keys(portfolio.distribution || {}).map(key => ({ name: key, value: portfolio.distribution[key] }))
  const INV_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6']

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      <div>
        <h1 className="text-3xl font-bold text-slate-800">Visão Geral</h1>
        <p className="text-slate-500 mt-1">Seu patrimônio, faturas futuras e despesas por categoria.</p>
      </div>
      
      {/* Cards Superiores */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div className="bg-slate-900 p-6 rounded-2xl shadow-lg border border-slate-800 flex items-center gap-4">
          <div className="bg-blue-500 p-3 rounded-xl text-white"><Landmark size={24} /></div>
          <div>
            <h3 className="text-xs font-medium text-slate-300">Patrimônio Total</h3>
            <p className="text-xl font-bold text-white">R$ {totalWealth.toFixed(2)}</p>
          </div>
        </div>

        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 flex items-center gap-4">
          <div className="bg-slate-100 p-3 rounded-xl text-slate-600"><Wallet size={24}/></div>
          <div>
            <h3 className="text-xs font-medium text-slate-500">Saldo em Conta</h3>
            <p className={`text-xl font-bold ${bankBalance >= 0 ? 'text-slate-900' : 'text-red-500'}`}>R$ {bankBalance.toFixed(2)}</p>
          </div>
        </div>

        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 flex items-center gap-4">
          <div className="bg-blue-50 p-3 rounded-xl text-blue-600"><PiggyBank size={24}/></div>
          <div>
            <h3 className="text-xs font-medium text-slate-500">Investimentos</h3>
            <p className="text-xl font-bold text-blue-600">R$ {portfolio.current_balance}</p>
          </div>
        </div>

        {/* NOVO CARTÃO: Fatura Próximo Mês */}
        <div className="bg-red-50 p-6 rounded-2xl shadow-sm border border-red-100 flex items-center gap-4">
          <div className="bg-red-100 p-3 rounded-xl text-red-600"><CreditCard size={24}/></div>
          <div>
            <h3 className="text-xs font-medium text-red-800">Fatura Próximo Mês</h3>
            <p className="text-xl font-bold text-red-600">R$ {nextMonthInvoice.toFixed(2)}</p>
          </div>
        </div>
      </div>

      {/* Seção de Gráficos */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* Gráfico 1: Despesas por Categoria (Mês Atual) */}
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100">
          <h2 className="text-lg font-bold text-slate-800 mb-6">Despesas do Mês por Categoria</h2>
          {expensesByCategory.length > 0 ? (
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={expensesByCategory} innerRadius={70} outerRadius={90} paddingAngle={5} dataKey="value">
                    {expensesByCategory.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={CATEGORY_COLORS[CATEGORIES.indexOf(entry.name)] || '#64748b'} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => `R$ ${value.toFixed(2)}`} />
                  <Legend verticalAlign="bottom" height={36}/>
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
             <div className="h-72 flex flex-col items-center justify-center text-slate-400">
               <p>Nenhuma despesa lançada neste mês.</p>
             </div>
          )}
        </div>

        {/* Gráfico 2: Distribuição de Investimentos */}
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-lg font-bold text-slate-800">Distribuição da Carteira</h2>
            <span className={`px-3 py-1 rounded-full text-xs font-bold ${portfolio.portfolio_profitability >= 0 ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
              Rentabilidade: {portfolio.portfolio_profitability > 0 ? '+' : ''}{portfolio.portfolio_profitability}%
            </span>
          </div>
          {invChartData.length > 0 ? (
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={invChartData} innerRadius={70} outerRadius={90} paddingAngle={5} dataKey="value">
                    {invChartData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={INV_COLORS[index % INV_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => `${value}%`} />
                  <Legend verticalAlign="bottom" height={36}/>
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
             <div className="h-72 flex items-center justify-center text-slate-400">Nenhum ativo cadastrado.</div>
          )}
        </div>

      </div>
    </div>
  )
}