import { useState } from 'react'
import { Briefcase, Landmark, Plus, RefreshCw, Trash2, TrendingUp, X } from 'lucide-react'
import InvestmentLaunchModal from '../../components/InvestmentLaunchModal'
import {
  AlertMessage,
  Badge,
  Button,
  EmptyState,
  IconButton,
  PageHeader,
  Panel,
  PanelHeader,
  SegmentedControl,
  cx,
} from '../../components/ui'
import { investmentsApi } from '../../lib/dataApi'
import { formatCurrency, getLocalDateString } from '../../lib/format'
import PortfolioOverview from './PortfolioOverview'
import {
  formatDateTime,
  getClassLabel,
  parseNumberInput,
  quoteSourceLabel,
  quoteStatusLabel,
} from './helpers'
import useInvestments from './useInvestments'
import { describeFixedIncome } from '../../lib/fixedIncome'

const POSITION_TABS = [
  { value: 'VARIAVEL', label: 'Variável', icon: TrendingUp },
  { value: 'FIXA', label: 'Renda fixa', icon: Landmark },
]

export default function Posicao() {
  const {
    assets,
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
  } = useInvestments()

  const [activeTab, setActiveTab] = useState('VARIAVEL')
  const [loading, setLoading] = useState(false)
  const [isLaunchModalOpen, setIsLaunchModalOpen] = useState(false)
  const [launchIntent, setLaunchIntent] = useState({ mode: 'BUY', assetId: '' })

  const openBuyModal = () => {
    setLaunchIntent({ mode: 'BUY', assetId: '' })
    setIsLaunchModalOpen(true)
  }

  const openSellModal = (asset) => {
    setLaunchIntent({ mode: 'SELL', assetId: String(asset.id) })
    setIsLaunchModalOpen(true)
  }

  const handleSellVariable = async (asset) => {
    openSellModal(asset)
  }

  const handlePartialSale = async (asset) => {
    if (asset.class !== 'FIXED_INCOME') return

    const amountStr = window.prompt(`RESGATE PARCIAL\nAtivo: ${asset.name}\nValor Bruto Atual: R$ ${asset.current_value.toFixed(2)}\n\nQuanto você deseja resgatar (em R$)?`)
    if (!amountStr) return

    const amount = parseNumberInput(amountStr)

    if (isNaN(amount) || amount <= 0 || amount > asset.current_value) {
      alert('Valor inválido. Digite um valor entre R$ 0.01 e o valor total bruto.')
      return
    }

    const defaultDate = getLocalDateString()
    const dateStr = window.prompt('Data do resgate (AAAA-MM-DD):', defaultDate)
    if (!dateStr) return
    if (!/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
      alert('Data inválida. Use o formato AAAA-MM-DD.')
      return
    }

    setLoading(true)
    try {
      const ratio = amount / asset.current_value
      const costBasisSold = asset.average_price * ratio

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
      ])

      alert('Resgate realizado e registrado nas operações!')
      await fetchPortfolio()
      await fetchMovements()
    } catch (error) {
      alert('Erro ao realizar resgate: ' + error.message)
    } finally {
      setLoading(false)
    }
  }

  // A guarda do backend exige a classe junto do ativo: um DELETE por ativo sem
  // a asset_class correspondente e recusado.
  const handleDeleteFullPosition = async (asset) => {
    if (window.confirm(`Tem certeza que deseja excluir ${asset.class === 'FIXED_INCOME' ? 'este aporte de' : 'TODA a posição de'} ${asset.name}?`)) {
      try {
        if (asset.class === 'FIXED_INCOME') {
          await investmentsApi.remove(asset.id)
        } else {
          const assetId = asset.asset_id || asset.id
          await investmentsApi.removeByAsset(assetId, asset.class)
        }

        await fetchPortfolio()
        await fetchMovements()
      } catch (error) {
        setDataError(error.message || 'Não foi possível excluir a posição.')
      }
    }
  }

  const handleManualPrice = async (asset, e) => {
    const newPrice = e.target.value
    if (newPrice && newPrice !== asset.current_price.toString()) {
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
        await fetchPortfolio()
      } catch (error) {
        setDataError(error.message || 'Não foi possível atualizar a cotação.')
        e.target.value = asset.current_price
      }
    }
  }

  const filteredAssets = assets.filter((asset) => {
    if (activeTab === 'VARIAVEL') return asset.class !== 'FIXED_INCOME'
    if (activeTab === 'FIXA') return asset.class === 'FIXED_INCOME'
    return true
  })

  const rowProps = (asset) => ({
    asset,
    isUpdatingPrices,
    isUpdatingThisAsset: updatingAssetId === String(asset.asset_id || asset.id),
    busy: loading,
    onManualPrice: handleManualPrice,
    onRefresh: () => handleUpdateStockPrices(false, null, asset),
    onSell: () => (asset.class === 'FIXED_INCOME' ? handlePartialSale(asset) : handleSellVariable(asset)),
    onDelete: () => handleDeleteFullPosition(asset),
  })

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Investimentos"
        title="Posição"
        description="O que você tem, quanto vale e como está rendendo."
        actions={(
          <>
            <Button
              type="button"
              variant="secondary"
              icon={RefreshCw}
              loading={isUpdatingPrices}
              onClick={() => handleUpdateStockPrices(false)}
            >
              Atualizar cotações
            </Button>
            <Button type="button" icon={Plus} onClick={openBuyModal}>
              Registrar operação
            </Button>
          </>
        )}
      />

      <AlertMessage tone="warning" message={dataError} onDismiss={() => setDataError('')} />

      {quoteUpdateResult ? (
        <QuoteUpdateResult result={quoteUpdateResult} onClose={() => setQuoteUpdateResult(null)} />
      ) : null}

      {assets.length > 0 ? (
        <PortfolioOverview assets={assets} getClassLabel={getClassLabel} />
      ) : null}

      <SegmentedControl items={POSITION_TABS} value={activeTab} onChange={setActiveTab} />

      <Panel className="overflow-hidden">
        {filteredAssets.length === 0 ? (
          <div className="p-5">
            <EmptyState
              icon={Briefcase}
              title="Nenhum ativo cadastrado nesta categoria."
              message="Registre uma compra ou um aporte para acompanhar a posição aqui."
              action={<Button type="button" icon={Plus} onClick={openBuyModal}>Registrar operação</Button>}
            />
          </div>
        ) : (
          <>
            {/* Celular: um cartao por ativo, acoes em botoes de 44px. */}
            <ul className="divide-y divide-zinc-100 md:hidden">
              {filteredAssets.map((asset) => (
                <PositionCard key={asset.id} {...rowProps(asset)} />
              ))}
            </ul>

            <div className="hidden overflow-x-auto md:block">
              <table className="app-table min-w-[960px]">
                <thead>
                  <tr>
                    <th>Ativo</th>
                    <th>Qtd total</th>
                    <th>Preço médio / aporte</th>
                    <th>Cotação atual (editável)</th>
                    <th>Valor total</th>
                    <th>Rentabilidade</th>
                    <th className="text-right">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredAssets.map((asset) => (
                    <PositionRow key={asset.id} {...rowProps(asset)} />
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Panel>

      <InvestmentLaunchModal
        open={isLaunchModalOpen}
        onClose={() => setIsLaunchModalOpen(false)}
        assets={assets}
        onSaved={refreshAll}
        initialMode={launchIntent.mode}
        initialAssetId={launchIntent.assetId}
      />
    </div>
  )
}

function QuoteUpdateResult({ result, onClose }) {
  return (
    <Panel className="animate-slide-down">
      <PanelHeader
        title="Atualização de cotações"
        description={`${result.updated_assets?.length || 0} atualizada(s), ${result.failed_assets?.length || 0} falha(s), ${result.stale_assets?.length || 0} desatualizada(s)/sem cotação.`}
        actions={<IconButton label="Fechar resultado" icon={X} variant="subtle" onClick={onClose} />}
      />
      {result.updated_assets?.length || result.cached_assets?.length || result.failed_assets?.length || result.stale_assets?.length ? (
        <div className="space-y-2 px-5 py-4 text-sm">
          {result.updated_assets?.length ? (
            <p className="text-emerald-700">
              Atualizados: {result.updated_assets.map((item) => item.ticker || item.name).join(', ')}
            </p>
          ) : null}
          {result.cached_assets?.length ? (
            <p className="text-amber-700">
              Usando cache: {result.cached_assets.map((item) => item.ticker || item.name).join(', ')}
            </p>
          ) : null}
          {result.failed_assets?.length ? (
            <p className="text-rose-700">
              Falharam: {result.failed_assets.map((item) => `${item.ticker || item.name} (${item.error || 'sem detalhe'})`).join(', ')}
            </p>
          ) : null}
          {result.stale_assets?.length ? (
            <p className="text-zinc-600">
              Desatualizada/sem cotação: {result.stale_assets.map((item) => item.ticker || item.name).join(', ')}
            </p>
          ) : null}
        </div>
      ) : null}
    </Panel>
  )
}

function PriceEditor({ asset, isUpdatingPrices, isUpdatingThisAsset, onManualPrice, onRefresh }) {
  const quote = asset.quote || {}
  const quoteStatus = quote.status || 'missing'
  const quoteIsFresh = quoteStatus === 'fresh'
  const isFixed = asset.class === 'FIXED_INCOME'

  return (
    <div>
      <div className="flex items-center gap-2">
        <span className="text-sm text-zinc-600">R$</span>
        <input
          key={`${asset.id}-${asset.current_price}`}
          type="number"
          step="0.01"
          inputMode="decimal"
          aria-label={`Cotação de ${asset.name}`}
          defaultValue={asset.current_price}
          disabled={isFixed}
          onBlur={(e) => onManualPrice(asset, e)}
          className={cx('app-input w-32 py-2', isFixed && 'cursor-not-allowed bg-zinc-100 text-zinc-500')}
          title={isFixed ? 'Valor calculado automaticamente pela taxa do título' : 'Digite o novo preço e clique fora para salvar'}
        />
        <IconButton
          label="Atualizar cotação deste ativo"
          icon={RefreshCw}
          onClick={onRefresh}
          disabled={isUpdatingPrices}
          className={cx('disabled:opacity-50', isUpdatingThisAsset && '[&>svg]:animate-spin')}
        />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-zinc-600">
        <span>{quoteSourceLabel(quote.source)} · {formatDateTime(quote.quoted_at)}</span>
        <Badge tone={quoteIsFresh ? 'success' : 'warning'} className="px-2 py-0.5">
          {quoteStatusLabel(quoteStatus)}
        </Badge>
      </div>
    </div>
  )
}

function ValueCell({ asset }) {
  return (
    <>
      <p className="font-medium text-zinc-900">Bruto: {formatCurrency(asset.current_value)}</p>
      {asset.class === 'FIXED_INCOME' && (
        asset.is_tax_free
          ? <p className="text-xs font-medium text-emerald-700">Líquido: {formatCurrency(asset.current_value)} (Isento)</p>
          : <p className="text-xs text-zinc-600">Líquido: {formatCurrency(asset.net_value)}</p>
      )}
    </>
  )
}

function ProfitBadge({ value }) {
  return (
    <Badge tone={value >= 0 ? 'success' : 'danger'}>
      {value > 0 ? '+' : ''}{value}%
    </Badge>
  )
}

function PositionRow({ asset, busy, onSell, onDelete, ...priceProps }) {
  const isFixed = asset.class === 'FIXED_INCOME'
  return (
    <tr>
      <td>
        <p className="font-semibold text-zinc-950">{asset.name}</p>
        <p className="text-xs text-zinc-600">{getClassLabel(asset.class)}</p>
        {isFixed && describeFixedIncome(asset.metadata) ? (
          <p className="text-xs text-zinc-500">{describeFixedIncome(asset.metadata)}</p>
        ) : null}
      </td>
      <td className="tabular text-zinc-800">{isFixed ? '-' : asset.quantity}</td>
      <td className="tabular text-zinc-800">{formatCurrency(asset.average_price)}</td>
      <td><PriceEditor asset={asset} {...priceProps} /></td>
      <td className="tabular"><ValueCell asset={asset} /></td>
      <td><ProfitBadge value={asset.profitability_percent} /></td>
      <td className="text-right">
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" variant="secondary" onClick={onSell} disabled={busy}>
            {isFixed ? 'Resgatar' : 'Vender'}
          </Button>
          <IconButton
            label={isFixed ? 'Excluir este aporte' : 'Excluir toda a posição'}
            icon={Trash2}
            variant="danger"
            onClick={onDelete}
          />
        </div>
      </td>
    </tr>
  )
}

function PositionCard({ asset, busy, onSell, onDelete, ...priceProps }) {
  const isFixed = asset.class === 'FIXED_INCOME'
  return (
    <li className="space-y-3 px-4 py-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-semibold text-zinc-950">{asset.name}</p>
          <p className="text-xs text-zinc-600">
            {getClassLabel(asset.class)}
            {isFixed && describeFixedIncome(asset.metadata) ? ` · ${describeFixedIncome(asset.metadata)}` : ''}
            {isFixed ? '' : ` · ${asset.quantity} un.`}
            {` · PM ${formatCurrency(asset.average_price)}`}
          </p>
        </div>
        <ProfitBadge value={asset.profitability_percent} />
      </div>
      <div className="text-sm tabular"><ValueCell asset={asset} /></div>
      <PriceEditor asset={asset} {...priceProps} />
      <div className="flex gap-2">
        <Button type="button" size="lg" variant="secondary" onClick={onSell} disabled={busy} className="flex-1">
          {isFixed ? 'Resgatar' : 'Vender'}
        </Button>
        <IconButton
          label={isFixed ? 'Excluir este aporte' : 'Excluir toda a posição'}
          icon={Trash2}
          variant="danger"
          onClick={onDelete}
        />
      </div>
    </li>
  )
}
