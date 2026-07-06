import { useState, useEffect } from 'react'
import { apiFetch } from '../lib/api'
import { investmentsApi } from '../lib/dataApi'
import { RefreshCw, TrendingUp, Landmark, History, Plus, X } from 'lucide-react'
import InvestmentLaunchModal from '../components/InvestmentLaunchModal'

function readStoredJson(key, fallback) {
  try {
    const saved = localStorage.getItem(key)
    return saved ? JSON.parse(saved) : fallback
  } catch {
    localStorage.removeItem(key)
    return fallback
  }
}

function formatCurrency(value) {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(Number(value || 0))
}

function formatPercent(value) {
  return `${Number(value || 0).toFixed(2)}%`
}

function formatDateTime(value) {
  if (!value) return 'Sem atualização'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Data inválida'
  return date.toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function quoteSourceLabel(source) {
  const labels = {
    market: 'Mercado',
    manual: 'Manual',
    cdi: 'CDI',
    legacy: 'Legado',
    cache: 'Cache',
    cache_stale: 'Cache antigo',
    fallback: 'Sem fonte',
  }
  return labels[source] || source || 'Sem fonte'
}

function quoteStatusLabel(status) {
  const labels = {
    fresh: 'Atual',
    stale: 'Stale',
    missing: 'Sem cotação',
  }
  return labels[status] || 'Sem cotação'
}

function parseNumberInput(value) {
  const rawValue = String(value || '').trim()
  const normalized = rawValue.includes(',')
    ? rawValue.replace(/\./g, '').replace(',', '.')
    : rawValue
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : NaN
}

function getLocalDateString(date = new Date()) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function movementDateValue(movement) {
  return movement.metadata?.redemption_date
    || movement.metadata?.sale_date
    || movement.metadata?.purchase_date
    || movement.created_at
}

function movementUnitPrice(movement) {
  if (movement.metadata?.is_redemption) return Number(movement.current_price || 0)
  if (movement.quantity < 0 && movement.metadata?.sale_price) return Number(movement.metadata.sale_price || 0)
  return Number(movement.average_price || 0)
}

function movementTotalValue(movement) {
  return Math.abs(Number(movement.quantity || 0) * movementUnitPrice(movement))
}

function movementFees(movement) {
  return Number(
    movement.realized_fee_amount
    ?? movement.fee_amount
    ?? movement.metadata?.other_costs
    ?? 0
  )
}

function hasRealizedResult(movement) {
  return movement.realized_profit !== null
    && movement.realized_profit !== undefined
    && Number.isFinite(Number(movement.realized_profit))
}

export default function Investments() {
  const [activeTab, setActiveTab] = useState('VARIAVEL')

  const [assets, setAssets] = useState(() => {
    return readStoredJson('@financeMVP:assets', []);
  });

  const [movements, setMovements] = useState([]);
  const [loading, setLoading] = useState(false)
  const [dataError, setDataError] = useState('')

  const [editModal, setEditModal] = useState(null)
  const [isLaunchModalOpen, setIsLaunchModalOpen] = useState(false)
  const [launchIntent, setLaunchIntent] = useState({ mode: 'BUY', assetId: '' })
  const [isUpdatingPrices, setIsUpdatingPrices] = useState(false)
  const [updatingAssetId, setUpdatingAssetId] = useState('')
  const [quoteUpdateResult, setQuoteUpdateResult] = useState(null)

  const handleUpdateStockPrices = async (silent = false, investmentId = null, asset = null) => {
    setIsUpdatingPrices(true)
    const scopedAssetId = asset ? String(asset.asset_id || asset.id) : ''
    if (scopedAssetId) setUpdatingAssetId(scopedAssetId)
    try {
      const payload = asset
        ? { asset_id: scopedAssetId, asset_class: asset.class }
        : investmentId
          ? { investment_id: investmentId }
          : {};

      const data = await apiFetch('/api/investments/update-prices', {
        method: 'POST',
        body: JSON.stringify(payload)
      })

      if (!silent) {
        setQuoteUpdateResult(data)
      }
      await fetchPortfolio()
    } catch (error) {
      console.warn("Erro ao atualizar preços:", error)
      if (!silent) setDataError(error.message || "Erro de conexão ao tentar atualizar os preços.")
    } finally {
      setIsUpdatingPrices(false)
      setUpdatingAssetId('')
    }
  }

  useEffect(() => {
    fetchPortfolio()
    fetchMovements() 
  }, [])

  const fetchPortfolio = async () => {
    try {
      setDataError('')
      const data = await apiFetch('/api/investments/portfolio?refresh_prices=false')
      const fetchedAssets = data.assets || [];

      setAssets(fetchedAssets)
      localStorage.setItem('@financeMVP:assets', JSON.stringify(fetchedAssets));
    } catch (error) {
      console.warn("Erro ao buscar portfólio:", error)
      setDataError(error.message || 'Não foi possível carregar os investimentos.')
    }
  }

  const fetchMovements = async () => {
    try {
      const data = await investmentsApi.list({ order: 'created_at', ascending: false })
      setMovements(data || [])
    } catch (error) {
      console.warn("Erro ao buscar movimentações:", error)
      setMovements([])
      setDataError(error.message || 'Não foi possível carregar o histórico de movimentações.')
    }
  }

  const handleLaunchSaved = async () => {
    await fetchPortfolio()
    await fetchMovements()
  }

  const openBuyModal = () => {
    setLaunchIntent({ mode: 'BUY', assetId: '' })
    setIsLaunchModalOpen(true)
  }

  const openSellModal = (asset) => {
    setLaunchIntent({ mode: 'SELL', assetId: String(asset.id) })
    setIsLaunchModalOpen(true)
  }

  const openEditModal = (mov) => {
    const movementDate = movementDateValue(mov)
    setEditModal({
      id: mov.id,
      asset_class: mov.asset_class,
      ticker_or_name: mov.ticker_or_name,
      quantity: mov.quantity,
      average_price: mov.average_price,
      current_price: mov.current_price,
      metadata: mov.metadata || {},
      is_sale: mov.quantity < 0 && mov.asset_class !== 'FIXED_INCOME',
      is_redemption: !!mov.metadata?.is_redemption,
      sale_price: mov.metadata?.sale_price || '',
      other_costs: mov.metadata?.other_costs ?? mov.fee_amount ?? '',
      cdi_percentage: mov.metadata?.cdi_percentage ? (mov.metadata.cdi_percentage * 100).toFixed(1) : '',
      movement_date: movementDate ? String(movementDate).slice(0, 10) : '',
      is_tax_free: mov.metadata?.is_tax_free || false
    });
  }

  const handleSaveEdit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setDataError('');

    try {
      const averagePrice = Number(editModal.average_price)
      const finalQuantity = editModal.asset_class === 'FIXED_INCOME' ? 1 : Number(editModal.quantity);
      const cdiPercentage = Number(editModal.cdi_percentage)
      const otherCosts = editModal.other_costs === '' ? 0 : parseNumberInput(editModal.other_costs)
      const metadata = { ...(editModal.metadata || {}) }

      if (!Number.isFinite(averagePrice) || averagePrice < 0) {
        throw new Error('Informe um preço/valor válido.')
      }
      if (!Number.isFinite(otherCosts) || otherCosts < 0) {
        throw new Error('Informe custos validos.')
      }
      if (editModal.is_sale) {
        const salePrice = Number(editModal.sale_price || 0)
        if (!Number.isFinite(salePrice) || salePrice <= 0) {
          throw new Error('Informe um preço de venda válido.')
        }
      }
      if (
        !editModal.is_redemption
        && (
          !Number.isFinite(finalQuantity)
          || (editModal.is_sale ? finalQuantity >= 0 : finalQuantity <= 0)
        )
      ) {
        throw new Error('Informe uma quantidade válida.')
      }

      delete metadata.purchase_date
      delete metadata.sale_date
      delete metadata.redemption_date
      metadata.other_costs = otherCosts

      if (editModal.is_redemption) {
        metadata.redemption_date = editModal.movement_date
        metadata.is_redemption = true
      } else if (editModal.is_sale) {
        metadata.sale_date = editModal.movement_date
        metadata.sale_price = Number(editModal.sale_price || editModal.current_price || averagePrice)
      } else {
        metadata.purchase_date = editModal.movement_date
      }

      if (editModal.asset_class === 'FIXED_INCOME' && !editModal.is_redemption) {
        if (!Number.isFinite(cdiPercentage) || cdiPercentage <= 0) {
          throw new Error('Informe um percentual de CDI válido.')
        }
        metadata.cdi_percentage = cdiPercentage / 100
        metadata.is_tax_free = editModal.is_tax_free
      }

      await investmentsApi.update(editModal.id, {
        quantity: editModal.is_redemption ? Number(editModal.quantity) : finalQuantity,
        average_price: averagePrice,
        metadata: metadata
      });

      setEditModal(null);
      await fetchPortfolio();
      await fetchMovements();
      
      await handleUpdateStockPrices(true, editModal.id);

    } catch (error) {
      setDataError("Erro ao guardar edição: " + error.message);
    } finally {
      setLoading(false);
    }
  }

  const handleSellVariable = async (asset) => {
    openSellModal(asset)
  }

  const handlePartialSale = async (asset) => {
    if (asset.class !== 'FIXED_INCOME') return;

    const amountStr = window.prompt(`RESGATE PARCIAL\nAtivo: ${asset.name}\nValor Bruto Atual: R$ ${asset.current_value.toFixed(2)}\n\nQuanto você deseja resgatar (em R$)?`);
    if (!amountStr) return;
    
    const amount = parseNumberInput(amountStr);
    
    if (isNaN(amount) || amount <= 0 || amount > asset.current_value) {
      alert("Valor inválido. Digite um valor entre R$ 0.01 e o valor total bruto.");
      return;
    }

    const defaultDate = getLocalDateString()
    const dateStr = window.prompt('Data do resgate (AAAA-MM-DD):', defaultDate)
    if (!dateStr) return
    if (!/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
      alert('Data inválida. Use o formato AAAA-MM-DD.')
      return
    }

    setLoading(true);
    try {
      const ratio = amount / asset.current_value;
      const costBasisSold = asset.average_price * ratio;

      await investmentsApi.create([
        { 
          asset_class: asset.class,
          ticker_or_name: asset.name,
          quantity: -1, 
          average_price: costBasisSold, 
          current_price: amount,
          metadata: { 
            is_redemption: true,
            affects_position: true,
            related_id: asset.id,
            redemption_date: dateStr
          }
        }
      ]);

      alert("Resgate realizado e registrado nas movimentações!");
      await fetchPortfolio();
      await fetchMovements();
    } catch (error) {
      alert("Erro ao realizar resgate: " + error.message);
    } finally {
      setLoading(false);
    }
  }

  const handleDeleteMovement = async (id) => {
    if (window.confirm("Tem certeza que deseja excluir APENAS essa movimentação do histórico?")) {
      try {
        await investmentsApi.remove(id)
        await fetchPortfolio()
        await fetchMovements()
      } catch (error) {
        alert("Erro ao excluir movimentação: " + error.message)
      }
    }
  }

  const handleDeleteFullPosition = async (asset) => {
    if(window.confirm(`Tem certeza que deseja excluir ${asset.class === 'FIXED_INCOME' ? 'este aporte de' : 'TODA a posição de'} ${asset.name}?`)){
      try {
        if (asset.class === 'FIXED_INCOME') {
          await investmentsApi.remove(asset.id)
        } else {
          const assetId = asset.asset_id || asset.id
          await investmentsApi.removeByAsset(assetId, asset.class)
        }

        await fetchPortfolio();
        await fetchMovements();
      } catch (error) {
        setDataError(error.message || 'Não foi possível excluir a posição.')
      }
    }
  }

  const getClassLabel = (assetClass) => {
    const labels = {
      'STOCKS': 'Ações',
      'FIXED_INCOME': 'Renda Fixa',
      'REIT': 'Fundos Imobiliários',
      'CATTLE': 'Gado',
      'OTHER': 'Outros'
    }
    return labels[assetClass] || assetClass
  }

  const filteredAssets = assets.filter(asset => {
    if (activeTab === 'VARIAVEL') return asset.class !== 'FIXED_INCOME';
    if (activeTab === 'FIXA') return asset.class === 'FIXED_INCOME';
    return true;
  });

  const realizedMovements = movements.filter(hasRealizedResult)
  const realizedSummary = realizedMovements.reduce((acc, movement) => {
    acc.realizedProfit += Number(movement.realized_profit || 0)
    acc.taxAmount += Number(movement.realized_tax_amount || 0)
    acc.netProfitAfterTax += Number(movement.realized_net_profit_after_tax || 0)
    acc.netProceeds += Number(movement.realized_net_proceeds || 0)
    acc.costBasis += Number(movement.realized_cost_basis || 0)
    return acc
  }, {
    realizedProfit: 0,
    taxAmount: 0,
    netProfitAfterTax: 0,
    netProceeds: 0,
    costBasis: 0,
  });

  return (
    <div className="max-w-5xl mx-auto space-y-8 relative">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-zinc-800">Meus Investimentos</h1>
          <p className="text-zinc-500 mt-1">Adicione novos ativos e acompanhe sua rentabilidade.</p>
        </div>
        
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={() => handleUpdateStockPrices(false)}
            disabled={isUpdatingPrices}
            className="bg-white hover:bg-zinc-50 text-zinc-800 px-4 py-2.5 rounded-lg shadow-sm border border-zinc-200 flex items-center justify-center gap-2 disabled:opacity-50 transition"
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
          <button
            onClick={openBuyModal}
            className="bg-zinc-900 hover:bg-zinc-800 text-white px-4 py-2.5 rounded-lg shadow-sm flex items-center justify-center gap-2 transition"
          >
            <Plus size={18} />
            <span>Adicionar Lançamento</span>
          </button>
        </div>
      </div>

      {dataError ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-800">
          {dataError}
        </div>
      ) : null}

      {quoteUpdateResult ? (
        <div className="rounded-lg border border-zinc-200 bg-white p-4 text-sm shadow-sm">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="font-semibold text-zinc-900">Atualização de cotações</p>
              <p className="text-zinc-600">
                {quoteUpdateResult.updated_assets?.length || 0} atualizada(s),
                {' '}{quoteUpdateResult.failed_assets?.length || 0} falha(s),
                {' '}{quoteUpdateResult.stale_assets?.length || 0} stale/sem cotação.
              </p>
            </div>
            <button type="button" onClick={() => setQuoteUpdateResult(null)} className="text-sm font-medium text-zinc-500 hover:text-zinc-900">
              Fechar
            </button>
          </div>
          {quoteUpdateResult.updated_assets?.length ? (
            <p className="mt-3 text-emerald-700">
              Atualizados: {quoteUpdateResult.updated_assets.map((item) => item.ticker || item.name).join(', ')}
            </p>
          ) : null}
          {quoteUpdateResult.cached_assets?.length ? (
            <p className="mt-2 text-amber-700">
              Usando cache: {quoteUpdateResult.cached_assets.map((item) => item.ticker || item.name).join(', ')}
            </p>
          ) : null}
          {quoteUpdateResult.failed_assets?.length ? (
            <p className="mt-2 text-rose-700">
              Falharam: {quoteUpdateResult.failed_assets.map((item) => `${item.ticker || item.name} (${item.error || 'sem detalhe'})`).join(', ')}
            </p>
          ) : null}
          {quoteUpdateResult.stale_assets?.length ? (
            <p className="mt-2 text-zinc-600">
              Stale/sem cotação: {quoteUpdateResult.stale_assets.map((item) => item.ticker || item.name).join(', ')}
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="flex flex-wrap bg-zinc-200 p-1 rounded-lg w-fit gap-1">
        <button 
          onClick={() => setActiveTab('VARIAVEL')}
          className={`px-4 py-2 rounded-md font-medium transition flex items-center gap-2 ${activeTab === 'VARIAVEL' ? 'bg-white shadow-sm text-blue-600' : 'text-zinc-600 hover:bg-zinc-300'}`}
        >
          <TrendingUp size={18}/> Variável & Outros
        </button>
        <button 
          onClick={() => setActiveTab('FIXA')}
          className={`px-4 py-2 rounded-md font-medium transition flex items-center gap-2 ${activeTab === 'FIXA' ? 'bg-white shadow-sm text-blue-600' : 'text-zinc-600 hover:bg-zinc-300'}`}
        >
          <Landmark size={18}/> Renda Fixa (CDI)
        </button>
        <button 
          onClick={() => setActiveTab('MOVIMENTACOES')} 
          className={`px-4 py-2 rounded-md font-medium transition flex items-center gap-2 ${activeTab === 'MOVIMENTACOES' ? 'bg-white shadow-sm text-blue-600' : 'text-zinc-600 hover:bg-zinc-300'}`}
        >
          <History size={18}/> Movimentações
        </button>
      </div>
      
      {activeTab !== 'MOVIMENTACOES' && (
        <>
          <div className="bg-white rounded-lg shadow-sm border border-zinc-100 overflow-x-auto animate-in fade-in slide-in-from-bottom-4 duration-500">
            <table className="w-full text-left border-collapse min-w-max">
              <thead>
                <tr className="bg-zinc-50 border-b border-zinc-100 text-zinc-600 text-sm">
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
                {filteredAssets.map(asset => {
                  const quote = asset.quote || {}
                  const quoteStatus = quote.status || 'missing'
                  const quoteIsFresh = quoteStatus === 'fresh'
                  const assetUpdateId = String(asset.asset_id || asset.id)
                  const isUpdatingThisAsset = updatingAssetId === assetUpdateId
                  return (
                  <tr key={asset.id} className="border-b border-zinc-50 hover:bg-zinc-50 transition">
                    <td className="p-4">
                      <p className="font-bold text-zinc-800">{asset.name}</p>
                      <p className="text-xs text-zinc-500">{getClassLabel(asset.class)}</p>
                    </td>
                    <td className="p-4 text-zinc-800">
                      {asset.class === 'FIXED_INCOME' ? '-' : asset.quantity}
                    </td>
                    <td className="p-4 text-zinc-800">{formatCurrency(asset.average_price)}</td>
                    <td className="p-4">
                      <div className="flex items-center gap-2">
                        <span className="text-zinc-500">R$</span>
                        <input 
                          key={`${asset.id}-${asset.current_price}`}
                          type="number" 
                          step="0.01"
                          defaultValue={asset.current_price} 
                          disabled={asset.class === 'FIXED_INCOME'} 
                          onBlur={async (e) => {
                            const newPrice = e.target.value;
                            if(newPrice && newPrice !== asset.current_price.toString()){
                              const parsedPrice = Number(newPrice)
                              if (!Number.isFinite(parsedPrice) || parsedPrice < 0) {
                                setDataError('Informe uma cotação válida.')
                                e.target.value = asset.current_price
                                return
                              }

                              try {
                                setDataError('')
                                if (asset.class === 'FIXED_INCOME') {
                                  await investmentsApi.update(asset.id, { current_price: parsedPrice })
                                } else {
                                  const assetId = asset.asset_id || asset.id
                                  await investmentsApi.updatePriceByAsset(assetId, asset.class, parsedPrice)
                                }
                                await fetchPortfolio();
                              } catch (error) {
                                setDataError(error.message || 'Não foi possível atualizar a cotação.')
                                e.target.value = asset.current_price
                              }
                            }
                          }}
                          className={`w-28 p-1.5 border border-blue-200 rounded-md transition ${asset.class === 'FIXED_INCOME' ? 'bg-zinc-100 text-zinc-500 cursor-not-allowed border-zinc-200' : 'bg-blue-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500'}`}
                          title={asset.class === 'FIXED_INCOME' ? "Cotação calculada automaticamente pelo CDI" : "Digite o novo preço e clique fora para salvar"}
                        />
                        <button
                          type="button"
                          onClick={() => handleUpdateStockPrices(false, null, asset)}
                          disabled={isUpdatingPrices}
                          className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-zinc-200 text-zinc-600 transition hover:bg-zinc-100 disabled:opacity-50"
                          title="Atualizar cotação deste ativo"
                        >
                          <RefreshCw size={15} className={isUpdatingThisAsset ? 'animate-spin' : ''} />
                        </button>
                      </div>
                      <div className="mt-2 space-y-1 text-xs text-zinc-500">
                        <p>
                          {quoteSourceLabel(quote.source)} · {formatDateTime(quote.quoted_at)}
                        </p>
                        <span className={`inline-flex rounded-full px-2 py-0.5 font-semibold ${quoteIsFresh ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-800'}`}>
                          {quoteStatusLabel(quoteStatus)}
                        </span>
                      </div>
                    </td>
                    <td className="p-4">
                      <p className="font-medium text-zinc-800">Bruto: {formatCurrency(asset.current_value)}</p>
                      {asset.class === 'FIXED_INCOME' && (
                         asset.is_tax_free 
                           ? <p className="text-xs text-green-600 font-medium">Líquido: {formatCurrency(asset.current_value)} (Isento)</p>
                           : <p className="text-xs text-zinc-500">Líquido: {formatCurrency(asset.net_value)}</p>
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
                  )
                })}
                {filteredAssets.length === 0 && (
                  <tr><td colSpan="7" className="p-8 text-center text-zinc-500">Nenhum ativo cadastrado nesta categoria.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {activeTab === 'MOVIMENTACOES' && (
        <>
        <div className="grid gap-4 md:grid-cols-4">
          <div className="rounded-lg border border-zinc-100 bg-white p-4 shadow-sm">
            <p className="text-xs font-medium uppercase text-zinc-500">Operacoes realizadas</p>
            <p className="mt-2 text-2xl font-bold text-zinc-900">{realizedMovements.length}</p>
          </div>
          <div className="rounded-lg border border-zinc-100 bg-white p-4 shadow-sm">
            <p className="text-xs font-medium uppercase text-zinc-500">Lucro/prejuizo realizado</p>
            <p className={`mt-2 text-2xl font-bold ${realizedSummary.realizedProfit >= 0 ? 'text-emerald-700' : 'text-rose-600'}`}>
              {formatCurrency(realizedSummary.realizedProfit)}
            </p>
          </div>
          <div className="rounded-lg border border-zinc-100 bg-white p-4 shadow-sm">
            <p className="text-xs font-medium uppercase text-zinc-500">IR estimado</p>
            <p className="mt-2 text-2xl font-bold text-zinc-900">{formatCurrency(realizedSummary.taxAmount)}</p>
          </div>
          <div className="rounded-lg border border-zinc-100 bg-white p-4 shadow-sm">
            <p className="text-xs font-medium uppercase text-zinc-500">Resultado pos-IR</p>
            <p className={`mt-2 text-2xl font-bold ${realizedSummary.netProfitAfterTax >= 0 ? 'text-emerald-700' : 'text-rose-600'}`}>
              {formatCurrency(realizedSummary.netProfitAfterTax)}
            </p>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow-sm border border-zinc-100 overflow-x-auto animate-in fade-in slide-in-from-bottom-4 duration-500">
          <div className="p-4 border-b border-zinc-100 bg-zinc-50 flex justify-between items-center">
            <h2 className="font-bold text-zinc-700">Histórico de Movimentações</h2>
            <p className="text-xs text-zinc-500">Lista de compras e vendas na sua carteira.</p>
          </div>
          <table className="w-full text-left border-collapse min-w-max">
            <thead>
              <tr className="bg-white border-b border-zinc-100 text-zinc-600 text-sm">
                <th className="p-4 font-medium">Data / Hora</th>
                <th className="p-4 font-medium">Ativo</th>
                <th className="p-4 font-medium">Movimentação</th>
                <th className="p-4 font-medium">Preço Registrado</th>
                <th className="p-4 font-medium">Total</th>
                <th className="p-4 font-medium">Resultado realizado</th>
                <th className="p-4 font-medium">IR estimado</th>
                <th className="p-4 font-medium text-right">Ação</th>
              </tr>
            </thead>
            <tbody>
              {movements.map(mov => {
                const isFixed = mov.asset_class === 'FIXED_INCOME';
                const isSale = mov.quantity < 0;
                const isRedemption = !!mov.metadata?.is_redemption
                const unitPrice = movementUnitPrice(mov)
                const totalValue = movementTotalValue(mov)
                const fees = movementFees(mov)
                const hasResult = hasRealizedResult(mov)
                const netProceeds = hasResult
                  ? Number(mov.realized_net_proceeds || 0)
                  : Math.max(totalValue - fees, 0)
                const realizedProfit = Number(mov.realized_profit || 0)
                const realizedTax = Number(mov.realized_tax_amount || 0)
                const afterTax = Number(mov.realized_net_profit_after_tax || 0)
                const realizedMetadata = mov.realized_metadata || {}
                const allocationCount = Array.isArray(realizedMetadata.allocations)
                  ? realizedMetadata.allocations.length
                  : 0
                
                const dateValue = movementDateValue(mov)
                const hasCustomDate = dateValue && dateValue !== mov.created_at
                const dateObj = hasCustomDate
                  ? new Date(`${String(dateValue).slice(0, 10)}T00:00:00`)
                  : new Date(mov.created_at)
                return (
                  <tr key={mov.id} className="border-b border-zinc-50 hover:bg-zinc-50 transition">
                    <td className="p-4 text-zinc-600 text-sm">
                      {dateObj.toLocaleDateString('pt-BR')}
                      {!hasCustomDate && ` às ${dateObj.toLocaleTimeString('pt-BR', {hour: '2-digit', minute:'2-digit'})}`}
                    </td>
                    <td className="p-4">
                      <p className="font-bold text-zinc-800">{mov.ticker_or_name}</p>
                      <p className="text-xs text-zinc-500">{getClassLabel(mov.asset_class)}</p>
                    </td>
                    <td className="p-4">
                      <span className={`px-2 py-1 rounded-md text-xs font-bold ${isSale ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>
                        {isFixed ? (isSale ? 'Resgate' : 'Aporte') : (isSale ? 'Venda' : 'Compra')} de {isRedemption ? formatCurrency(totalValue) : Math.abs(mov.quantity)}
                      </span>
                    </td>
                    <td className="p-4 text-zinc-800">
                      {formatCurrency(unitPrice)}
                    </td>
                    <td className="p-4 font-medium text-zinc-800">
                      <p>{formatCurrency(totalValue)}</p>
                      {fees > 0 ? (
                        <p className="text-xs text-zinc-500">Custos: {formatCurrency(fees)}</p>
                      ) : null}
                      {isSale ? (
                        <p className="text-xs text-zinc-500">Liquido: {formatCurrency(netProceeds)}</p>
                      ) : null}
                    </td>
                    <td className="p-4">
                      {hasResult ? (
                        <div>
                          <p className={`font-bold ${realizedProfit >= 0 ? 'text-emerald-700' : 'text-rose-600'}`}>
                            {realizedProfit > 0 ? '+' : ''}{formatCurrency(realizedProfit)}
                          </p>
                          <p className="text-xs text-zinc-500">Base: {formatCurrency(mov.realized_cost_basis)}</p>
                          <p className="text-xs text-zinc-500">
                            {formatPercent(mov.realized_profitability_percent)} via {realizedMetadata.cost_method || 'FIFO'}
                            {allocationCount ? ` (${allocationCount} lote${allocationCount > 1 ? 's' : ''})` : ''}
                          </p>
                        </div>
                      ) : (
                        <span className="text-zinc-400">-</span>
                      )}
                    </td>
                    <td className="p-4">
                      {hasResult ? (
                        <div>
                          <p className="font-medium text-zinc-800">{formatCurrency(realizedTax)}</p>
                          <p className={`text-xs font-medium ${afterTax >= 0 ? 'text-emerald-700' : 'text-rose-600'}`}>
                            Pos-IR: {formatCurrency(afterTax)}
                          </p>
                          <p className="text-xs text-zinc-500">
                            Aliq.: {formatPercent(Number(mov.realized_tax_rate || 0) * 100)}
                          </p>
                        </div>
                      ) : (
                        <span className="text-zinc-400">-</span>
                      )}
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
                <tr><td colSpan="8" className="p-8 text-center text-zinc-500">Nenhum histórico encontrado.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        </>
      )}

      <InvestmentLaunchModal
        open={isLaunchModalOpen}
        onClose={() => setIsLaunchModalOpen(false)}
        assets={assets}
        onSaved={handleLaunchSaved}
        initialMode={launchIntent.mode}
        initialAssetId={launchIntent.assetId}
      />

      {editModal && (
        <div className="fixed inset-0 bg-zinc-900/40 flex items-center justify-center z-50 p-4 animate-in fade-in duration-200">
          <div className="bg-white rounded-lg p-6 w-full max-w-md max-h-[90vh] overflow-y-auto shadow-xl relative">
            <button onClick={() => setEditModal(null)} className="absolute top-4 right-4 text-zinc-400 hover:text-zinc-600 transition">
              <X size={20} />
            </button>

            <h3 className="text-xl font-bold text-zinc-800 mb-1">Editar Movimentação</h3>
            <p className="text-sm text-zinc-500 mb-6">Ativo: <span className="font-bold text-zinc-700">{editModal.ticker_or_name}</span></p>
            
            <form onSubmit={handleSaveEdit} className="space-y-4">
              {editModal.asset_class !== 'FIXED_INCOME' && (
                <div className="flex flex-col space-y-1">
                  <label className="text-sm text-zinc-500 font-medium">Quantidade</label>
                  <input type="number" step="0.0001" value={editModal.quantity} onChange={e => setEditModal({...editModal, quantity: e.target.value})} className="p-2 border border-zinc-300 rounded-lg" required />
                </div>
              )}

              <div className="flex flex-col space-y-1">
                <label className="text-sm text-zinc-500 font-medium">
                  {editModal.is_redemption ? 'Base de custo resgatada (R$)' : editModal.asset_class === 'FIXED_INCOME' ? 'Valor Aplicado (R$)' : 'Preço médio/base de custo (R$)'}
                </label>
                <input type="number" step="0.01" value={editModal.average_price} onChange={e => setEditModal({...editModal, average_price: e.target.value})} className="p-2 border border-zinc-300 rounded-lg" required />
              </div>

              {editModal.is_sale && (
                <div className="flex flex-col space-y-1">
                  <label className="text-sm text-zinc-500 font-medium">Preço de venda (R$)</label>
                  <input type="number" step="0.01" value={editModal.sale_price} onChange={e => setEditModal({...editModal, sale_price: e.target.value})} className="p-2 border border-zinc-300 rounded-lg" required />
                </div>
              )}

              <div className="flex flex-col space-y-1">
                <label className="text-sm text-zinc-500 font-medium">Outros custos (R$)</label>
                <input type="number" min="0" step="0.01" value={editModal.other_costs} onChange={e => setEditModal({...editModal, other_costs: e.target.value})} className="p-2 border border-zinc-300 rounded-lg" />
              </div>

              <div className="flex flex-col space-y-1">
                <label className="text-sm text-zinc-500 font-medium">Data da movimentação</label>
                <input type="date" value={editModal.movement_date} onChange={e => setEditModal({...editModal, movement_date: e.target.value})} className="p-2 border border-zinc-300 rounded-lg" required />
              </div>

              {editModal.asset_class === 'FIXED_INCOME' && !editModal.is_redemption && (
                <>
                  <div className="flex flex-col space-y-1">
                    <label className="text-sm text-zinc-500 font-medium">% do CDI</label>
                    <input type="number" step="0.1" value={editModal.cdi_percentage} onChange={e => setEditModal({...editModal, cdi_percentage: e.target.value})} className="p-2 border border-zinc-300 rounded-lg" required />
                  </div>

                  <div className="flex items-center space-x-2 pt-2 cursor-pointer">
                    <input type="checkbox" checked={editModal.is_tax_free} onChange={e => setEditModal({...editModal, is_tax_free: e.target.checked})} className="w-4 h-4 rounded border-zinc-300 text-blue-600 focus:ring-blue-500" />
                    <span className="text-sm text-zinc-600 font-medium">Isento de IR (LCI/LCA)</span>
                  </div>
                </>
              )}

              <div className="flex justify-end gap-3 pt-4 border-t border-zinc-100 mt-6">
                <button type="button" onClick={() => setEditModal(null)} className="px-4 py-2 text-zinc-600 hover:bg-zinc-100 rounded-lg font-medium transition">
                  Cancelar
                </button>
                <button type="submit" disabled={loading} className="px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium transition">
                  {loading ? 'Salvando...' : 'Salvar Alterações'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
