import { useState } from 'react'
import { Banknote, Briefcase, ChevronDown, Download, Info, Landmark, Pencil, Plus, RefreshCw, Trash2, TrendingUp, X } from 'lucide-react'
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
import { accountsApi, investmentsApi } from '../../lib/dataApi'
import { useQuery } from '../../lib/queries'
import { isPortfolioAccount, portfolioCashBalance } from '../../lib/transactions'
import { formatCurrency, formatDateBR, formatPercent, formatQuantity, formatSignedCurrency, getLocalDateString } from '../../lib/format'
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
import {
  allocateTreasuryRedemption,
  isMarketValued,
  treasuryMarketRateText,
  treasuryRateLabel,
  treasuryRateText,
} from '../../lib/treasury'
import { confirmAction } from '../../lib/confirm'
import ExportSheet from '../../components/ExportSheet'

const POSITION_TABS = [
  { value: 'VARIAVEL', label: 'Variável', icon: TrendingUp },
  { value: 'FIXA', label: 'Renda fixa', icon: Landmark },
  { value: 'TESOURO', label: 'Tesouro Direto', icon: Banknote },
]

// Tesouro Direto e a categoria TESOURO da renda fixa (`category` da posicao,
// services/asset_categories.py): aba propria, agrupada pelo indexador.
const isTreasury = (asset) => asset.category === 'TESOURO'
const RATE_KIND_ORDER = ['POS', 'PRE', 'IPCA']
const RATE_KIND_GROUP_LABELS = { POS: 'Pós-fixado (Selic)', PRE: 'Pré-fixado', IPCA: 'IPCA+' }
const NO_RATE_KIND = 'SEM_INDEXADOR'

// A classe STOCKS junta acao, ETF e BDR; a tela separa pelo tipo do papel
// (`market_kind`, do catalogo da B3). FII e Outros seguem a classe; o
// Bitcoin, dentro de Outros, tem o grupo dele (market_kind CRIPTO).
const VARIABLE_GROUP_ORDER = ['ACAO', 'ETF', 'BDR', 'FII', 'CRIPTO', 'OTHER']
const VARIABLE_GROUP_LABELS = {
  ACAO: 'Ações',
  ETF: 'ETFs',
  BDR: 'BDRs',
  FII: 'Fundos Imobiliários',
  CRIPTO: 'Cripto',
}

function variableGroupKey(asset) {
  if (asset.class === 'STOCKS') return asset.market_kind || 'ACAO'
  if (asset.class === 'REIT') return 'FII'
  if (asset.market_kind === 'CRIPTO') return 'CRIPTO'
  return asset.class
}
const FIXED_INCOME_TYPE_ORDER = FIXED_INCOME_TYPES.map((type) => type.value)
const NO_FIXED_INCOME_TYPE = 'SEM_TIPO'

// Subdivide a aba: renda variavel por tipo (Acoes, ETFs, BDRs, FIIs...), renda fixa pelo
// tipo do titulo (CDB, LCI...), Tesouro pelo indexador. Aporte antigo sem tipo cai em
// "Sem tipo", no fim.
function groupKeyAndLabel(asset, activeTab) {
  if (activeTab === 'TESOURO') {
    const key = asset.rate_kind || NO_RATE_KIND
    return [key, RATE_KIND_GROUP_LABELS[key] || 'Sem indexador']
  }
  if (activeTab === 'FIXA') {
    const key = asset.metadata?.fixed_income_type || NO_FIXED_INCOME_TYPE
    return [key, FIXED_INCOME_TYPES.find((type) => type.value === key)?.label || (key === NO_FIXED_INCOME_TYPE ? 'Sem tipo' : key)]
  }
  const key = variableGroupKey(asset)
  return [key, VARIABLE_GROUP_LABELS[key] || getClassLabel(key)]
}

