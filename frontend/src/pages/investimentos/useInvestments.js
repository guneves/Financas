import { useEffect, useState } from 'react'
import { apiFetch } from '../../lib/api'
import { investmentsApi } from '../../lib/dataApi'
import { useDataVersion } from '../../lib/newEntry'
import { readStoredJson } from './helpers'

// Estado e carga compartilhados por Posicao e Operacoes: posicoes, historico,
// erro e a atualizacao de cotacoes. Movido de Investments.jsx sem mudanca de payload.
export default function useInvestments() {
  const [assets, setAssets] = useState(() => {
    return readStoredJson('@financeMVP:assets', [])
  })
  // Totais da carteira como o backend soma (bruto, aplicado, liquido de IR).
  // Sem cache: so aparecem depois da primeira busca.
  const [totals, setTotals] = useState(null)
  const [movements, setMovements] = useState([])
  const [dataError, setDataError] = useState('')

  const [isUpdatingPrices, setIsUpdatingPrices] = useState(false)
  const [updatingAssetId, setUpdatingAssetId] = useState('')
  const [quoteUpdateResult, setQuoteUpdateResult] = useState(null)

  const fetchPortfolio = async () => {
    try {
      setDataError('')
      const data = await apiFetch('/api/investments/portfolio?refresh_prices=false')
      const fetchedAssets = data.assets || []

      setAssets(fetchedAssets)
      setTotals({
        invested: Number(data.total_invested || 0),
        value: Number(data.current_balance || 0),
        netValue: Number(data.current_net_balance || 0),
      })
      localStorage.setItem('@financeMVP:assets', JSON.stringify(fetchedAssets))
    } catch (error) {
      console.warn('Erro ao buscar portfólio:', error)
      setDataError(error.message || 'Não foi possível carregar os investimentos.')
    }
  }

  const fetchMovements = async () => {
    try {
      const data = await investmentsApi.list({ order: 'created_at', ascending: false })
      setMovements(data || [])
    } catch (error) {
      console.warn('Erro ao buscar operações:', error)
      setMovements([])
      setDataError(error.message || 'Não foi possível carregar o histórico de operações.')
    }
  }

  const refreshAll = async () => {
    await fetchPortfolio()
    await fetchMovements()
  }

  const handleUpdateStockPrices = async (silent = false, investmentId = null, asset = null) => {
    setIsUpdatingPrices(true)
    const scopedAssetId = asset ? String(asset.asset_id || asset.id) : ''
    if (scopedAssetId) setUpdatingAssetId(scopedAssetId)
    try {
      const payload = asset
        ? { asset_id: scopedAssetId, asset_class: asset.class }
        : investmentId
          ? { investment_id: investmentId }
          : {}

      const data = await apiFetch('/api/investments/update-prices', {
        method: 'POST',
        body: JSON.stringify(payload)
      })

      if (!silent) {
        setQuoteUpdateResult(data)
      }
      await fetchPortfolio()
    } catch (error) {
      console.warn('Erro ao atualizar preços:', error)
      if (!silent) setDataError(error.message || 'Erro de conexão ao tentar atualizar os preços.')
    } finally {
      setIsUpdatingPrices(false)
      setUpdatingAssetId('')
    }
  }

  // dataVersion: recarrega depois de um "+ Novo" (ex.: Investimento) salvo no Layout.
  const dataVersion = useDataVersion()
  useEffect(() => {
    fetchPortfolio()
    fetchMovements()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataVersion])

  return {
    assets,
    totals,
    movements,
    dataError,
    setDataError,
    fetchPortfolio,
    fetchMovements,
    refreshAll,
    handleUpdateStockPrices,
    isUpdatingPrices,
    updatingAssetId,
    quoteUpdateResult,
    setQuoteUpdateResult,
  }
}
