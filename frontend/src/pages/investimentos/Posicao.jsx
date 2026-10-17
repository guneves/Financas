import { useState } from 'react'
import { Briefcase, Download, Landmark, Pencil, Plus, RefreshCw, Trash2, TrendingUp, X } from 'lucide-react'
import InvestmentLaunchModal from '../../components/InvestmentLaunchModal'
import CashLinkField, { cashLinkMetadata, emptyCashLink } from '../../components/CashLinkField'
import {
  AlertMessage,
  Button,
  EmptyState,
  ListSkeleton,
  Field,
  IconButton,
  Menu,
  PageHeader,
  Panel,
  PanelHeader,
  SegmentedControl,
  Sheet,
  SummaryPanel,
  cx,
} from '../../components/ui'
import { investmentsApi } from '../../lib/dataApi'
import { formatCurrency, formatPercent, formatQuantity, formatSignedCurrency, getLocalDateString } from '../../lib/format'
import { MASKED_CURRENCY, MASKED_TEXT, usePrivateFormatter, useValuesHidden } from '../../lib/privacy'
import { toast } from '../../lib/toast'
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
import { confirmAction } from '../../lib/confirm'
import ExportSheet from '../../components/ExportSheet'

const POSITION_TABS = [
  { value: 'VARIAVEL', label: 'Variável', icon: TrendingUp },
  { value: 'FIXA', label: 'Renda fixa', icon: Landmark },
]

// A classe STOCKS junta acao, ETF e BDR; a tela separa pelo tipo do papel
// (`market_kind`, do catalogo da B3). FII e Outros seguem a classe.
const VARIABLE_GROUP_ORDER = ['ACAO', 'ETF', 'BDR', 'FII', 'OTHER']
const VARIABLE_GROUP_LABELS = {
  ACAO: 'Ações',
  ETF: 'ETFs',
  BDR: 'BDRs',
  FII: 'Fundos Imobiliários',
}

function variableGroupKey(asset) {
  if (asset.class === 'STOCKS') return asset.market_kind || 'ACAO'
  if (asset.class === 'REIT') return 'FII'
  return asset.class
}
const FIXED_INCOME_TYPE_ORDER = FIXED_INCOME_TYPES.map((type) => type.value)
const NO_FIXED_INCOME_TYPE = 'SEM_TIPO'