function groupAssets(assets, activeTab) {
  const order = activeTab === 'TESOURO' ? RATE_KIND_ORDER : activeTab === 'FIXA' ? FIXED_INCOME_TYPE_ORDER : VARIABLE_GROUP_ORDER
  const groups = new Map()

  assets.forEach((asset) => {
    const [key, label] = groupKeyAndLabel(asset, activeTab)
    if (!groups.has(key)) {
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

// O cabecalho de um grupo abre e fecha os ativos dele; todos comecam fechados.
function GroupToggle({ group, open, onToggle, money }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className="flex min-h-11 w-full items-center gap-2 text-left xl:min-h-0"
    >
      <ChevronDown aria-hidden="true" className={cx('size-4 shrink-0 text-zinc-500 transition-transform', open ? '' : '-rotate-90')} />
      <span className="flex-1 text-xs font-semibold uppercase tracking-wide text-zinc-600">{group.label}</span>
      <span className="text-xs font-normal text-zinc-500 tabular">{groupSummary(group, money)}</span>
    </button>
  )
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
  // Grupos (Ações, ETFs, CDB...) abertos; comecam todos fechados.
  const [openGroups, setOpenGroups] = useState(() => new Set())
  const [loading, setLoading] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const [isLaunchModalOpen, setIsLaunchModalOpen] = useState(false)
  const [launchIntent, setLaunchIntent] = useState({ mode: 'BUY', assetId: '' })
  // Cotacao manual e resgate parcial: cada um num sheet (eram um campo em
  // toda linha e dois window.prompt).
  const [quoteFor, setQuoteFor] = useState(null)
  const [redeemFor, setRedeemFor] = useState(null)
  const [detailFor, setDetailFor] = useState(null)

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
  //
  // Tesouro Direto agrupado: um resgate por compra, das mais antigas para as
  // mais novas (PEPS, `allocateTreasuryRedemption()`), cada um apontando a sua.
  const handlePartialSale = async ({ asset, amount, date, cashLink }) => {
    setLoading(true)
    try {
      const parts = asset.lots?.length
        ? allocateTreasuryRedemption(asset.lots, amount)
        : [{ lotId: asset.id, amount, cost: asset.average_price * (amount / asset.current_value) }]

      await investmentsApi.create(parts.map((part) => ({
        asset_class: asset.class,
        ticker_or_name: asset.ticker || asset.name,
        quantity: -1,
        average_price: part.cost,
        current_price: part.amount,
        metadata: {
          is_redemption: true,
          affects_position: true,
          related_id: part.lotId,
          redemption_date: date,
          ...cashLinkMetadata(cashLink)
        }
      })))

      setRedeemFor(null)
      toast(`Resgate de ${formatCurrency(amount)} registrado nas operações.`)
      await refreshAll()
    } finally {
      setLoading(false)
    }
  }

  // A guarda do backend exige a classe junto do ativo: um DELETE por ativo sem
  // a asset_class correspondente e recusado.
  // Tesouro com mais de uma compra: todas as operacoes do titulo, como uma acao.
  const handleDeleteFullPosition = async (asset) => {
    const groupedTreasury = (asset.lots?.length || 0) > 1
    const singleBuy = asset.class === 'FIXED_INCOME' && !groupedTreasury
    if (await confirmAction({
      title: `Excluir ${singleBuy ? 'este aporte de' : 'toda a posição de'} ${asset.name}?`,
      message: singleBuy ? 'O aporte sai das operações.' : 'Todas as operações deste ativo saem do histórico.',
      confirmLabel: 'Excluir',
    })) {
      try {
        if (groupedTreasury) {
          for (const assetId of asset.asset_ids?.length ? asset.asset_ids : [asset.asset_id]) {
            await investmentsApi.removeByAsset(assetId, asset.class)
          }
        } else if (asset.class === 'FIXED_INCOME') {
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
    if (activeTab === 'FIXA') return asset.class === 'FIXED_INCOME' && !isTreasury(asset)
    if (activeTab === 'TESOURO') return isTreasury(asset)
    return true
  })
  const assetGroups = groupAssets(filteredAssets, activeTab)
  const toggleGroup = (key) => {
    setOpenGroups((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const rowProps = (asset) => ({
    asset,
    isUpdatingPrices,
    isUpdatingThisAsset: updatingAssetId === String(asset.asset_id || asset.id),
    busy: loading,
    onEditQuote: () => setQuoteFor(asset),
    onDetails: asset.treasury ? () => setDetailFor(asset) : undefined,
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
                  <h3 className="bg-zinc-50 px-4">
                    <GroupToggle group={group} open={openGroups.has(group.key)} onToggle={() => toggleGroup(group.key)} money={privateMoney} />
                  </h3>
                  {openGroups.has(group.key) ? (
                    <ul className="divide-y divide-zinc-100 border-t border-zinc-200">
                      {group.assets.map((asset) => (
                        activeTab === 'TESOURO'
                          ? <TreasuryCard key={asset.id} {...rowProps(asset)} />
                          : <PositionCard key={asset.id} {...rowProps(asset)} />
                      ))}
                    </ul>
                  ) : null}
                </section>
              ))}
            </div>

            <div className="hidden xl:block">
              {activeTab === 'TESOURO' ? (
                <TreasuryTable
                  groups={assetGroups}
                  openGroups={openGroups}
                  toggleGroup={toggleGroup}
                  money={privateMoney}
                  rowProps={rowProps}
                />
              ) : (
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
                        <GroupToggle group={group} open={openGroups.has(group.key)} onToggle={() => toggleGroup(group.key)} money={privateMoney} />
                      </th>
                    </tr>
                    {openGroups.has(group.key)
                      ? group.assets.map((asset) => <PositionRow key={asset.id} {...rowProps(asset)} />)
                      : null}
                  </tbody>
                ))}
              </table>
              )}
            </div>
          </>
        )}
      </Panel>

      {activeTab === 'TESOURO' && filteredAssets.length > 0 ? <TreasurySourceNote assets={filteredAssets} /> : null}

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
      <TreasuryDetailSheet asset={detailFor} onClose={() => setDetailFor(null)} />
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
//
// O saldo das contas Corretora aparece so aqui (dono, 2026-10-17): e o dinheiro
// da carteira que ainda nao virou ativo, e o Inicio nao o conta.
function PortfolioSummary({ totals }) {
  const money = usePrivateFormatter(formatCurrency)
  const hidden = useValuesHidden()
  const result = totals.value - totals.invested
  const resultPercent = totals.invested > 0 ? (result / totals.invested) * 100 : 0
  const accountsQuery = useQuery({ queryKey: ['contas', 'ativas'], queryFn: () => accountsApi.list() })
  const brokerages = (accountsQuery.data || []).filter(isPortfolioAccount)
  const cashFigure = brokerages.length
    ? [{
        label: 'Saldo na corretora',
        value: money(portfolioCashBalance(brokerages)),
        hint: brokerages.length === 1 ? brokerages[0].name : `${brokerages.length} contas Corretora`,
      }]
    : []
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
        { label: 'Líquido estimado', value: money(totals.netValue), hint: 'Após IR e custódia da renda fixa' },
        ...cashFigure,
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
        <Field
          label="Valor bruto a resgatar (R$)"
          hint={(openedFor?.lots?.length || 0) > 1
            ? 'Sai primeiro das compras mais antigas, como no Tesouro; o custo resgatado é proporcional ao valor.'
            : 'O custo resgatado é proporcional a este valor.'}
        >
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
  // O PU de mercado do Tesouro e publico; o valor de um titulo na curva, nao.
  const masked = useValuesHidden() && isFixed && !isMarketValued(asset)
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
function positionMenuItems(asset, { isUpdatingPrices, onEditQuote, onRefresh, onDelete, onDetails }) {
  const isFixed = asset.class === 'FIXED_INCOME'
  const singleBuy = isFixed && (asset.lots?.length || 0) <= 1
  return [
    ...(onDetails ? [{ label: 'Detalhes do título', icon: Info, onSelect: onDetails }] : []),
    ...(isFixed ? [] : [{ label: 'Editar cotação', icon: Pencil, onSelect: onEditQuote }]),
    ...(isUpdatingPrices ? [] : [{ label: isFixed ? 'Atualizar valor' : 'Atualizar cotação', icon: RefreshCw, onSelect: onRefresh }]),
    { label: singleBuy ? 'Excluir este aporte' : 'Excluir toda a posição', icon: Trash2, tone: 'danger', onSelect: onDelete },
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

// Titulos do Tesouro: duas casas, como o extrato da corretora ("0,85").
function formatUnits(value) {
  return Number(value || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function TreasuryRateLine({ asset }) {
  const text = treasuryRateLabel(asset) || describeFixedIncome(asset.metadata)
  return text ? <p className="text-xs text-zinc-500">{text}</p> : null
}

// Aba Tesouro Direto: uma linha por titulo (as compras do mesmo titulo juntas),
// com vencimento, quantidade de titulos e os saldos liquido e bruto -- a leitura
// do extrato da corretora.
function TreasuryTable({ groups, openGroups, toggleGroup, money, rowProps }) {
  return (
    <table className="app-table table-fixed">
      <colgroup>
        <col />
        <col className="w-28" />
        <col className="w-24" />
        <col className="w-36" />
        <col className="w-40" />
        <col className="w-36" />
        <col className="w-24" />
        <col className="w-36" />
      </colgroup>
      <thead>
        <tr>
          <th>Título</th>
          <th className="text-right">Vencimento</th>
          <th className="text-right">Quantidade</th>
          <th className="text-right" title="Preço unitário de venda do dia, do Tesouro Nacional">PU</th>
          <th className="text-right" title="Bruto menos custódia da B3, IOF e IR, se vendido hoje">Saldo líquido</th>
          <th className="text-right" title="Títulos x PU de mercado">Saldo bruto</th>
          <th className="text-right">Rentab.</th>
          <th><span className="sr-only">Ações</span></th>
        </tr>
      </thead>
      {groups.map((group) => (
        <tbody key={group.key}>
          <tr className="!border-b !border-zinc-200 bg-zinc-50 hover:!bg-zinc-50">
            <th colSpan={8} scope="rowgroup" className="py-2">
              <GroupToggle group={group} open={openGroups.has(group.key)} onToggle={() => toggleGroup(group.key)} money={money} />
            </th>
          </tr>
          {openGroups.has(group.key)
            ? group.assets.map((asset) => <TreasuryRow key={asset.id} {...rowProps(asset)} />)
            : null}
        </tbody>
      ))}
    </table>
  )
}

function TreasuryRow({ asset, busy, onSell, isUpdatingThisAsset, ...menuProps }) {
  const hidden = useValuesHidden()
  const money = usePrivateFormatter(formatCurrency)
  const treasury = asset.treasury || {}
  return (
    <tr>
      <td>
        <p className="font-semibold text-zinc-950 [overflow-wrap:anywhere]">{asset.name}</p>
        <TreasuryRateLine asset={asset} />
      </td>
      <td className="num text-zinc-700">{treasury.maturity_date ? formatDateBR(treasury.maturity_date) : '—'}</td>
      <td className="num text-zinc-700">{treasury.units != null ? (hidden ? MASKED_TEXT : formatUnits(treasury.units)) : '—'}</td>
      <td className="num"><QuoteValue asset={asset} isUpdatingThisAsset={isUpdatingThisAsset} /></td>
      <td className="num font-semibold text-zinc-950">{money(asset.net_value)}</td>
      <td className="num text-zinc-700">{money(asset.current_value)}</td>
      <td className="num"><Profit value={asset.profitability_percent} /></td>
      <td className="py-1.5 text-right">
        <div className="flex justify-end gap-1.5">
          <Button type="button" size="sm" variant="secondary" onClick={onSell} disabled={busy} className="lg:h-8">
            Resgatar
          </Button>
          <Menu label={`Mais ações para ${asset.name}`} items={positionMenuItems(asset, menuProps)} />
        </div>
      </td>
    </tr>
  )
}

function TreasuryCard({ asset, busy, onSell, isUpdatingThisAsset, ...menuProps }) {
  const hidden = useValuesHidden()
  const money = usePrivateFormatter(formatCurrency)
  const treasury = asset.treasury || {}
  const facts = [
    treasury.maturity_date ? `Venc. ${formatDateBR(treasury.maturity_date)}` : null,
    treasury.units != null ? `${hidden ? MASKED_TEXT : formatUnits(treasury.units)} títulos` : null,
  ].filter(Boolean).join(' · ')
  return (
    <li className="space-y-3 px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-zinc-950 [overflow-wrap:anywhere]">{asset.name}</p>
          {facts ? <p className="text-xs text-zinc-500 tabular">{facts}</p> : null}
          <TreasuryRateLine asset={asset} />
        </div>
        <div className="shrink-0 text-right">
          <p className="font-semibold text-zinc-950">{money(asset.net_value)}</p>
          <p className="text-xs text-zinc-500">bruto {money(asset.current_value)}</p>
          <p className="text-sm"><Profit value={asset.profitability_percent} /></p>
        </div>
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm tabular">
          <QuoteValue asset={asset} isUpdatingThisAsset={isUpdatingThisAsset} />
        </span>
        <div className="flex gap-2">
          <Button type="button" size="lg" variant="secondary" onClick={onSell} disabled={busy}>
            Resgatar
          </Button>
          <Menu label={`Mais ações para ${asset.name}`} size="md" items={positionMenuItems(asset, menuProps)} />
        </div>
      </div>
    </li>
  )
}

// De onde vem o valor: o PU do Tesouro Nacional na data base, ou a curva.
function TreasurySourceNote({ assets }) {
  const onCurve = assets.filter((asset) => !isMarketValued(asset))
  const dates = assets.map((asset) => asset.treasury?.price_date).filter(Boolean).sort()
  const priceDate = dates.length ? dates[dates.length - 1] : null
  return (
    <div className="space-y-2 text-xs text-zinc-500">
      {priceDate ? (
        <p>
          Marcação a mercado pelo PU de venda do Tesouro Nacional (Tesouro Transparente), data base {formatDateBR(priceDate)}.
          Saldo líquido = bruto − custódia da B3 (0,20% a.a.) − IOF − IR, como se vendido hoje.
        </p>
      ) : null}
      {onCurve.length ? (
        <AlertMessage tone="info">
          {`Sem o preço do Tesouro para ${onCurve.map((asset) => asset.name).join(', ')}: o valor segue a curva da taxa contratada. `}
          Confira se o nome traz o tipo e o ano do título (ex.: Tesouro IPCA+ 2045).
        </AlertMessage>
      ) : null}
    </div>
  )
}

function DetailFigure({ label, value, hint }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5">
      <dt className="text-sm text-zinc-600">{label}</dt>
      <dd className="text-right text-sm font-semibold text-zinc-950 tabular">
        {value}
        {hint ? <span className="block text-xs font-normal text-zinc-500">{hint}</span> : null}
      </dd>
    </div>
  )
}

function TreasuryDetailSheet({ asset, onClose }) {
  const [shown, setShown] = useState(null)
  if (asset && asset !== shown) setShown(asset)
  const money = usePrivateFormatter(formatCurrency)
  const hidden = useValuesHidden()
  const current = asset || shown
  const treasury = current?.treasury || {}
  const lots = current?.lots || []
  const marketRate = current ? treasuryMarketRateText(current) : ''
  return (
    <Sheet
      open={Boolean(asset)}
      onClose={onClose}
      title={current?.name || 'Título'}
      description={treasury.maturity_date ? `Vence em ${formatDateBR(treasury.maturity_date)}` : undefined}
      footer={(
        <div className="flex justify-end">
          <Button type="button" variant="secondary" size="lg" onClick={onClose}>Fechar</Button>
        </div>
      )}
    >
      {current ? (
        <div className="space-y-5">
          {treasury.valuation !== 'MARKET' ? (
            <AlertMessage tone="info">
              Sem o preço do Tesouro para este título agora: o valor segue a curva da taxa contratada.
            </AlertMessage>
          ) : null}
          <dl className="divide-y divide-zinc-100">
            <DetailFigure label="Saldo bruto" value={money(current.current_value)} hint={treasury.units != null ? `${hidden ? MASKED_TEXT : formatUnits(treasury.units)} títulos` : undefined} />
            <DetailFigure label="Custódia da B3" value={money(treasury.custody)} hint="0,20% a.a., provisionada" />
            {Number(treasury.iof) > 0 ? <DetailFigure label="IOF" value={money(treasury.iof)} /> : null}
            <DetailFigure label="IR" value={money(treasury.income_tax)} hint="Tabela regressiva, compra a compra" />
            <DetailFigure label="Saldo líquido" value={money(current.net_value)} />
            <DetailFigure label="Valor aplicado" value={money(current.total_invested)} />
          </dl>
          <dl className="divide-y divide-zinc-100">
            {treasury.market_pu ? (
              <DetailFigure label="PU de venda" value={formatCurrency(treasury.market_pu)} hint={treasury.price_date ? `Data base ${formatDateBR(treasury.price_date)}` : undefined} />
            ) : null}
            {marketRate ? <DetailFigure label="Taxa de mercado hoje" value={marketRate} /> : null}
            <DetailFigure label={(treasury.lot_count || 0) > 1 ? 'Sua taxa média' : 'Sua taxa'} value={treasuryRateText(treasury.average_rate, current.metadata) || '—'} />
          </dl>
          {lots.length ? (
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-600">
                {lots.length === 1 ? 'Compra' : `${lots.length} compras`}
              </h3>
              <ul className="divide-y divide-zinc-100 rounded-lg border border-zinc-200">
                {lots.map((lot) => (
                  <li key={lot.id} className="space-y-0.5 px-3 py-2 text-sm">
                    <div className="flex justify-between gap-3">
                      <span className="font-semibold text-zinc-950">{formatDateBR(lot.purchase_date)}</span>
                      <span className="tabular text-zinc-950">{money(lot.net)}</span>
                    </div>
                    <div className="flex justify-between gap-3 text-xs text-zinc-500 tabular">
                      <span>
                        {[
                          treasuryRateText(lot.rate, current.metadata),
                          lot.units != null ? `${hidden ? MASKED_TEXT : formatUnits(lot.units)} títulos` : null,
                        ].filter(Boolean).join(' · ')}
                      </span>
                      <span>aplicado {money(lot.invested)} · bruto {money(lot.gross)}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </Sheet>
  )
}
