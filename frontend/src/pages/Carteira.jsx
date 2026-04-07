import { useEffect, useMemo, useState } from 'react'
import { supabase } from '../lib/supabaseClient'
import {
  TrendingUp,
  Wallet,
  Landmark,
  BarChart3,
  PieChart as PieChartIcon,
  ChevronDown,
  CircleDollarSign,
  ChevronUp,
} from 'lucide-react'
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  PieChart,
  Pie,
  Cell,
} from 'recharts'

const TYPE_OPTIONS = ['TODOS', 'STOCKS', 'FIXED_INCOME', 'REIT', 'OTHER']
const MONTH_OPTIONS = [6, 12, 24]
const CHART_COLORS = ['#3b82f6', '#67e8f9', '#facc15', '#fb923c', '#a78bfa']

const currency = (value) =>
  new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Number(value || 0))

const percent = (value) => `${Number(value || 0).toFixed(2).replace('.', ',')}%`

const monthLabel = (date) =>
  new Intl.DateTimeFormat('pt-BR', { month: '2-digit', year: '2-digit' }).format(date)

const movementDate = (movement) => {
  const purchaseDate = movement?.metadata?.purchase_date
  if (purchaseDate) return new Date(`${purchaseDate}T00:00:00`)
  return new Date(movement.created_at)
}

const classLabel = (assetClass) => {
  const labels = {
    STOCKS: 'Ações',
    FIXED_INCOME: 'Renda Fixa',
    REIT: 'Tesouro Direto',
    OTHER: 'ETFs',
    TODOS: 'Todos os tipos',
  }
  return labels[assetClass] || assetClass
}