// Subdivide a aba: renda variavel por tipo (Acoes, ETFs, BDRs, FIIs...), renda fixa pelo
// tipo do titulo (CDB, LCI...). Aporte antigo sem tipo cai em "Sem tipo", no fim.
function groupAssets(assets, activeTab) {
  const isFixedTab = activeTab === 'FIXA'
  const order = isFixedTab ? FIXED_INCOME_TYPE_ORDER : VARIABLE_GROUP_ORDER
  const groups = new Map()

  assets.forEach((asset) => {
    const key = isFixedTab
      ? (asset.metadata?.fixed_income_type || NO_FIXED_INCOME_TYPE)
      : variableGroupKey(asset)
    if (!groups.has(key)) {
      const label = isFixedTab
        ? (FIXED_INCOME_TYPES.find((type) => type.value === key)?.label || (key === NO_FIXED_INCOME_TYPE ? 'Sem tipo' : key))
        : (VARIABLE_GROUP_LABELS[key] || getClassLabel(key))
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
    loading: portfolioLoading,
    assets,
    totals,
    dataError,
    setDataError,
    refreshAll,
    handleUpdateStockPrices,
    isUpdatingPrices,
    updatingAssetId,
    quoteUpdateResult,
    setQuoteUpdateResult,
  } = useInvestments()

  const [activeTab, setActiveTab] = useState('VARIAVEL')
  const [loading, setLoading] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const [isLaunchModalOpen, setIsLaunchModalOpen] = useState(false)
  const [launchIntent, setLaunchIntent] = useState({ mode: 'BUY', assetId: '' })
  // Cotacao manual e resgate parcial: cada um num sheet (eram um campo em
  // toda linha e dois window.prompt).
  const [quoteFor, setQuoteFor] = useState(null)
  const [redeemFor, setRedeemFor] = useState(null)

  // Exporta a carteira como ela esta agora; nao forca atualizacao de cotacao.
  const handleExportPortfolio = (options) => investmentsApi.exportPortfolio(options)

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

  // Resgate parcial de renda fixa: a base de custo resgatada e proporcional
  // ao valor bruto resgatado. Entra na conta da carteira, a nao ser que o
  // sheet marque "Não descontar" (`cashLink`); um erro volta para o sheet.
  const handlePartialSale = async ({ asset, amount, date, cashLink }) => {
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
            redemption_date: date,
            ...cashLinkMetadata(cashLink)
          }
        }
      ])

      setRedeemFor(null)
      toast(`Resgate de ${formatCurrency(amount)} registrado nas operações.`)
      await refreshAll()
    } finally {
      setLoading(false)
    }
  }

  // A guarda do backend exige a classe junto do ativo: um DELETE por ativo sem
  // a asset_class correspondente e recusado.
  const handleDeleteFullPosition = async (asset) => {
    if (await confirmAction({
      title: `Excluir ${asset.class === 'FIXED_INCOME' ? 'este aporte de' : 'toda a posição de'} ${asset.name}?`,
      message: asset.class === 'FIXED_INCOME' ? 'O aporte sai das operações.' : 'Todas as operações deste ativo saem do histórico.',
      confirmLabel: 'Excluir',
    })) {
      try {
        if (asset.class === 'FIXED_INCOME') {
          await investmentsApi.remove(asset.id)
        } else {
          const assetId = asset.asset_id || asset.id
          await investmentsApi.removeByAsset(assetId, asset.class)
        }

        await refreshAll()
      } catch (error) {
        setDataError(error.message || 'Não foi possível excluir a posição.')
      }
    }
  }

  // Cotacao digitada a mao (acao sem fonte, "outros"). A renda fixa
  // nao passa por aqui: o valor dela vem da taxa do titulo.
  const handleManualPrice = async (asset, price) => {
    const assetId = asset.asset_id || asset.id
    await investmentsApi.updatePriceByAsset(assetId, asset.class, price)
    setQuoteFor(null)
    setDataError('')
    toast(`Cotação de ${asset.name} salva.`)
    await refreshAll()
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
    onEditQuote: () => setQuoteFor(asset),
    onRefresh: () => handleUpdateStockPrices(false, null, asset),
    onSell: () => (asset.class === 'FIXED_INCOME' ? setRedeemFor(asset) : handleSellVariable(asset)),
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
              disabled={assets.length === 0}
              onClick={() => setExportOpen(true)}
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

      {assets.length > 0 && totals ? <PortfolioSummary totals={totals} /> : null}

      {assets.length > 0 ? (
        <PortfolioOverview assets={assets} getClassLabel={getClassLabel} />
      ) : null}

      <SegmentedControl items={POSITION_TABS} value={activeTab} onChange={setActiveTab} />

      {/* overflow-clip, nao hidden: hidden faria do painel o conteiner do
          cabecalho grudento, e ele pararia de grudar ao rolar a pagina. */}
      <Panel className="overflow-clip">
        {portfolioLoading ? (
          <ListSkeleton rows={6} />
        ) : filteredAssets.length === 0 ? (
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
            <div className="xl:hidden">
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

            <div className="hidden xl:block">
              <table className="app-table table-fixed">
                <colgroup>
                  <col />
                  <col className="w-24" />
                  <col className="w-28" />
                  <col className="w-36" />
                  <col className="w-40" />
                  <col className="w-24" />
                  <col className="w-32" />
                  <col className="w-28" />
                  <col className="w-36" />
                </colgroup>
                <thead>
                  <tr>
                    <th>Ativo</th>
                    <th className="text-right">Qtd</th>
                    <th className="text-right">Preço médio</th>
                    <th className="text-right">Cotação</th>
                    <th className="text-right">Valor</th>
                    <th className="text-right">Rentab.</th>
                    <th className="text-right">Proventos</th>
                    <th className="text-right" title="Preço, proventos recebidos e lucro realizado sobre tudo o que entrou no ativo">Rentab. c/ proventos</th>
                    <th><span className="sr-only">Ações</span></th>
                  </tr>
                </thead>
                {assetGroups.map((group) => (
                  <tbody key={group.key}>
                    <tr className="!border-b !border-zinc-200 bg-zinc-50 hover:!bg-zinc-50">
                      <th colSpan={9} scope="rowgroup" className="py-2">
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

      <QuoteSheet asset={quoteFor} onClose={() => setQuoteFor(null)} onSave={handleManualPrice} />
      <RedeemSheet asset={redeemFor} onClose={() => setRedeemFor(null)} onSave={handlePartialSale} />
      <ExportSheet
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        exportName="portfolio"
        title="Exportar carteira"
        description="Posições como estão agora, com as últimas cotações salvas."
        onExport={handleExportPortfolio}
      />
    </div>
  )
}

// Carteira em um bloco: valor bruto em destaque, aplicado, resultado e o
// liquido estimado (IR regressivo da renda fixa), como o backend soma. Os
// valores somem no modo privado; o percentual fica, como a rentabilidade.
function PortfolioSummary({ totals }) {
  const money = usePrivateFormatter(formatCurrency)
  const hidden = useValuesHidden()
  const result = totals.value - totals.invested
  const resultPercent = totals.invested > 0 ? (result / totals.invested) * 100 : 0
  return (
    <SummaryPanel
      lead={{ label: 'Carteira', value: money(totals.value), hint: 'Valor de mercado bruto' }}
      figures={[
        { label: 'Valor aplicado', value: money(totals.invested), hint: 'Custo das posições abertas' },
        {
          label: 'Resultado',
          value: hidden ? MASKED_CURRENCY : formatSignedCurrency(result),
          hint: `${formatPercent(resultPercent, 2, { signed: true })} bruto`,
          tone: hidden ? 'neutral' : result >= 0 ? 'gain' : 'loss',
        },
        { label: 'Líquido estimado', value: money(totals.netValue), hint: 'Após o IR da renda fixa' },
      ]}
    />
  )
}

function QuoteSheet({ asset, onClose, onSave }) {
  const [value, setValue] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [openedFor, setOpenedFor] = useState(null)
  // Abriu para outro ativo: recomeca do preco dele.
  if (asset && asset !== openedFor) {
    setOpenedFor(asset)
    setValue(String(asset.current_price ?? '').replace('.', ','))
    setError('')
  }

  const submit = async (event) => {
    event.preventDefault()
    const price = parseNumberInput(value)
    if (!Number.isFinite(price) || price < 0) {
      setError('Informe uma cotação válida.')
      return
    }
    setSaving(true)
    try {
      await onSave(asset, price)
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível atualizar a cotação.')
    } finally {
      setSaving(false)
    }
  }

  const quote = openedFor?.quote || {}
  return (
    <Sheet
      open={Boolean(asset)}
      onClose={onClose}
      title="Editar cotação"
      description={openedFor ? `${openedFor.name} · ${quoteSourceLabel(quote.source)}, ${formatDateTime(quote.quoted_at)}` : undefined}
      footer={(
        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <Button type="button" variant="secondary" size="lg" onClick={onClose}>Cancelar</Button>
          <Button type="submit" form="quote-edit" size="lg" loading={saving}>Salvar cotação</Button>
        </div>
      )}
    >
      <form id="quote-edit" onSubmit={submit} className="space-y-4">
        <AlertMessage message={error} />
        <Field label="Cotação (R$)" hint="Um ativo com fonte de mercado volta ao preço da fonte na próxima atualização.">
          <input
            type="text"
            inputMode="decimal"
            autoFocus
            value={value}
            onChange={(event) => setValue(event.target.value)}
            className="app-input"
            required
          />
        </Field>
      </form>
    </Sheet>
  )
}

function RedeemSheet({ asset, onClose, onSave }) {
  const [form, setForm] = useState({ amount: '', date: '' })
  const [cashLink, setCashLink] = useState(emptyCashLink)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [openedFor, setOpenedFor] = useState(null)
  if (asset && asset !== openedFor) {
    setOpenedFor(asset)
    setForm({ amount: '', date: getLocalDateString() })
    setCashLink(emptyCashLink())
    setError('')
  }

  const submit = async (event) => {
    event.preventDefault()
    const amount = parseNumberInput(form.amount)
    if (!Number.isFinite(amount) || amount <= 0 || amount > asset.current_value) {
      setError(`Informe um valor entre R$ 0,01 e ${formatCurrency(asset.current_value)}.`)
      return
    }
    if (!form.date) {
      setError('Informe a data do resgate.')
      return
    }
    setSaving(true)
    try {
      await onSave({ asset, amount, date: form.date, cashLink })
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível registrar o resgate.')
    } finally {
      setSaving(false)
    }
  }

  // O valor atual do titulo e carteira: some no modo privado.
  const money = usePrivateFormatter(formatCurrency)
  return (
    <Sheet
      open={Boolean(asset)}
      onClose={onClose}
      title="Resgate parcial"
      description={openedFor ? `${openedFor.name} · valor bruto atual ${money(openedFor.current_value)}` : undefined}
      footer={(
        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <Button type="button" variant="secondary" size="lg" onClick={onClose}>Cancelar</Button>
          <Button type="submit" form="redeem-partial" size="lg" loading={saving}>Registrar resgate</Button>
        </div>
      )}
    >
      <form id="redeem-partial" onSubmit={submit} className="space-y-4">
        <AlertMessage message={error} />
        <Field label="Valor bruto a resgatar (R$)" hint="O custo resgatado é proporcional a este valor.">
          <input
            type="text"
            inputMode="decimal"
            autoFocus
            placeholder="0,00"
            value={form.amount}
            onChange={(event) => setForm({ ...form, amount: event.target.value })}
            className="app-input"
            required
          />
        </Field>
        <Field label="Data do resgate">
          <input
            type="date"
            value={form.date}
            onChange={(event) => setForm({ ...form, date: event.target.value })}
            className="app-input"
            required
          />
        </Field>
        <CashLinkField
          value={cashLink}
          onChange={setCashLink}
          movementType="REDEMPTION"
          selectClassName="app-select"
          enabled={Boolean(asset)}
        />
      </form>
    </Sheet>
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

// Cotacao so para ler: um ponto de status (verde = atual, ambar =
// desatualizada ou sem cotacao) e o preco. Fonte e horario ficam no title do
// ponto e para leitor de tela. Editar e atualizar moram no menu da linha.
function QuoteValue({ asset, isUpdatingThisAsset }) {
  const quote = asset.quote || {}
  const quoteStatus = quote.status || 'missing'
  const quoteIsFresh = quoteStatus === 'fresh'
  const isFixed = asset.class === 'FIXED_INCOME'
  // Na renda fixa a "cotacao" e o valor do titulo (quantidade 1).
  const masked = useValuesHidden() && isFixed
  const statusText = `${quoteStatusLabel(quoteStatus)} · ${quoteSourceLabel(quote.source)} · ${formatDateTime(quote.quoted_at)}`

  return (
    <span className="inline-flex items-center justify-end gap-2" title={statusText}>
      {isUpdatingThisAsset ? (
        <RefreshCw className="h-3 w-3 shrink-0 animate-spin text-zinc-500" aria-hidden="true" />
      ) : (
        <span className={cx('h-2 w-2 shrink-0 rounded-full', quoteIsFresh ? 'bg-emerald-500' : 'bg-amber-500')} aria-hidden="true" />
      )}
      <span className="sr-only">{statusText}</span>
      <span className="text-zinc-700">
        {masked ? MASKED_CURRENCY : formatCurrency(asset.current_price)}
      </span>
    </span>
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

// Rentabilidade: a cor segue ganho/perda; zero fica neutro.
function Profit({ value }) {
  const tone = value > 0 ? 'text-emerald-700' : value < 0 ? 'text-rose-600' : 'text-zinc-500'
  return (
    <span className={cx('font-semibold', tone)}>
      {formatPercent(value, 2, { signed: true })}
    </span>
  )
}

// Acoes raras da linha, atras do "⋯". Renda fixa nao tem "Editar cotação":
// o valor dela vem da taxa do titulo.
function positionMenuItems(asset, { isUpdatingPrices, onEditQuote, onRefresh, onDelete }) {
  const isFixed = asset.class === 'FIXED_INCOME'
  return [
    ...(isFixed ? [] : [{ label: 'Editar cotação', icon: Pencil, onSelect: onEditQuote }]),
    ...(isUpdatingPrices ? [] : [{ label: isFixed ? 'Atualizar valor' : 'Atualizar cotação', icon: RefreshCw, onSelect: onRefresh }]),
    { label: isFixed ? 'Excluir este aporte' : 'Excluir toda a posição', icon: Trash2, tone: 'danger', onSelect: onDelete },
  ]
}

function PositionRow({ asset, busy, onSell, isUpdatingThisAsset, ...menuProps }) {
  const isFixed = asset.class === 'FIXED_INCOME'
  const hidden = useValuesHidden()
  const money = usePrivateFormatter(formatCurrency)
  const fixedDescription = isFixed ? describeFixedIncome(asset.metadata) : ''
  return (
    <tr>
      <td>
        {/* Sem truncate: o ticker e o nome do titulo quebram, nunca viram "PETR…". */}
        <p className="font-semibold text-zinc-950 [overflow-wrap:anywhere]">{asset.name}</p>
        {fixedDescription ? <p className="text-xs text-zinc-500">{fixedDescription}</p> : null}
      </td>
      <td className="num text-zinc-700">{isFixed ? '—' : hidden ? MASKED_TEXT : formatQuantity(asset.quantity)}</td>
      <td className="num text-zinc-700">{hidden && isFixed ? MASKED_CURRENCY : formatCurrency(asset.average_price)}</td>
      <td className="num"><QuoteValue asset={asset} isUpdatingThisAsset={isUpdatingThisAsset} /></td>
      <td className="num">
        <p className="font-semibold text-zinc-950">{money(asset.current_value)}</p>
        <NetValue asset={asset} money={money} />
      </td>
      <td className="num"><Profit value={asset.profitability_percent} /></td>
      <td className="num">
        <p className="text-zinc-700">{money(asset.proceeds_net)}</p>
        {Number(asset.dividend_yield_12m) > 0 ? (
          <p className="text-xs text-zinc-500">DY 12m {formatPercent(asset.dividend_yield_12m)}</p>
        ) : null}
      </td>
      <td className="num"><Profit value={asset.total_return_percent} /></td>
      <td className="py-1.5 text-right">
        <div className="flex justify-end gap-1.5">
          <Button type="button" size="sm" variant="secondary" onClick={onSell} disabled={busy} className="lg:h-8">
            {isFixed ? 'Resgatar' : 'Vender'}
          </Button>
          <Menu label={`Mais ações para ${asset.name}`} items={positionMenuItems(asset, menuProps)} />
        </div>
      </td>
    </tr>
  )
}

function PositionCard({ asset, busy, onSell, isUpdatingThisAsset, ...menuProps }) {
  const isFixed = asset.class === 'FIXED_INCOME'
  const hidden = useValuesHidden()
  const money = usePrivateFormatter(formatCurrency)
  return (
    <li className="space-y-3 px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-zinc-950 [overflow-wrap:anywhere]">{asset.name}</p>
          <p className="truncate text-xs text-zinc-500">
            {isFixed ? describeFixedIncome(asset.metadata) || getClassLabel(asset.class) : `${hidden ? MASKED_TEXT : formatQuantity(asset.quantity)} un.`}
            {` · PM ${hidden && isFixed ? MASKED_CURRENCY : formatCurrency(asset.average_price)}`}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="font-semibold text-zinc-950">{money(asset.current_value)}</p>
          <p className="text-sm"><Profit value={asset.profitability_percent} /></p>
        </div>
      </div>
      {/* Proventos recebidos e a rentabilidade com eles, ao lado da de preco. */}
      <p className="flex flex-wrap justify-between gap-x-3 text-xs text-zinc-600 tabular">
        <span>Proventos {money(asset.proceeds_net)}</span>
        <span>c/ proventos <Profit value={asset.total_return_percent} /></span>
      </p>
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm tabular">
          <QuoteValue asset={asset} isUpdatingThisAsset={isUpdatingThisAsset} />
        </span>
        <div className="flex gap-2">
          <Button type="button" size="lg" variant="secondary" onClick={onSell} disabled={busy}>
            {isFixed ? 'Resgatar' : 'Vender'}
          </Button>
          <Menu label={`Mais ações para ${asset.name}`} size="md" items={positionMenuItems(asset, menuProps)} />
        </div>
      </div>
    </li>
  )
}
