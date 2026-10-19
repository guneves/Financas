import { useEffect, useState } from 'react'
import { apiFetch } from '../../lib/api'
import { investmentsApi, refreshQuotes } from '../../lib/dataApi'
import { invalidateServerData, queryErrorMessage, useQuery } from '../../lib/queries'
import { useProceedsSync } from '../../lib/proceedsSync'

async function fetchPortfolio() {
  const data = await apiFetch('/api/investments/portfolio?refresh_prices=false')
  return {
    assets: data.assets || [],
    // Totais da carteira como o backend soma (bruto, aplicado, liquido de IR).
    totals: {
      invested: Number(data.total_invested || 0),
      value: Number(data.current_balance || 0),
      netValue: Number(data.current_net_balance || 0),
    },
  }
}

const NO_ASSETS = []
const NO_MOVEMENTS = []

// Estado e carga compartilhados por Posicao e Operacoes: posicoes, historico,
// erro e a atualizacao de cotacoes. Duas queries (carteira e operacoes);
// gravar qualquer coisa invalida as duas (lib/queries.js).
export default function useInvestments() {
  useProceedsSync()
  const portfolioQuery = useQuery({ queryKey: ['investimentos', 'carteira'], queryFn: fetchPortfolio })
  const movementsQuery = useQuery({
    queryKey: ['investimentos', 'operacoes'],
    queryFn: () => investmentsApi.list({ order: 'created_at', ascending: false }),
  })
  const assets = portfolioQuery.data?.assets || NO_ASSETS
  const totals = portfolioQuery.data?.totals || null
  const movements = movementsQuery.data || NO_MOVEMENTS

  const [dataError, setDataError] = useState('')
  const [isUpdatingPrices, setIsUpdatingPrices] = useState(false)
  const [updatingAssetId, setUpdatingAssetId] = useState('')
  const [quoteUpdateResult, setQuoteUpdateResult] = useState(null)

  useEffect(() => {
    if (portfolioQuery.error) {
      console.warn('Erro ao buscar portfólio:', portfolioQuery.error)
      setDataError(queryErrorMessage(portfolioQuery, 'Não foi possível carregar os investimentos.'))
    }
  }, [portfolioQuery.error])

  useEffect(() => {
    if (movementsQuery.error) {
      console.warn('Erro ao buscar operações:', movementsQuery.error)
      setDataError(queryErrorMessage(movementsQuery, 'Não foi possível carregar o histórico de operações.'))
    }
  }, [movementsQuery.error])

  // Depois de gravar: tudo que estava em cache busca de novo.
  const refreshAll = () => invalidateServerData()

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

      // So refaz as telas se alguma cotacao mudou (refreshQuotes), e sem
      // esperar a busca nova: o cache mostra o anterior enquanto ela corre.
      const data = await refreshQuotes(payload)

      if (!silent) {
        setQuoteUpdateResult(data)
      }
    } catch (error) {
      console.warn('Erro ao atualizar preços:', error)
      if (!silent) setDataError(error.message || 'Erro de conexão ao tentar atualizar os preços.')
    } finally {
      setIsUpdatingPrices(false)
      setUpdatingAssetId('')
    }
  }

  return {
    loading: portfolioQuery.isPending,
    movementsLoading: movementsQuery.isPending,
    assets,
    totals,
    movements,
    dataError,
    setDataError,
    refreshAll,
    handleUpdateStockPrices,
    isUpdatingPrices,
    updatingAssetId,
    quoteUpdateResult,
    setQuoteUpdateResult,
  }
}