export default function Carteira() {
  const [portfolio, setPortfolio] = useState(null)
  const [assets, setAssets] = useState([])
  const [movements, setMovements] = useState([])
  const [monthsFilter, setMonthsFilter] = useState(12)
  const [typeFilter, setTypeFilter] = useState('TODOS')
  const [openGroups, setOpenGroups] = useState({})

  useEffect(() => {
    fetchPortfolio()
    fetchMovements()
  }, [])

  const fetchPortfolio = async () => {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session) return

    try {
      const response = await fetch('http://localhost:5000/api/investments/portfolio', {
        headers: { Authorization: `Bearer ${session.access_token}` },
      })
      const data = await response.json()
      setPortfolio(data)
      setAssets(data.assets || [])
    } catch (error) {
      console.error('Erro ao buscar carteira:', error)
    }
  }

  const fetchMovements = async () => {
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return

    const { data, error } = await supabase
      .from('investments')
      .select('*')
      .eq('user_id', user.id)
      .order('created_at', { ascending: true })

    if (!error && data) {
      setMovements(data)
    }
  }

  const filteredAssets = useMemo(() => {
    if (typeFilter === 'TODOS') return assets
    return assets.filter(asset => asset.class === typeFilter)
  }, [assets, typeFilter])

  const summary = useMemo(() => {
    const invested = filteredAssets.reduce((acc, asset) => acc + Number(asset.average_price || 0) * (asset.class === 'FIXED_INCOME' ? 1 : Number(asset.quantity || 0)), 0)
    const current = filteredAssets.reduce((acc, asset) => acc + Number(asset.current_value || 0), 0)
    const net = filteredAssets.reduce((acc, asset) => acc + Number(asset.net_value || asset.current_value || 0), 0)
    const profit = current - invested
    const profitability = invested > 0 ? (profit / invested) * 100 : 0

    return { invested, current, net, profit, profitability }
  }, [filteredAssets])

  const pieData = useMemo(() => {
    return filteredAssets
      .reduce((acc, asset) => {
        const found = acc.find(item => item.name === classLabel(asset.class))
        if (found) {
          found.value += Number(asset.current_value || 0)
        } else {
          acc.push({ name: classLabel(asset.class), value: Number(asset.current_value || 0) })
        }
        return acc
      }, [])
      .filter(item => item.value > 0)
  }, [filteredAssets])

  const groupedRows = useMemo(() => {
    const groups = {}

    filteredAssets.forEach(asset => {
      const key = classLabel(asset.class)
      if (!groups[key]) {
        groups[key] = {
          name: key,
          assetCount: 0,
          invested: 0,
          current: 0,
          net: 0,
          profit: 0,
          profitability: 0,
          items: [],
        }
      }

      const invested = Number(asset.average_price || 0) * (asset.class === 'FIXED_INCOME' ? 1 : Number(asset.quantity || 0))
      const current = Number(asset.current_value || 0)
      const net = Number(asset.net_value || asset.current_value || 0)

      groups[key].assetCount += 1
      groups[key].invested += invested
      groups[key].current += current
      groups[key].net += net
      groups[key].items.push(asset)
    })

    return Object.values(groups)
      .map(group => {
        const profit = group.current - group.invested
        const profitability = group.invested > 0 ? (profit / group.invested) * 100 : 0
        const share = summary.current > 0 ? (group.current / summary.current) * 100 : 0
        return { ...group, profit, profitability, share }
      })
      .sort((a, b) => b.current - a.current)
  }, [filteredAssets, summary.current])

  const evolutionData = useMemo(() => {
    const months = []
    const now = new Date()
    const start = new Date(now.getFullYear(), now.getMonth() - (monthsFilter - 1), 1)

    for (let i = 0; i < monthsFilter; i++) {
      months.push(new Date(start.getFullYear(), start.getMonth() + i, 1))
    }

    const relevantMovements = movements.filter(mov => {
      const movDate = movementDate(mov)
      if (typeFilter !== 'TODOS' && mov.asset_class !== typeFilter) return false
      return movDate >= start
    })

    let investedAccumulated = 0
    const totalInvested = summary.invested
    const totalProfit = summary.profit

    return months.map((month) => {
      relevantMovements.forEach(mov => {
        const movDate = movementDate(mov)
        if (
          movDate.getFullYear() === month.getFullYear() &&
          movDate.getMonth() === month.getMonth()
        ) {
          const quantity = Number(mov.quantity || 0)
          const average = Number(mov.average_price || 0)
          const amount = Math.abs(quantity * average)
          if (quantity > 0) investedAccumulated += amount
          if (quantity < 0 && mov.asset_class !== 'FIXED_INCOME') investedAccumulated -= amount
        }
      })

      const allocatedProfit = totalInvested > 0 ? (Math.max(investedAccumulated, 0) / totalInvested) * totalProfit : 0

      return {
        month: monthLabel(month),
        valorAplicado: Math.max(investedAccumulated, 0),
        ganhoCapital: Math.max(allocatedProfit, 0),
      }
    })
  }, [movements, monthsFilter, typeFilter, summary.invested, summary.profit])

  const toggleGroup = (groupName) => {
    setOpenGroups((prev) => ({
      ...prev,
      [groupName]: !prev[groupName],
    }))
  }

  if (!portfolio) {
    return <div className="text-slate-500 animate-pulse p-8">Carregando carteira...</div>
  }

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-slate-800">Carteira</h1>
        <p className="text-slate-500 mt-1">Acompanhe a evolução do patrimônio e a composição atual dos seus ativos.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
        <MetricCard
          icon={Wallet}
          title="Patrimônio total"
          value={currency(summary.current)}
          footLabel="Valor investido"
          footValue={currency(summary.invested)}
          badge={percent(summary.profitability)}
          positive={summary.profitability >= 0}
        />
        <MetricCard
          icon={CircleDollarSign}
          title="Lucro total"
          value={currency(summary.profit)}
          footLabel="Ganho de capital"
          footValue={currency(summary.profit)}
          positive={summary.profit >= 0}
        />
        <MetricCard
          icon={Landmark}
          title="Saldo líquido estimado"
          value={currency(summary.net)}
          footLabel="Diferença líquida"
          footValue={currency(summary.net - summary.invested)}
          positive={summary.net - summary.invested >= 0}
        />
        <MetricCard
          icon={TrendingUp}
          title="Rentabilidade"
          value={percent(summary.profitability)}
          footLabel="Variação em reais"
          footValue={currency(summary.profit)}
          positive={summary.profitability >= 0}
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-5 gap-6">
        <div className="xl:col-span-3 bg-white rounded-2xl shadow-sm border border-slate-100 p-6">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-6">
            <h2 className="text-lg font-bold text-slate-800">Evolução do Patrimônio</h2>
            <div className="flex gap-3 flex-wrap">
              <SelectBox
                icon={BarChart3}
                value={monthsFilter}
                onChange={(e) => setMonthsFilter(Number(e.target.value))}
                options={MONTH_OPTIONS.map(value => ({ value, label: `${value} meses` }))}
              />
              <SelectBox
                icon={CircleDollarSign}
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                options={TYPE_OPTIONS.map(value => ({ value, label: classLabel(value) }))}
              />
            </div>
          </div>

          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={evolutionData} barGap={6}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="month" tick={{ fill: '#64748b', fontSize: 12 }} />
                <YAxis tickFormatter={(value) => value.toLocaleString('pt-BR')} tick={{ fill: '#64748b', fontSize: 12 }} />
                <Tooltip formatter={(value) => currency(value)} />
                <Bar dataKey="valorAplicado" name="Valor aplicado" radius={[8, 8, 0, 0]} fill="#38b86e" />
                <Bar dataKey="ganhoCapital" name="Ganho capital" radius={[8, 8, 0, 0]} fill="#9ae6b4" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="xl:col-span-2 bg-white rounded-2xl shadow-sm border border-slate-100 p-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
            <h2 className="text-lg font-bold text-slate-800">Ativos na Carteira</h2>
            <SelectBox
              icon={PieChartIcon}
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              options={TYPE_OPTIONS.map(value => ({ value, label: classLabel(value) }))}
            />
          </div>

          {pieData.length > 0 ? (
            <div className="space-y-6">
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={68} outerRadius={102} paddingAngle={3}>
                      {pieData.map((entry, index) => (
                        <Cell key={entry.name} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(value) => currency(value)} />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              <div className="space-y-3">
                {pieData.map((item, index) => {
                  const itemPercent = summary.current > 0 ? (item.value / summary.current) * 100 : 0
                  return (
                    <div key={item.name} className="flex items-center justify-between gap-4 text-sm">
                      <div className="flex items-center gap-3 text-slate-700 font-medium">
                        <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: CHART_COLORS[index % CHART_COLORS.length] }} />
                        {item.name}
                      </div>
                      <span className="text-slate-500">{percent(itemPercent)}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          ) : (
            <div className="h-64 flex items-center justify-center text-slate-400">Nenhum ativo cadastrado.</div>
          )}
        </div>
      </div>

      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <h2 className="text-2xl font-bold text-slate-800">Meus Ativos</h2>
          <span className="text-slate-400 font-semibold">({groupedRows.length})</span>
        </div>

        <div className="space-y-4">
          {groupedRows.map((group) => {
            const isOpen = !!openGroups[group.name]
            return (
              <div key={group.name} className="bg-white rounded-2xl border border-slate-100 shadow-sm px-6 py-5">
                <div className="grid grid-cols-1 lg:grid-cols-[1.6fr_repeat(5,1fr)_40px] gap-4 items-center">
                  <div className="flex items-center gap-4 min-w-0">
                    <div className="w-10 h-10 rounded-full border border-slate-200 bg-slate-50 flex items-center justify-center text-slate-700 font-bold">
                      {group.name[0]}
                    </div>
                    <div>
                      <h3 className="text-2xl font-semibold text-slate-800 leading-none">{group.name}</h3>
                    </div>
                  </div>

                  <InfoColumn label="Ativos" value={String(group.assetCount)} />
                  <InfoColumn label="Valor total" value={currency(group.current)} />
                  <InfoColumn label="Variação" value={percent(group.profitability)} positive={group.profitability >= 0} />
                  <InfoColumn label="Rentabilidade" value={percent(group.profitability)} positive={group.profitability >= 0} />
                  <InfoColumn label="% na carteira" value={percent(group.share)} mutedSecondary={currency(group.profit)} />

                  <button onClick={() => toggleGroup(group.name)} className="w-9 h-9 rounded-full bg-slate-100 text-slate-400 hover:bg-slate-200 transition flex items-center justify-center">
                    {isOpen ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                  </button>
                </div>

                {isOpen && (
                  <div className="mt-5 border-t border-slate-100 pt-4 overflow-x-auto">
                    <table className="w-full min-w-[720px] text-left">
                      <thead>
                        <tr className="text-sm text-slate-500 border-b border-slate-100">
                          <th className="pb-3 font-medium">Ativo</th>
                          <th className="pb-3 font-medium">Quantidade</th>
                          <th className="pb-3 font-medium">Preço médio</th>
                          <th className="pb-3 font-medium">Valor atual</th>
                          <th className="pb-3 font-medium">Rentabilidade</th>
                        </tr>
                      </thead>
                      <tbody>
                        {group.items.map((asset) => (
                          <tr key={asset.id} className="border-b border-slate-50 last:border-0">
                            <td className="py-3 font-medium text-slate-800">{asset.name}</td>
                            <td className="py-3 text-slate-600">{asset.class === 'FIXED_INCOME' ? '-' : asset.quantity}</td>
                            <td className="py-3 text-slate-600">{currency(asset.average_price)}</td>
                            <td className="py-3 text-slate-800 font-medium">{currency(asset.current_value)}</td>
                            <td className="py-3">
                              <span className={`px-2 py-1 rounded-full text-xs font-bold ${asset.profitability_percent >= 0 ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                                {asset.profitability_percent > 0 ? '+' : ''}{asset.profitability_percent}%
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )
          })}

          {groupedRows.length === 0 && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-10 text-center text-slate-500">
              Nenhum ativo encontrado para este filtro.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function MetricCard({ icon: Icon, title, value, footLabel, footValue, badge, positive = true }) {
  return (
    <div className="bg-white border border-slate-100 rounded-2xl shadow-sm p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3 min-w-0">
          <div className="w-10 h-10 rounded-xl bg-slate-50 flex items-center justify-center text-slate-500 border border-slate-100">
            <Icon size={18} />
          </div>
          <div>
            <p className="text-sm text-slate-600 font-medium">{title}</p>
            <div className="flex items-center gap-2 mt-2 flex-wrap">
              <p className={`text-2xl font-bold ${positive ? 'text-emerald-600' : 'text-rose-500'}`}>{value}</p>
              {badge && (
                <span className={`px-2.5 py-1 rounded-full text-sm font-semibold ${positive ? 'bg-emerald-50 text-emerald-600' : 'bg-rose-50 text-rose-500'}`}>
                  {badge}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>
      <div className="mt-3 text-sm text-slate-500">
        <p>{footLabel}</p>
        <p className="font-semibold text-slate-700">{footValue}</p>
      </div>
    </div>
  )
}

function SelectBox({ icon: Icon, value, onChange, options }) {
  return (
    <div className="relative">
      <div className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
        <Icon size={16} />
      </div>
      <select
        value={value}
        onChange={onChange}
        className="appearance-none bg-white border border-slate-200 rounded-xl pl-10 pr-10 py-2.5 text-sm font-medium text-slate-700 shadow-sm"
      >
        {options.map(option => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
      <div className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
        <ChevronDown size={16} />
      </div>
    </div>
  )
}

function InfoColumn({ label, value, positive, mutedSecondary }) {
  const colorClass = positive === undefined ? 'text-slate-800' : positive ? 'text-emerald-600' : 'text-rose-500'

  return (
    <div>
      <p className="text-sm text-slate-500">{label}</p>
      <p className={`text-xl font-semibold ${colorClass}`}>{value}</p>
      {mutedSecondary && <p className="text-sm text-slate-400 mt-1">{mutedSecondary}</p>}
    </div>
  )
}
