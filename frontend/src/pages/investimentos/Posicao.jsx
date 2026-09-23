import { useState } from 'react'
import { Briefcase, Download, Landmark, Plus, RefreshCw, Trash2, TrendingUp, X } from 'lucide-react'
import InvestmentLaunchModal from '../../components/InvestmentLaunchModal'
import {
  AlertMessage,
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
import { formatCurrency, formatPercent, getLocalDateString } from '../../lib/format'
import { MASKED_CURRENCY, MASKED_TEXT, usePrivateFormatter, useValuesHidden } from '../../lib/privacy'
import PortfolioOverview from './PortfolioOverview'
import {
  formatDateTime,
  getClassLabel,
  parseNumberInput,
  quoteSourceLabel,
  quoteStatusLabel,
} from './helpers'
import useInvestments from './useInvestments'
import { FIXED_INCOME_TYPES, describeFixedIncome } from '../../lib/fixedIncome'

const POSITION_TABS = [
  { value: 'VARIAVEL', label: 'Variável', icon: TrendingUp },
  { value: 'FIXA', label: 'Renda fixa', icon: Landmark },
]

const VARIABLE_CLASS_ORDER = ['STOCKS', 'REIT', 'CATTLE', 'OTHER']
const FIXED_INCOME_TYPE_ORDER = FIXED_INCOME_TYPES.map((type) => type.value)
const NO_FIXED_INCOME_TYPE = 'SEM_TIPO'

// Subdivide a aba: renda variavel por classe (Acoes, FIIs...), renda fixa pelo
// tipo do titulo (CDB, LCI...). Aporte antigo sem tipo cai em "Sem tipo", no fim.
function groupAssets(assets, activeTab) {
  const isFixedTab = activeTab === 'FIXA'
  const order = isFixedTab ? FIXED_INCOME_TYPE_ORDER : VARIABLE_CLASS_ORDER
  const groups = new Map()

  assets.forEach((asset) => {
    const key = isFixedTab
      ? (asset.metadata?.fixed_income_type || NO_FIXED_INCOME_TYPE)
      : asset.class
    if (!groups.has(key)) {
      const label = isFixedTab
        ? (FIXED_INCOME_TYPES.find((type) => type.value === key)?.label || (key === NO_FIXED_INCOME_TYPE ? 'Sem tipo' : key))
        : getClassLabel(key)
      groups.set(key, { key, label, assets: [], total: 0 })
    }
    const group = groups.get(key)
    group.assets.push(asset)
    group.total += Number(asset.current_value || 0)
  })

  const rank = (key) => {
    const index = order.indexOf(key)
    return index === -1 ? order.length : index
  }
  return [...groups.values()].sort((a, b) => rank(a.key) - rank(b.key) || a.label.localeCompare(b.label, 'pt-BR'))
}

function groupSummary(group, money) {
  const count = group.assets.length
  return `${count} ${count === 1 ? 'posição' : 'posições'} · ${money(group.total)}`
}

export default function Posicao() {
  // Modo privado: valores, quantidades e o principal da renda fixa somem;
  // preco medio de acao, cotacao e rentabilidade (%) ficam.
  const privateMoney = usePrivateFormatter(formatCurrency)
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
  const [exporting, setExporting] = useState(false)
  const [isLaunchModalOpen, setIsLaunchModalOpen] = useState(false)
  const [launchIntent, setLaunchIntent] = useState({ mode: 'BUY', assetId: '' })

  // Exporta a carteira como ela esta agora; nao forca atualizacao de cotacao.
  const handleExportPortfolio = async () => {
    setExporting(true)
    try {
      await investmentsApi.exportPortfolioCsv()
      setDataError('')
    } catch (error) {
      setDataError(error.message || 'Não foi possível exportar a carteira.')
    } finally {
      setExporting(false)
    }
  }

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
  const assetGroups = groupAssets(filteredAssets, activeTab)

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
            <Button
              type="button"
              variant="secondary"
              icon={Download}
              loading={exporting}
              disabled={assets.length === 0}
              onClick={handleExportPortfolio}
            >
              Exportar
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

      {/* overflow-clip, nao hidden: hidden faria do painel o conteiner do
          cabecalho grudento, e ele pararia de grudar ao rolar a pagina. */}
      <Panel className="overflow-clip">
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
            <div className="md:hidden">
              {assetGroups.map((group) => (
                <section key={group.key} className="border-b border-zinc-200 last:border-0">
                  <div className="flex items-baseline justify-between gap-3 bg-zinc-50 px-4 py-2">
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-600">{group.label}</h3>
                    <span className="text-xs text-zinc-500 tabular">{groupSummary(group, privateMoney)}</span>
                  </div>
                  <ul className="divide-y divide-zinc-100">
                    {group.assets.map((asset) => (
                      <PositionCard key={asset.id} {...rowProps(asset)} />
                    ))}
                  </ul>
                </section>
              ))}
            </div>

            <div className="hidden md:block">
              <table className="app-table table-fixed">
                <colgroup>
                  <col />
                  <col className="w-24" />
                  <col className="w-32" />
                  <col className="w-52" />
                  <col className="w-40" />
                  <col className="w-28" />
                  <col className="w-40" />
                </colgroup>
                <thead>
                  <tr>
                    <th>Ativo</th>
                    <th className="text-right">Qtd</th>
                    <th className="text-right">Preço médio</th>
                    <th className="text-right">Cotação</th>
                    <th className="text-right">Valor</th>
                    <th className="text-right">Rentab.</th>
                    <th><span className="sr-only">Ações</span></th>
                  </tr>
                </thead>
                {assetGroups.map((group) => (
                  <tbody key={group.key}>
                    <tr className="!border-b !border-zinc-200 bg-zinc-50 hover:!bg-zinc-50">
                      <th colSpan={7} scope="rowgroup" className="py-2">
                        <div className="flex items-baseline justify-between gap-3">
                          <span className="text-xs font-semibold uppercase tracking-wide text-zinc-600">{group.label}</span>
                          <span className="text-xs font-normal text-zinc-500 tabular">{groupSummary(group, privateMoney)}</span>
                        </div>
                      </th>
                    </tr>
                    {group.assets.map((asset) => (
                      <PositionRow key={asset.id} {...rowProps(asset)} />
                    ))}
                  </tbody>
                ))}
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

// Cotacao em uma linha: campo, atualizar e um ponto de status (verde = atual,
// ambar = desatualizada ou sem cotacao). Fonte e horario ficam no title do
// ponto e para leitor de tela.
function PriceEditor({ asset, isUpdatingPrices, isUpdatingThisAsset, onManualPrice, onRefresh, compact = false }) {
  const quote = asset.quote || {}
  const quoteStatus = quote.status || 'missing'
  const quoteIsFresh = quoteStatus === 'fresh'
  const isFixed = asset.class === 'FIXED_INCOME'
  // Na renda fixa a "cotacao" e o valor do titulo (quantidade 1).
  const masked = useValuesHidden() && isFixed
  const statusText = `${quoteStatusLabel(quoteStatus)} · ${quoteSourceLabel(quote.source)} · ${formatDateTime(quote.quoted_at)}`

  return (
    <div className={cx('flex items-center gap-1.5', compact && 'justify-end')}>
      <span
        className={cx('h-2 w-2 shrink-0 rounded-full', quoteIsFresh ? 'bg-emerald-500' : 'bg-amber-500')}
        title={statusText}
      />
      <span className="sr-only">{statusText}</span>
      {masked ? (
        <span className="w-28 text-right text-sm font-medium text-zinc-500">{MASKED_CURRENCY}</span>
      ) : (
        <input
          key={`${asset.id}-${asset.current_price}`}
          type="number"
          step="0.01"
          inputMode="decimal"
          aria-label={`Cotação de ${asset.name}`}
          defaultValue={asset.current_price}
          disabled={isFixed}
          onBlur={(e) => onManualPrice(asset, e)}
          className={cx('app-input h-9 w-28 py-1 text-right lg:h-8', isFixed && 'cursor-not-allowed bg-zinc-100 text-zinc-500')}
          title={isFixed ? 'Valor calculado automaticamente pela taxa do título' : 'Digite o novo preço e clique fora para salvar'}
        />
      )}
      <IconButton
        label="Atualizar cotação deste ativo"
        icon={RefreshCw}
        size="sm"
        onClick={onRefresh}
        disabled={isUpdatingPrices}
        className={cx('disabled:opacity-50', isUpdatingThisAsset && '[&>svg]:animate-spin')}
      />
    </div>
  )
}

// Liquido so existe na renda fixa (IR regressivo); acao e FII mostram o bruto.
function NetValue({ asset, money }) {
  if (asset.class !== 'FIXED_INCOME') return null
  return (
    <p className="text-xs text-zinc-500">
      líq. {money(asset.is_tax_free ? asset.current_value : asset.net_value)}{asset.is_tax_free ? ' · isento' : ''}
    </p>
  )
}

// Rentabilidade: a cor segue ganho/perda.
function Profit({ value }) {
  return (
    <span className={cx('font-semibold', value >= 0 ? 'text-emerald-700' : 'text-rose-600')}>
      {formatPercent(value, 2, { signed: true })}
    </span>
  )
}

function PositionRow({ asset, busy, onSell, onDelete, ...priceProps }) {
  const isFixed = asset.class === 'FIXED_INCOME'
  const hidden = useValuesHidden()
  const money = usePrivateFormatter(formatCurrency)
  const fixedDescription = isFixed ? describeFixedIncome(asset.metadata) : ''
  return (
    <tr>
      <td>
        <p className="truncate font-semibold text-zinc-950" title={asset.name}>{asset.name}</p>
        {fixedDescription ? <p className="truncate text-xs text-zinc-500">{fixedDescription}</p> : null}
      </td>
      <td className="num text-zinc-700">{isFixed ? '—' : hidden ? MASKED_TEXT : asset.quantity}</td>
      <td className="num text-zinc-700">{hidden && isFixed ? MASKED_CURRENCY : formatCurrency(asset.average_price)}</td>
      <td className="py-1.5"><PriceEditor asset={asset} compact {...priceProps} /></td>
      <td className="num">
        <p className="font-semibold text-zinc-950">{money(asset.current_value)}</p>
        <NetValue asset={asset} money={money} />
      </td>
      <td className="num"><Profit value={asset.profitability_percent} /></td>
      <td className="py-1.5 text-right">
        <div className="flex justify-end gap-1.5">
          <Button type="button" size="sm" variant="secondary" onClick={onSell} disabled={busy} className="lg:h-8">
            {isFixed ? 'Resgatar' : 'Vender'}
          </Button>
          <IconButton
            label={isFixed ? 'Excluir este aporte' : 'Excluir toda a posição'}
            icon={Trash2}
            size="sm"
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
  const hidden = useValuesHidden()
  const money = usePrivateFormatter(formatCurrency)
  return (
    <li className="space-y-3 px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-semibold text-zinc-950">{asset.name}</p>
          <p className="truncate text-xs text-zinc-500">
            {isFixed ? describeFixedIncome(asset.metadata) || getClassLabel(asset.class) : `${hidden ? MASKED_TEXT : asset.quantity} un.`}
            {` · PM ${hidden && isFixed ? MASKED_CURRENCY : formatCurrency(asset.average_price)}`}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="font-semibold text-zinc-950">{money(asset.current_value)}</p>
          <p className="text-sm"><Profit value={asset.profitability_percent} /></p>
        </div>
      </div>
      <div className="flex items-center justify-between gap-2">
        <PriceEditor asset={asset} {...priceProps} />
        <div className="flex gap-2">
          <Button type="button" size="lg" variant="secondary" onClick={onSell} disabled={busy}>
            {isFixed ? 'Resgatar' : 'Vender'}
          </Button>
          <IconButton
            label={isFixed ? 'Excluir este aporte' : 'Excluir toda a posição'}
            icon={Trash2}
            variant="danger"
            onClick={onDelete}
          />
        </div>
      </div>
    </li>
  )
}
