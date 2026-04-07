import { useState, useEffect } from 'react'
import { supabase } from '../lib/supabaseClient'
import { RefreshCw, TrendingUp, Landmark, History, X } from 'lucide-react'

export default function Investments() {
  const [activeTab, setActiveTab] = useState('VARIAVEL')

  const [assets, setAssets] = useState(() => {
    const savedAssets = localStorage.getItem('@financeMVP:assets');
    return savedAssets ? JSON.parse(savedAssets) : [];
  });
  
  const [movements, setMovements] = useState([]);
  const [loading, setLoading] = useState(false)

  const [form, setForm] = useState({ 
    asset_class: 'STOCKS', 
    ticker_or_name: '', 
    quantity: '', 
    average_price: '',
    cdi_percentage: '',
    purchase_date: '',
    is_tax_free: false
  })

  const [editModal, setEditModal] = useState(null)
  const [isUpdatingPrices, setIsUpdatingPrices] = useState(false)

  const handleUpdateStockPrices = async (silent = false, investmentId = null) => {
    setIsUpdatingPrices(true)
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) return;
      
      const payload = investmentId ? { investment_id: investmentId } : {};
      
      const response = await fetch('http://localhost:5000/api/investments/update-prices', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${session.access_token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      })

      if (response.ok) {
        const data = await response.json()
        if (!silent) {
          alert(`Sucesso! ${data.updated_count} cotações foram atualizadas.`)
        }
        fetchPortfolio() 
      } else {
        if (!silent) alert("Erro ao atualizar cotações. Verifique o terminal do backend.")
      }
    } catch (error) {
      console.error("Erro ao atualizar preços:", error)
      if (!silent) alert("Erro de conexão ao tentar atualizar os preços.")
    } finally {
      setIsUpdatingPrices(false)
    }
  }

  useEffect(() => {
    fetchPortfolio()
    fetchMovements() 
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

  const fetchMovements = async () => {
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return

    const { data, error } = await supabase
      .from('investments')
      .select('*')
      .eq('user_id', user.id)
      .order('created_at', { ascending: false }) 

    if (!error && data) {
      setMovements(data)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const { data: { user }, error: userError } = await supabase.auth.getUser();
      if (userError || !user) throw new Error("Usuário não encontrado.");

      const tickerName = form.ticker_or_name.trim().toUpperCase();
      const existingAsset = assets.find(a => a.ticker === tickerName);
      const marketPrice = existingAsset ? existingAsset.current_price : parseFloat(form.average_price);
      
      const finalQuantity = form.asset_class === 'FIXED_INCOME' ? 1 : parseFloat(form.quantity);

      let metadata = null;
      if (form.asset_class === 'FIXED_INCOME' && form.cdi_percentage && form.purchase_date) {
          metadata = { 
            cdi_percentage: (parseFloat(form.cdi_percentage) / 100),
            purchase_date: form.purchase_date,
            is_tax_free: form.is_tax_free
          };
      }

      const { data: insertedData, error: insertError } = await supabase.from('investments').insert([
        { 
          user_id: user.id, 
          asset_class: form.asset_class,
          ticker_or_name: tickerName,
          quantity: finalQuantity,
          average_price: parseFloat(form.average_price),
          current_price: marketPrice,
          metadata: metadata
        }
      ]).select(); 

      if (insertError) throw new Error(insertError.message);

      if (activeTab === 'VARIAVEL') {
        setForm({ asset_class: 'STOCKS', ticker_or_name: '', quantity: '', average_price: '', cdi_percentage: '', purchase_date: '', is_tax_free: false });
      } else {
        setForm({ asset_class: 'FIXED_INCOME', ticker_or_name: '', quantity: '', average_price: '', cdi_percentage: '', purchase_date: '', is_tax_free: false });
      }
      
      fetchPortfolio(); 
      fetchMovements(); 

      if (insertedData && insertedData.length > 0) {
        await handleUpdateStockPrices(true, insertedData[0].id); 
      }

    } catch (error) {
      console.error("Erro crítico no envio:", error);
      alert("Falha ao adicionar: " + error.message);
    } finally {
      setLoading(false); 
    }
  };

  const openEditModal = (mov) => {
    setEditModal({
      id: mov.id,
      asset_class: mov.asset_class,
      ticker_or_name: mov.ticker_or_name,
      quantity: mov.quantity,
      average_price: mov.average_price,
      cdi_percentage: mov.metadata?.cdi_percentage ? (mov.metadata.cdi_percentage * 100).toFixed(1) : '',
      purchase_date: mov.metadata?.purchase_date || '',
      is_tax_free: mov.metadata?.is_tax_free || false
    });
  }

  const handleSaveEdit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      let metadata = null;
      if (editModal.asset_class === 'FIXED_INCOME') {
          metadata = { 
            cdi_percentage: (parseFloat(editModal.cdi_percentage) / 100),
            purchase_date: editModal.purchase_date,
            is_tax_free: editModal.is_tax_free
          };
      }

      const finalQuantity = editModal.asset_class === 'FIXED_INCOME' ? 1 : parseFloat(editModal.quantity);

      const { error } = await supabase.from('investments')
        .update({ 
          quantity: finalQuantity,
          average_price: parseFloat(editModal.average_price),
          metadata: metadata
        })
        .eq('id', editModal.id);

      if (error) throw new Error(error.message);

      setEditModal(null);
      fetchPortfolio(); 
      fetchMovements();
      
      await handleUpdateStockPrices(true, editModal.id);

    } catch (error) {
      alert("Erro ao guardar edição: " + error.message);
    } finally {
      setLoading(false);
    }
  }

  // ---- FUNÇÃO DE VENDA PARCIAL DE AÇÕES/FIIs ----
  const handleSellVariable = async (asset) => {
    const qtyStr = window.prompt(`VENDA DE ATIVO\nAtivo: ${asset.name}\nQuantidade Disponível: ${asset.quantity}\n\nQuantas cotas/ações você deseja vender?`);
    if (!qtyStr) return;
    
    const qtyToSell = parseFloat(qtyStr.replace(',', '.'));
    
    if (isNaN(qtyToSell) || qtyToSell <= 0 || qtyToSell > asset.quantity) {
      alert("Quantidade inválida. Digite um valor entre 0 e a quantidade total que você possui.");
      return;
    }

    if (qtyToSell === asset.quantity) {
      handleDeleteFullPosition(asset); 
      return;
    }

    setLoading(true);
    try {
      const { data: { user } } = await supabase.auth.getUser();

      // Registra uma nova movimentação com quantidade NEGATIVA.
      // Isso abate a quantidade e mantém o preço médio perfeitamente.
      const { error } = await supabase.from('investments').insert([
        { 
          user_id: user.id, 
          asset_class: asset.class,
          ticker_or_name: asset.ticker,
          quantity: -qtyToSell, 
          average_price: asset.average_price, 
          current_price: asset.current_price 
        }
      ]);

      if (error) throw new Error(error.message);

      alert("Venda registrada com sucesso!");
      fetchPortfolio();
      fetchMovements();
    } catch (error) {
      alert("Erro ao registrar venda: " + error.message);
    } finally {
      setLoading(false);
    }
  }

  const handlePartialSale = async (asset) => {
    if (asset.class !== 'FIXED_INCOME') return;

    const amountStr = window.prompt(`RESGATE PARCIAL\nAtivo: ${asset.name}\nValor Bruto Atual: R$ ${asset.current_value.toFixed(2)}\n\nQuanto você deseja resgatar (em R$)?`);
    if (!amountStr) return;
    
    const amount = parseFloat(amountStr.replace(',', '.'));
    
    if (isNaN(amount) || amount <= 0 || amount > asset.current_value) {
      alert("Valor inválido. Digite um valor entre R$ 0.01 e o valor total bruto.");
      return;
    }

    if (amount === asset.current_value) {
      handleDeleteFullPosition(asset); 
      return;
    }

    const ratio = amount / asset.current_value;
    const newAvgPrice = asset.average_price * (1 - ratio);
    const newCurrentPrice = asset.current_price * (1 - ratio);

    const { data: { user } } = await supabase.auth.getUser();

    const { error } = await supabase.from('investments')
      .update({ average_price: newAvgPrice, current_price: newCurrentPrice })
      .eq('id', asset.id)
      .eq('user_id', user.id);

    if (!error) {
      fetchPortfolio();
      fetchMovements();
      alert("Resgate parcial realizado com sucesso!");
    } else {
      alert("Erro ao realizar resgate: " + error.message);
    }
  }

  const handleDeleteMovement = async (id) => {
    if (window.confirm("Tem certeza que deseja excluir APENAS essa movimentação do histórico?")) {
      const { error } = await supabase.from('investments').delete().eq('id', id)
      if (!error) {
        fetchPortfolio()
        fetchMovements()
      } else {
        alert("Erro ao excluir movimentação: " + error.message)
      }
    }
  }

  const handleDeleteFullPosition = async (asset) => {
    if(window.confirm(`Tem certeza que deseja excluir ${asset.class === 'FIXED_INCOME' ? 'este aporte de' : 'TODA a posição de'} ${asset.name}?`)){
      const { data: { user } } = await supabase.auth.getUser()
      
      if (asset.class === 'FIXED_INCOME') {
        await supabase.from('investments').delete().eq('id', asset.id).eq('user_id', user.id)
      } else {
        await supabase.from('investments').delete().eq('ticker_or_name', asset.ticker).eq('user_id', user.id)
      }
      
      fetchPortfolio();
      fetchMovements();
    }
  }

  const getClassLabel = (assetClass) => {
    const labels = {
      'STOCKS': 'Ações',
      'FIXED_INCOME': 'Renda Fixa',
      'REIT': 'Fundos Imobiliários',
      'OTHER': 'Outros'
    }
    return labels[assetClass] || assetClass
  }

  // Lógica para filtrar a Tabela baseada na aba ativa
  const filteredAssets = assets.filter(asset => {
    if (activeTab === 'VARIAVEL') return asset.class !== 'FIXED_INCOME';
    if (activeTab === 'FIXA') return asset.class === 'FIXED_INCOME';
    return true;
  });

  return (
    <div className="max-w-5xl mx-auto space-y-8 relative">
      
      {/* CABEÇALHO */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-800">Meus Investimentos</h1>
          <p className="text-slate-500 mt-1">Adicione novos ativos e acompanhe sua rentabilidade.</p>
        </div>
        
        <button
          onClick={() => handleUpdateStockPrices(false)}
          disabled={isUpdatingPrices}
          className="bg-slate-800 hover:bg-slate-900 text-white px-4 py-2.5 rounded-lg shadow-sm flex items-center justify-center gap-2 disabled:opacity-50 transition"
        >
          {isUpdatingPrices ? (
            <span>A atualizar...</span>
          ) : (
            <>
              <RefreshCw size={18} />
              <span>Sincronizar Cotações</span>
            </>
          )}
        </button>
      </div>

      {/* SELETOR DE ABAS */}
      <div className="flex flex-wrap bg-slate-200 p-1 rounded-lg w-fit gap-1">
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
        <button 
          onClick={() => setActiveTab('MOVIMENTACOES')} 
          className={`px-4 py-2 rounded-md font-medium transition flex items-center gap-2 ${activeTab === 'MOVIMENTACOES' ? 'bg-white shadow-sm text-blue-600' : 'text-slate-600 hover:bg-slate-300'}`}
        >
          <History size={18}/> Movimentações
        </button>
      </div>
      
      {activeTab !== 'MOVIMENTACOES' && (
        <>
          {/* RENDA VARIÁVEL */}
          {activeTab === 'VARIAVEL' && (
            <form onSubmit={handleSubmit} className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 grid grid-cols-1 md:grid-cols-5 gap-4 items-end animate-in fade-in slide-in-from-bottom-4 duration-500">
              <div className="flex flex-col space-y-1">
                <label className="text-sm text-slate-500 font-medium">Classe do Ativo</label>
                <select value={form.asset_class} onChange={e => setForm({...form, asset_class: e.target.value})} className="p-2 border border-slate-300 rounded-lg bg-white" required>
                  <option value="STOCKS">Ações</option>
                  <option value="REIT">Fundos Imobiliários</option>
                  <option value="OTHER">Outros</option>
                </select>
              </div>

              <div className="flex flex-col space-y-1">
                <label className="text-sm text-slate-500 font-medium">Nome / Ticker</label>
                <input type="text" placeholder="Ex: PETR4" value={form.ticker_or_name} onChange={e => setForm({...form, ticker_or_name: e.target.value})} className="p-2 border border-slate-300 rounded-lg" required />
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
                {loading ? 'A adicionar...' : 'Adicionar Ativo'}
              </button>
            </form>
          )}

          {/* RENDA FIXA */}
          {activeTab === 'FIXA' && (
            <form onSubmit={handleSubmit} className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 grid grid-cols-1 md:grid-cols-6 gap-4 items-end animate-in fade-in slide-in-from-bottom-4 duration-500">
              
              <div className="flex flex-col space-y-1 md:col-span-2">
                <label className="text-sm text-slate-500 font-medium">Nome do Ativo</label>
                <input type="text" placeholder="Ex: LCI Banco Inter" value={form.ticker_or_name} onChange={e => setForm({...form, ticker_or_name: e.target.value})} className="p-2 border border-slate-300 rounded-lg" required />
              </div>

              <div className="flex flex-col space-y-1 md:col-span-1">
                <label className="text-sm text-slate-500 font-medium">Valor Aplicado (R$)</label>
                <input type="number" step="0.01" placeholder="Ex: 1000.00" value={form.average_price} onChange={e => setForm({...form, average_price: e.target.value})} className="p-2 border border-slate-300 rounded-lg" required />
              </div>

              <div className="flex flex-col space-y-1 md:col-span-1">
                <label className="text-sm text-slate-500 font-medium">% do CDI</label>
                <input type="number" step="0.1" placeholder="Ex: 110" value={form.cdi_percentage} onChange={e => setForm({...form, cdi_percentage: e.target.value})} className="p-2 border border-slate-300 rounded-lg" required />
              </div>

              <div className="flex flex-col space-y-1 md:col-span-1">
                <label className="text-sm text-slate-500 font-medium">Data Aplicação</label>
                <input type="date" value={form.purchase_date} onChange={e => setForm({...form, purchase_date: e.target.value})} className="p-2 border border-slate-300 rounded-lg" required />
              </div>

              <div className="flex flex-col space-y-1 md:col-span-1 justify-center pb-2 pl-2">
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input type="checkbox" checked={form.is_tax_free} onChange={e => setForm({...form, is_tax_free: e.target.checked})} className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500" />
                  <span className="text-sm text-slate-600 font-medium">Isento (LCI/A)</span>
                </label>
              </div>

              <button type="submit" disabled={loading} className="md:col-span-6 bg-blue-600 text-white rounded-lg py-2.5 font-medium hover:bg-blue-700 transition">
                {loading ? 'A adicionar...' : 'Adicionar à Renda Fixa'}
              </button>
            </form>
          )}

          {/* TABELA DE POSIÇÕES (CARTEIRA) */}
          <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-x-auto animate-in fade-in slide-in-from-bottom-4 duration-500">
            <table className="w-full text-left border-collapse min-w-max">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-100 text-slate-600 text-sm">
                  <th className="p-4 font-medium">Ativo</th>
                  <th className="p-4 font-medium">Qtd Total</th>
                  <th className="p-4 font-medium">Preço Médio / Aporte</th>
                  <th className="p-4 font-medium text-blue-600">Cotação Atual (Editar)</th>
                  <th className="p-4 font-medium">Valor Total</th>
                  <th className="p-4 font-medium">Rentabilidade</th>
                  <th className="p-4 font-medium text-right">Ações</th>
                </tr>
              </thead>
              <tbody>
                {filteredAssets.map(asset => (
                  <tr key={asset.id} className="border-b border-slate-50 hover:bg-slate-50 transition">
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
                          disabled={asset.class === 'FIXED_INCOME'} 
                          onBlur={async (e) => {
                            const newPrice = e.target.value;
                            if(newPrice && newPrice !== asset.current_price.toString()){
                              const { data: { user } } = await supabase.auth.getUser()
                              
                              let query = supabase.from('investments').update({ current_price: parseFloat(newPrice) })
                              if (asset.class === 'FIXED_INCOME') {
                                 query = query.eq('id', asset.id)
                              } else {
                                 query = query.eq('ticker_or_name', asset.ticker)
                              }
                              await query.eq('user_id', user.id)
                              fetchPortfolio(); 
                            }
                          }}
                          className={`w-28 p-1.5 border border-blue-200 rounded-md transition ${asset.class === 'FIXED_INCOME' ? 'bg-slate-100 text-slate-500 cursor-not-allowed border-slate-200' : 'bg-blue-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500'}`}
                          title={asset.class === 'FIXED_INCOME' ? "Cotação calculada automaticamente pelo CDI" : "Digite o novo preço e clique fora para salvar"}
                        />
                      </div>
                    </td>
                    <td className="p-4">
                      <p className="font-medium text-slate-800">Bruto: R$ {asset.current_value.toFixed(2)}</p>
                      {asset.class === 'FIXED_INCOME' && (
                         asset.is_tax_free 
                           ? <p className="text-xs text-green-600 font-medium">Líquido: R$ {asset.current_value.toFixed(2)} (Isento)</p> 
                           : <p className="text-xs text-slate-500">Líquido: R$ {asset.net_value?.toFixed(2)}</p>
                      )}
                    </td>
                    <td className="p-4">
                      <span className={`px-2 py-1 rounded-full text-xs font-bold ${asset.profitability_percent >= 0 ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                        {asset.profitability_percent > 0 ? '+' : ''}{asset.profitability_percent}%
                      </span>
                    </td>
                    <td className="p-4 text-right space-x-3">
                      {asset.class === 'FIXED_INCOME' ? (
                        <button onClick={() => handlePartialSale(asset)} className="text-blue-600 hover:text-blue-800 text-sm font-medium transition">
                          Resgatar
                        </button>
                      ) : (
                        <button onClick={() => handleSellVariable(asset)} className="text-blue-600 hover:text-blue-800 text-sm font-medium transition">
                          Vender
                        </button>
                      )}
                      <button onClick={() => handleDeleteFullPosition(asset)} className="text-red-400 hover:text-red-600 text-sm font-medium transition">
                        Excluir
                      </button>
                    </td>
                  </tr>
                ))}
                {filteredAssets.length === 0 && (
                  <tr><td colSpan="7" className="p-8 text-center text-slate-500">Nenhum ativo cadastrado nesta categoria.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ABA DE MOVIMENTAÇÕES (Histórico Cru) */}
      {activeTab === 'MOVIMENTACOES' && (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-x-auto animate-in fade-in slide-in-from-bottom-4 duration-500">
          <div className="p-4 border-b border-slate-100 bg-slate-50 flex justify-between items-center">
            <h2 className="font-bold text-slate-700">Histórico de Movimentações</h2>
            <p className="text-xs text-slate-500">Lista de compras e vendas na sua carteira.</p>
          </div>
          <table className="w-full text-left border-collapse min-w-max">
            <thead>
              <tr className="bg-white border-b border-slate-100 text-slate-600 text-sm">
                <th className="p-4 font-medium">Data / Hora</th>
                <th className="p-4 font-medium">Ativo</th>
                <th className="p-4 font-medium">Movimentação</th>
                <th className="p-4 font-medium">Preço Registrado</th>
                <th className="p-4 font-medium">Total</th>
                <th className="p-4 font-medium text-right">Ação</th>
              </tr>
            </thead>
            <tbody>
              {movements.map(mov => {
                const isFixed = mov.asset_class === 'FIXED_INCOME';
                const dateObj = new Date(mov.created_at);
                const isSale = mov.quantity < 0;
                
                return (
                  <tr key={mov.id} className="border-b border-slate-50 hover:bg-slate-50 transition">
                    <td className="p-4 text-slate-600 text-sm">
                      {dateObj.toLocaleDateString('pt-BR')} às {dateObj.toLocaleTimeString('pt-BR', {hour: '2-digit', minute:'2-digit'})}
                    </td>
                    <td className="p-4">
                      <p className="font-bold text-slate-800">{mov.ticker_or_name}</p>
                      <p className="text-xs text-slate-500">{getClassLabel(mov.asset_class)}</p>
                    </td>
                    <td className="p-4">
                      <span className={`px-2 py-1 rounded-md text-xs font-bold ${isSale ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>
                        {isFixed ? (isSale ? 'Resgate' : 'Aporte') : (isSale ? 'Venda' : 'Compra')} de {Math.abs(mov.quantity)}
                      </span>
                    </td>
                    <td className="p-4 text-slate-800">
                      R$ {mov.average_price.toFixed(2)}
                    </td>
                    <td className="p-4 font-medium text-slate-800">
                      R$ {Math.abs(mov.quantity * mov.average_price).toFixed(2)}
                    </td>
                    <td className="p-4 text-right space-x-3">
                      <button 
                        onClick={() => openEditModal(mov)} 
                        className="text-blue-500 hover:text-blue-700 text-sm font-medium transition"
                      >
                        Editar
                      </button>
                      <button 
                        onClick={() => handleDeleteMovement(mov.id)} 
                        className="text-red-400 hover:text-red-600 text-sm font-medium transition"
                        title="Excluir apenas esta movimentação"
                      >
                        Desfazer
                      </button>
                    </td>
                  </tr>
                )
              })}
              {movements.length === 0 && (
                <tr><td colSpan="6" className="p-8 text-center text-slate-500">Nenhum histórico encontrado.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* MODAL DE EDIÇÃO */}
      {editModal && (
        <div className="fixed inset-0 bg-slate-900/40 flex items-center justify-center z-50 p-4 animate-in fade-in duration-200">
          <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-xl relative">
            
            <button onClick={() => setEditModal(null)} className="absolute top-4 right-4 text-slate-400 hover:text-slate-600 transition">
              <X size={20} />
            </button>

            <h3 className="text-xl font-bold text-slate-800 mb-1">Editar Movimentação</h3>
            <p className="text-sm text-slate-500 mb-6">Ativo: <span className="font-bold text-slate-700">{editModal.ticker_or_name}</span></p>
            
            <form onSubmit={handleSaveEdit} className="space-y-4">
              
              {editModal.asset_class !== 'FIXED_INCOME' && (
                <div className="flex flex-col space-y-1">
                  <label className="text-sm text-slate-500 font-medium">Quantidade</label>
                  <input type="number" step="0.0001" value={editModal.quantity} onChange={e => setEditModal({...editModal, quantity: e.target.value})} className="p-2 border border-slate-300 rounded-lg" required />
                </div>
              )}

              <div className="flex flex-col space-y-1">
                <label className="text-sm text-slate-500 font-medium">
                  {editModal.asset_class === 'FIXED_INCOME' ? 'Valor Aplicado (R$)' : 'Preço de Compra/Venda (R$)'}
                </label>
                <input type="number" step="0.01" value={editModal.average_price} onChange={e => setEditModal({...editModal, average_price: e.target.value})} className="p-2 border border-slate-300 rounded-lg" required />
              </div>

              {editModal.asset_class === 'FIXED_INCOME' && (
                <>
                  <div className="flex flex-col space-y-1">
                    <label className="text-sm text-slate-500 font-medium">% do CDI</label>
                    <input type="number" step="0.1" value={editModal.cdi_percentage} onChange={e => setEditModal({...editModal, cdi_percentage: e.target.value})} className="p-2 border border-slate-300 rounded-lg" required />
                  </div>
                  
                  <div className="flex flex-col space-y-1">
                    <label className="text-sm text-slate-500 font-medium">Data Aplicação</label>
                    <input type="date" value={editModal.purchase_date} onChange={e => setEditModal({...editModal, purchase_date: e.target.value})} className="p-2 border border-slate-300 rounded-lg" required />
                  </div>

                  <div className="flex items-center space-x-2 pt-2 cursor-pointer">
                    <input type="checkbox" checked={editModal.is_tax_free} onChange={e => setEditModal({...editModal, is_tax_free: e.target.checked})} className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500" />
                    <span className="text-sm text-slate-600 font-medium">Isento de IR (LCI/LCA)</span>
                  </div>
                </>
              )}

              <div className="flex justify-end gap-3 pt-4 border-t border-slate-100 mt-6">
                <button type="button" onClick={() => setEditModal(null)} className="px-4 py-2 text-slate-600 hover:bg-slate-100 rounded-lg font-medium transition">
                  Cancelar
                </button>
                <button type="submit" disabled={loading} className="px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium transition">
                  {loading ? 'A guardar...' : 'Guardar Alterações'}
                </button>
              </div>
            </form>

          </div>
        </div>
      )}

    </div>
  )
}