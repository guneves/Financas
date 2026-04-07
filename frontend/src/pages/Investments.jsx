import { useState, useEffect } from 'react'
import { supabase } from '../lib/supabaseClient'
import { RefreshCw, TrendingUp, Landmark } from 'lucide-react'

export default function Investments() {
  // Estado para controlar a aba atual
  const [activeTab, setActiveTab] = useState('VARIAVEL')

  const [assets, setAssets] = useState(() => {
    const savedAssets = localStorage.getItem('@financeMVP:assets');
    return savedAssets ? JSON.parse(savedAssets) : [];
  });
  const [loading, setLoading] = useState(false)

  //formulario
  const [form, setForm] = useState({ 
    asset_class: 'STOCKS', 
    ticker_or_name: '', 
    quantity: '', 
    average_price: '',
    cdi_percentage: '',
    purchase_date: ''
  })
  
  const [isUpdatingPrices, setIsUpdatingPrices] = useState(false)

  const handleUpdateStockPrices = async () => {
    setIsUpdatingPrices(true)
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) return;
      
      const response = await fetch('http://localhost:5000/api/investments/update-prices', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${session.access_token}`,
          'Content-Type': 'application/json'
        }
      })

      if (response.ok) {
        const data = await response.json()
        alert(`Sucesso! ${data.updated_count} cotações foram atualizadas.`)
        fetchPortfolio() // Recarrega a tabela
      } else {
        alert("Erro ao atualizar cotações. Verifique o terminal do backend.")
      }
    } catch (error) {
      console.error("Erro ao atualizar preços:", error)
      alert("Erro de conexão ao tentar atualizar os preços.")
    } finally {
      setIsUpdatingPrices(false)
    }
  }

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
      
      const fetchedAssets = data.assets || [];
      
      setAssets(fetchedAssets)
      
      localStorage.setItem('@financeMVP:assets', JSON.stringify(fetchedAssets));
      
    } catch (error) {
      console.error("Erro ao buscar portfólio:", error)
    }
  }

const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    const { data: { user } } = await supabase.auth.getUser()

    // 1. Padroniza o nome para maiúsculo (evita criar linhas separadas para "petr4" e "PETR4")
    const tickerName = form.ticker_or_name.trim().toUpperCase();

    // 2. Procura se você já tem esse ativo na carteira
    const existingAsset = assets.find(a => a.ticker === tickerName);
    
    // 3. Se já existir, a nova compra herda a cotação de mercado atual.
    // Se for um ativo novo, a cotação atual começa igual ao preço da compra.
    const marketPrice = existingAsset ? existingAsset.current_price : parseFloat(form.average_price);

    // Prepara as métricas específicas
    let metadata = null;
    if (form.asset_class === 'FIXED_INCOME' && form.cdi_percentage && form.purchase_date) {
        metadata = { 
          cdi_percentage: (parseFloat(form.cdi_percentage) / 100),
          purchase_date: form.purchase_date
        };
    }

    const { error } = await supabase.from('investments').insert([
      { 
        user_id: user.id, 
        asset_class: form.asset_class,
        ticker_or_name: tickerName,
        quantity: parseFloat(form.quantity),
        average_price: parseFloat(form.average_price),
        current_price: marketPrice, //Mantém a cotação
        metadata: metadata
      }
    ])

    if (!error) {
      // Limpa os campos mantendo a classe do ativo atual
      if (activeTab === 'VARIAVEL') {
        setForm({ asset_class: 'STOCKS', ticker_or_name: '', quantity: '', average_price: '', purchase_date: '' })
      } else {
        setForm({ asset_class: 'FIXED_INCOME', ticker_or_name: '', quantity: '', average_price: '', mortality_rate: '', cdi_percentage: '', purchase_date: '' })
      }
      fetchPortfolio() 
    } else {
      alert("Erro ao adicionar aporte: " + error.message)
    }
    setLoading(false)
  }

  const handleDelete = async (id) => {
    const { error } = await supabase.from('investments').delete().eq('id', id)
    if (!error) fetchPortfolio()
  }

  const getClassLabel = (assetClass) => {
    const labels = {
      'STOCKS': 'Ações',
      'FIXED_INCOME': 'Renda Fixa',
      'REIT': 'Fundos Imobiliários',
      'ETF': 'ETFs',
      'OTHER': 'Outros'
    }
    return labels[assetClass] || assetClass
  }

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      
      {/* CABEÇALHO */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-800">Meus Investimentos</h1>
          <p className="text-slate-500 mt-1">Adicione novos ativos e acompanhe sua rentabilidade.</p>
        </div>
        
        <button
          onClick={handleUpdateStockPrices}
          disabled={isUpdatingPrices}
          className="bg-slate-800 hover:bg-slate-900 text-white px-4 py-2.5 rounded-lg shadow-sm flex items-center justify-center gap-2 disabled:opacity-50 transition"
        >
          {isUpdatingPrices ? (
            <span>Atualizando...</span>
          ) : (
            <>
              <RefreshCw size={18} />
              <span>Sincronizar Cotações</span>
            </>
          )}
        </button>
      </div>

      {/* Seletor de Abas */}
      <div className="flex bg-slate-200 p-1 rounded-lg w-fit">
        <button 
          onClick={() => {
            setActiveTab('VARIAVEL');
            setForm({...form, asset_class: 'STOCKS', ticker_or_name: '', quantity: '', average_price: ''});
          }} 
          className={`px-4 py-2 rounded-md font-medium transition flex items-center gap-2 ${activeTab === 'VARIAVEL' ? 'bg-white shadow-sm text-blue-600' : 'text-slate-600 hover:bg-slate-300'}`}
        >
          <TrendingUp size={18}/> Variável & Outros
        </button>
        <button 
          onClick={() => {
            setActiveTab('FIXA');
            setForm({...form, asset_class: 'FIXED_INCOME', ticker_or_name: '', quantity: '1', average_price: ''});
          }} 
          className={`px-4 py-2 rounded-md font-medium transition flex items-center gap-2 ${activeTab === 'FIXA' ? 'bg-white shadow-sm text-blue-600' : 'text-slate-600 hover:bg-slate-300'}`}
        >
          <Landmark size={18}/> Renda Fixa (CDI)
        </button>
      </div>
      
      {/* Renda Variavel */}
      {activeTab === 'VARIAVEL' && (
        <form onSubmit={handleSubmit} className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 grid grid-cols-1 md:grid-cols-5 gap-4 items-end animate-in fade-in slide-in-from-bottom-4 duration-500">
          <div className="flex flex-col space-y-1">
            <label className="text-sm text-slate-500 font-medium">Classe do Ativo</label>
            <select value={form.asset_class} onChange={e => setForm({...form, asset_class: e.target.value})} className="p-2 border border-slate-300 rounded-lg bg-white" required>
              <option value="STOCKS">Ações</option>
              <option value="REIT">Fundos Imobiliários</option>
              <option value="ETF">ETFs</option>
              <option value="OTHER">Outros</option>
            </select>
          </div>

          <div className="flex flex-col space-y-1">
            <label className="text-sm text-slate-500 font-medium">Nome / Ticker</label>
            <input type="text" placeholder="Ex: PETR4, Lote Nelore" value={form.ticker_or_name} onChange={e => setForm({...form, ticker_or_name: e.target.value})} className="p-2 border border-slate-300 rounded-lg" required />
          </div>

          <div className="flex flex-col space-y-1">
            <label className="text-sm text-slate-500 font-medium">Quantidade</label>
            <input type="number" step="0.0001" placeholder="Ex: 100" value={form.quantity} onChange={e => setForm({...form, quantity: e.target.value})} className="p-2 border border-slate-300 rounded-lg" required />
          </div>

          <div className="flex flex-col space-y-1">
            <label className="text-sm text-slate-500 font-medium">Preço de Compra (R$)</label>
            <input type="number" step="0.01" placeholder="Ex: 35.50" value={form.average_price} onChange={e => setForm({...form, average_price: e.target.value})} className="p-2 border border-slate-300 rounded-lg" required />
          </div>

          <button type="submit" disabled={loading} className="md:col-span-5 bg-blue-600 text-white rounded-lg py-2.5 font-medium hover:bg-blue-700 transition">
            {loading ? 'Adicionando...' : 'Adicionar Ativo'}
          </button>
        </form>
      )}

      {/* Renda Fixa */}
      {activeTab === 'FIXA' && (
        <form onSubmit={handleSubmit} className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 grid grid-cols-1 md:grid-cols-4 gap-4 items-end animate-in fade-in slide-in-from-bottom-4 duration-500">
          <div className="flex flex-col space-y-1">
            <label className="text-sm text-slate-500 font-medium">Nome do Ativo</label>
            <input type="text" placeholder="Ex: CDB Banco Inter" value={form.ticker_or_name} onChange={e => setForm({...form, ticker_or_name: e.target.value})} className="p-2 border border-slate-300 rounded-lg" required />
          </div>

          <div className="flex flex-col space-y-1">
            <label className="text-sm text-slate-500 font-medium">Valor Aplicado (R$)</label>
            <input type="number" step="0.01" placeholder="Ex: 1000.00" value={form.average_price} onChange={e => setForm({...form, average_price: e.target.value})} className="p-2 border border-slate-300 rounded-lg" required />
          </div>

          <div className="flex flex-col space-y-1">
            <label className="text-sm text-slate-500 font-medium">% do CDI</label>
            <input type="number" step="0.1" placeholder="Ex: 110" value={form.cdi_percentage} onChange={e => setForm({...form, cdi_percentage: e.target.value})} className="p-2 border border-slate-300 rounded-lg" required />
          </div>

          <div className="flex flex-col space-y-1">
            <label className="text-sm text-slate-500 font-medium">Data da Aplicação</label>
            <input type="date" value={form.purchase_date} onChange={e => setForm({...form, purchase_date: e.target.value})} className="p-2 border border-slate-300 rounded-lg" required />
          </div>

          <button type="submit" disabled={loading} className="md:col-span-4 bg-blue-600 text-white rounded-lg py-2.5 font-medium hover:bg-blue-700 transition">
            {loading ? 'Adicionando...' : 'Adicionar à Renda Fixa'}
          </button>
        </form>
      )}

      {/* Tabela de Posições */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-x-auto">
        <table className="w-full text-left border-collapse min-w-max">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100 text-slate-600 text-sm">
              <th className="p-4 font-medium">Ativo</th>
              <th className="p-4 font-medium">Qtd Total</th>
              <th className="p-4 font-medium">Preço Médio</th>
              <th className="p-4 font-medium text-blue-600">Cotação Atual (Editar)</th>
              <th className="p-4 font-medium">Valor Total</th>
              <th className="p-4 font-medium">Rentabilidade</th>
              <th className="p-4 font-medium text-right">Ações</th>
            </tr>
          </thead>
          <tbody>
            {assets.map(asset => (
              <tr key={asset.ticker} className="border-b border-slate-50 hover:bg-slate-50 transition">
                <td className="p-4">
                  <p className="font-bold text-slate-800">{asset.name}</p>
                  <p className="text-xs text-slate-500">{getClassLabel(asset.class)}</p>
                </td>
                <td className="p-4 text-slate-800">
                  {asset.class === 'FIXED_INCOME' ? '-' : asset.quantity}
                </td>
                <td className="p-4 text-slate-800">R$ {asset.average_price.toFixed(2)}</td>
                <td className="p-4">
                  <div className="flex items-center gap-1">
                    <span className="text-slate-500">R$</span>
                    <input 
                      type="number" 
                      step="0.01"
                      defaultValue={asset.current_price} 
                      disabled={asset.class === 'FIXED_INCOME'} // Desabilita edição manual se for CDI
                      onBlur={async (e) => {
                        const newPrice = e.target.value;
                        if(newPrice && newPrice !== asset.current_price.toString()){
                          const { data: { user } } = await supabase.auth.getUser()
                          await supabase.from('investments')
                            .update({ current_price: parseFloat(newPrice) })
                            .eq('ticker_or_name', asset.ticker)
                            .eq('user_id', user.id)
                          fetchPortfolio(); 
                        }
                      }}
                      className={`w-28 p-1.5 border border-blue-200 rounded-md transition ${asset.class === 'FIXED_INCOME' ? 'bg-slate-100 text-slate-500 cursor-not-allowed border-slate-200' : 'bg-blue-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500'}`}
                      title={asset.class === 'FIXED_INCOME' ? "Cotação calculada automaticamente pelo CDI" : "Digite o novo preço e clique fora para salvar"}
                    />
                  </div>
                </td>
                <td className="p-4 font-medium text-slate-800">R$ {asset.current_value.toFixed(2)}</td>
                <td className="p-4">
                  <span className={`px-2 py-1 rounded-full text-xs font-bold ${asset.profitability_percent >= 0 ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                    {asset.profitability_percent > 0 ? '+' : ''}{asset.profitability_percent}%
                  </span>
                </td>
                <td className="p-4 text-right">
                  <button onClick={async () => {
                    if(window.confirm(`Tem certeza que deseja excluir TODA a posição de ${asset.ticker}?`)){
                      const { data: { user } } = await supabase.auth.getUser()
                      await supabase.from('investments').delete().eq('ticker_or_name', asset.ticker).eq('user_id', user.id)
                      fetchPortfolio();
                    }
                  }} className="text-red-400 hover:text-red-600 text-sm font-medium transition">Excluir</button>
                </td>
              </tr>
            ))}
            {assets.length === 0 && (
              <tr><td colSpan="7" className="p-8 text-center text-slate-500">Nenhum ativo cadastrado.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}