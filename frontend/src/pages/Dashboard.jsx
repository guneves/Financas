import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabaseClient'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import { TrendingUp, DollarSign, Activity } from 'lucide-react'

export default function Dashboard() {
  const [portfolio, setPortfolio] = useState(null)
  
  useEffect(() => {
    fetchPortfolio()
  }, [])

  const fetchPortfolio = async () => {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session) return

    try {
      const response = await fetch('http://localhost:5000/api/investments/portfolio', {
        headers: { 'Authorization': `Bearer ${session.access_token}` }
      })
      const data = await response.json()
      setPortfolio(data)
    } catch (error) {
      console.error("Erro ao buscar dados:", error)
    }
  }

  if (!portfolio) return <div className="text-slate-500 animate-pulse">Calculando métricas...</div>

  // Preparar dados para o gráfico
  const chartData = Object.keys(portfolio.distribution || {}).map(key => ({
    name: key,
    value: portfolio.distribution[key]
  }))
  const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6']

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      <div>
        <h1 className="text-3xl font-bold text-slate-800">Visão Geral</h1>
        <p className="text-slate-500 mt-1">Acompanhe a evolução do seu patrimônio e despesas.</p>
      </div>
      
      {/* Cards Superiores */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 flex items-center gap-4">
          <div className="bg-slate-100 p-4 rounded-xl text-slate-600"><DollarSign /></div>
          <div>
            <h3 className="text-sm font-medium text-slate-500">Total Investido</h3>
            <p className="text-2xl font-bold text-slate-900">R$ {portfolio.total_invested}</p>
          </div>
        </div>

        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 flex items-center gap-4">
          <div className="bg-blue-50 p-4 rounded-xl text-blue-600"><Activity /></div>
          <div>
            <h3 className="text-sm font-medium text-slate-500">Saldo Atual (Patrimônio)</h3>
            <p className="text-2xl font-bold text-blue-600">R$ {portfolio.current_balance}</p>
          </div>
        </div>

        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 flex items-center gap-4">
          <div className={`p-4 rounded-xl ${portfolio.portfolio_profitability >= 0 ? 'bg-green-50 text-green-600' : 'bg-red-50 text-red-600'}`}>
            <TrendingUp />
          </div>
          <div>
            <h3 className="text-sm font-medium text-slate-500">Rentabilidade Global</h3>
            <p className={`text-2xl font-bold ${portfolio.portfolio_profitability >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              {portfolio.portfolio_profitability}%
            </p>
          </div>
        </div>
      </div>

      {/* Gráficos e Tabelas */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100">
          <h2 className="text-lg font-bold text-slate-800 mb-6">Distribuição da Carteira</h2>
          {chartData.length > 0 ? (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={chartData} innerRadius={60} outerRadius={80} paddingAngle={5} dataKey="value">
                    {chartData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => `${value}%`} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
             <div className="h-64 flex items-center justify-center text-slate-400">Nenhum ativo cadastrado.</div>
          )}
        </div>
      </div>
    </div>
  )
}