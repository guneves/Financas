import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, Scale, Sparkles, Target } from 'lucide-react'
import { allocationApi } from '../../lib/dataApi'
import { formatCurrency, formatPercent } from '../../lib/format'
import { usePrivateFormatter } from '../../lib/privacy'
import { invalidateServerData, keepPreviousData, queryErrorMessage, useQuery } from '../../lib/queries'
import { toast } from '../../lib/toast'
import useDebouncedValue from '../../lib/useDebouncedValue'
import {
  AlertMessage,
  Badge,
  Button,
  EmptyState,
  Expand,
  Field,
  ListSkeleton,
  PageHeader,
  Panel,
  PanelHeader,
  Sheet,
  cx,
} from '../../components/ui'
import { getClassLabel } from './helpers'
import SectorAllocation from './SectorAllocation'

const CLASS_ORDER = ['STOCKS', 'REIT', 'FIXED_INCOME', 'OTHER']
// Desvio que pede atencao (pontos percentuais). Abaixo disso, "no plano".
const DRIFT_WARNING = 5

function sumOf(values) {
  return values.reduce((acc, value) => acc + (Number(String(value).replace(',', '.')) || 0), 0)
}

function toNumber(value) {
  return Number(String(value).replace(',', '.'))
}

// "Faltam R$ 1.000,00" / "R$ 1.000,00 acima" / "Na meta", a partir de gap = meta - atual.
function gapText(gap, money) {
  if (gap === null || gap === undefined) return ''
  if (Math.abs(gap) < 0.01) return 'Na meta'
  return gap > 0 ? `Faltam ${money(gap)}` : `${money(Math.abs(gap))} acima`
}

function DriftBadge({ diff }) {
  if (diff === null || diff === undefined) return <Badge>Sem meta</Badge>
  const tone = Math.abs(diff) >= DRIFT_WARNING ? 'warning' : 'neutral'
  const label = Math.abs(diff) < 0.01 ? 'Na meta' : `${formatPercent(diff, 1, { signed: true })} p.p.`
  return <Badge tone={tone}>{label}</Badge>
}

// Barra do atual com um traco na meta: ver de longe quem esta acima ou abaixo.
function AllocationBar({ percent, target }) {
  const width = Math.min(Math.max(Number(percent || 0), 0), 100)
  return (
    <div className="relative h-2 w-full rounded-full bg-zinc-100">
      <div className="bar-grow h-full rounded-full bg-emerald-500" style={{ width: `${width}%` }} />
      {target !== null && target !== undefined ? (
        <span
          className="absolute -top-1 h-4 w-0.5 rounded-full bg-zinc-950"
          style={{ left: `calc(${Math.min(Math.max(target, 0), 100)}% - 1px)` }}
          aria-hidden="true"
        />
      ) : null}
    </div>
  )
}

function TargetsSheet({ open, onClose, allocation }) {
  const [classes, setClasses] = useState({})
  const [assets, setAssets] = useState({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  // Ao abrir, parte das metas gravadas.
  useEffect(() => {
    if (!open) return
    const nextClasses = {}
    const nextAssets = {}
    for (const item of allocation?.classes || []) {
      if (item.target_percent !== null) nextClasses[item.asset_class] = String(item.target_percent)
      for (const asset of item.assets) {
        if (asset.target_percent !== null && asset.asset_id) nextAssets[asset.asset_id] = String(asset.target_percent)
      }
    }
    setClasses(nextClasses)
    setAssets(nextAssets)
    setError('')
    // So na abertura: um refetch com o sheet aberto nao apaga o que foi digitado.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const byClass = useMemo(() => {
    const map = {}
    for (const item of allocation?.classes || []) map[item.asset_class] = item
    return map
  }, [allocation])

  const classSum = sumOf(Object.values(classes).filter((value) => value !== ''))
  const anyClass = Object.values(classes).some((value) => value !== '')

  const handleSave = async () => {
    setSaving(true)
    setError('')
    try {
      const payload = { classes: {}, assets: {} }
      for (const [key, value] of Object.entries(classes)) if (value !== '') payload.classes[key] = toNumber(value)
      for (const [key, value] of Object.entries(assets)) if (value !== '') payload.assets[key] = toNumber(value)
      await allocationApi.saveTargets(payload)
      await invalidateServerData()
      toast('Metas de alocação salvas.')
      onClose()
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível salvar as metas.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="Metas de alocação"
      description="Classes em % da carteira; ativos em % da própria classe. Deixe em branco o que não tem meta."
      footer={(
        <div className="flex items-center justify-between gap-3">
          <p className={cx('text-sm font-semibold', anyClass && Math.abs(classSum - 100) > 0.01 ? 'text-amber-700' : 'text-zinc-600')}>
            Classes: {formatPercent(classSum, 2)}
          </p>
          <Button type="button" icon={Target} loading={saving} onClick={handleSave}>Salvar metas</Button>
        </div>
      )}
    >
      <AlertMessage message={error} onDismiss={() => setError('')} className="mb-4" />
      <div className="space-y-5">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {CLASS_ORDER.map((key) => (
            <Field key={key} label={getClassLabel(key)}>
              <input
                type="number"
                inputMode="decimal"
                min="0"
                max="100"
                step="0.01"
                placeholder="—"
                value={classes[key] ?? ''}
                onChange={(event) => setClasses({ ...classes, [key]: event.target.value })}
                className="app-input"
                aria-label={`Meta de ${getClassLabel(key)} (%)`}
              />
            </Field>
          ))}
        </div>
        {CLASS_ORDER.filter((key) => byClass[key]?.assets?.length).map((key) => {
          const classAssets = byClass[key].assets.filter((asset) => asset.asset_id)
          const values = classAssets.map((asset) => assets[asset.asset_id] ?? '')
          const filled = values.some((value) => value !== '')
          const sum = sumOf(values.filter((value) => value !== ''))
          return (
            <div key={key} className="rounded-2xl border border-zinc-200 p-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <p className="font-semibold text-zinc-900">{getClassLabel(key)} — por ativo</p>
                <span className={cx('text-sm font-semibold', filled && Math.abs(sum - 100) > 0.01 ? 'text-amber-700' : 'text-zinc-500')}>
                  {filled ? formatPercent(sum, 2) : 'opcional'}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {classAssets.map((asset) => (
                  <Field key={asset.asset_id} label={asset.ticker}>
                    <input
                      type="number"
                      inputMode="decimal"
                      min="0"
                      max="100"
                      step="0.01"
                      placeholder={filled ? '0' : '—'}
                      value={assets[asset.asset_id] ?? ''}
                      onChange={(event) => setAssets({ ...assets, [asset.asset_id]: event.target.value })}
                      className="app-input"
                      aria-label={`Meta de ${asset.ticker} dentro de ${getClassLabel(key)} (%)`}
                    />
                  </Field>
                ))}
              </div>
              {filled ? (
                <p className="mt-2 text-xs text-zinc-500">Com alguma meta preenchida na classe, as outras contam como 0% e a soma precisa dar 100%.</p>
              ) : null}
            </div>
          )
        })}
      </div>
    </Sheet>
  )
}

// Concentracao (calculada no servidor, `concentration`): ativo acima do limite
// (10% do valor liquido) em aviso. So percentuais: o modo privado nao esconde
// nada aqui.
function ConcentrationAlerts({ concentration }) {
  if (!concentration) return null
  const over = concentration.assets_over_threshold || []
  const threshold = formatPercent(concentration.threshold_percent, 0)
  return (
    <>
      {over.length ? (
        <AlertMessage tone="warning">
          <p>
            {over.length === 1 ? 'Um ativo passa' : `${over.length} ativos passam`} de {threshold} da carteira:
            {' '}
            {over.map((item, index) => (
              <span key={item.asset_id || item.ticker}>
                {index ? ', ' : ''}
                <span className="font-semibold">{item.ticker}</span> <span className="tabular whitespace-nowrap">{formatPercent(item.percent, 1)}</span>
              </span>
            ))}
            .
          </p>
          <p className="mt-0.5 font-normal">Uma queda forte em um deles pesa na carteira inteira.</p>
        </AlertMessage>
      ) : null}
    </>
  )
}

// Alocacao alvo (GET /api/allocation): atual x meta por classe e por ativo, e
// como dividir o proximo aporte sem vender nada.
export default function Alocacao() {
  const privateMoney = usePrivateFormatter(formatCurrency)
  const [contributionInput, setContributionInput] = useState('')
  const [editing, setEditing] = useState(false)
  const [openClasses, setOpenClasses] = useState({})
  const contribution = useDebouncedValue(Number(String(contributionInput).replace(',', '.')) || 0, 350)

  const query = useQuery({
    queryKey: ['investimentos', 'alocacao', contribution],
    queryFn: () => allocationApi.get(contribution > 0 ? { contribution } : {}),
    placeholderData: keepPreviousData,
  })
  const data = query.data
  const hasContribution = contribution > 0 && data?.has_class_targets

  const toggleClass = (key) => setOpenClasses((current) => ({ ...current, [key]: !current[key] }))

  return (
    <div className="space-y-6">
      <PageHeader
        title="Alocação"
        description="Quanto de cada classe e de cada ativo você quer ter, e para onde vai o próximo aporte."
        actions={<Button type="button" icon={Target} onClick={() => setEditing(true)} disabled={!data}>Definir metas</Button>}
      />

      <AlertMessage message={queryErrorMessage(query, 'Não foi possível calcular a alocação.')} />

      {query.isPending ? (
        <Panel><ListSkeleton rows={4} /></Panel>
      ) : data && !data.classes.length ? (
        <Panel className="p-5">
          <EmptyState icon={Scale} title="Carteira vazia" message="Registre uma compra em Operações para ver a alocação." className="min-h-40" />
        </Panel>
      ) : data ? (
        <>
          {!data.has_class_targets ? (
            <AlertMessage tone="info" message="Sem metas por classe ainda. Em “Definir metas”, diga quanto quer em cada classe; a tela passa a mostrar o desvio e a sugerir o aporte." />
          ) : null}

          <ConcentrationAlerts concentration={data.concentration} />

          {data.has_class_targets ? (
            <Panel className="p-5 sm:p-6">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
                <Field label="Quanto vai aportar?" className="sm:w-64" hint="Divide o valor entre o que está abaixo da meta, sem vender nada.">
                  <input
                    type="number"
                    inputMode="decimal"
                    min="0"
                    step="0.01"
                    placeholder="0,00"
                    value={contributionInput}
                    onChange={(event) => setContributionInput(event.target.value)}
                    className="app-input"
                  />
                </Field>
                {hasContribution ? (
                  <div className="flex flex-wrap gap-2 pb-6">
                    {data.classes.filter((item) => item.suggested > 0).map((item) => (
                      <Badge key={item.asset_class} tone="info">{getClassLabel(item.asset_class)}: {formatCurrency(item.suggested)}</Badge>
                    ))}
                  </div>
                ) : null}
              </div>
            </Panel>
          ) : null}

          {data.opportunities.length ? (
            <Panel className="overflow-clip">
              <PanelHeader
                title="Oportunidades de compra"
                description="Abaixo da meta dentro da classe e cotados abaixo do seu preço médio: comprar agora aproxima da meta e baixa o médio."
                actions={<Badge tone="info">{data.opportunities.length} ativo(s)</Badge>}
              />
              <ul className="divide-y divide-zinc-100">
                {data.opportunities.map((item) => (
                  <li key={item.asset_id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 sm:px-6">
                    <div className="flex items-center gap-2">
                      <Sparkles className="h-4 w-4 text-sky-600" aria-hidden="true" />
                      <span className="font-semibold text-zinc-900">{item.ticker}</span>
                      <span className="text-sm text-zinc-500">{getClassLabel(item.asset_class)}</span>
                    </div>
                    <div className="flex flex-wrap items-center gap-4 text-sm">
                      <span className="text-zinc-600">Atual <span className="num font-semibold text-zinc-900">{formatCurrency(item.current_price)}</span></span>
                      <span className="text-zinc-600">Médio <span className="num font-semibold text-zinc-900">{formatCurrency(item.average_price)}</span></span>
                      <span className="text-zinc-600">{formatPercent(item.percent_in_class, 1)} / meta {formatPercent(item.target_percent, 1)}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </Panel>
          ) : null}

          <Panel className="overflow-clip">
            <PanelHeader
              title="Por classe"
              description={`Carteira de ${privateMoney(data.total)} pelo valor líquido. O traço na barra é a meta.`}
            />
            <ul className="divide-y divide-zinc-100">
              {data.classes.map((item) => {
                const open = Boolean(openClasses[item.asset_class])
                return (
                  <li key={item.asset_class}>
                    <button
                      type="button"
                      onClick={() => toggleClass(item.asset_class)}
                      aria-expanded={open}
                      className="w-full px-5 py-4 text-left transition hover:bg-zinc-50 sm:px-6"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="flex min-w-0 items-center gap-2">
                          <ChevronDown className={cx('h-4 w-4 shrink-0 text-zinc-500 transition-transform', open && 'rotate-180')} />
                          <span className="font-semibold text-zinc-900">{getClassLabel(item.asset_class)}</span>
                          <span className="num text-sm text-zinc-500">{privateMoney(item.value)}</span>
                        </div>
                        <div className="flex flex-wrap items-center gap-3 text-sm">
                          <span className="text-zinc-700">
                            <span className="num font-semibold">{formatPercent(item.percent, 1)}</span>
                            {item.target_percent !== null ? <span className="text-zinc-500"> / meta {formatPercent(item.target_percent, 1)}</span> : null}
                          </span>
                          <DriftBadge diff={item.diff_percent} />
                        </div>
                      </div>
                      <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
                        <AllocationBar percent={item.percent} target={item.target_percent} />
                        <span className="text-right text-sm text-zinc-600 sm:w-44 sm:shrink-0">
                          {hasContribution && item.suggested > 0
                            ? <span className="font-semibold text-sky-700">Aportar {formatCurrency(item.suggested)}</span>
                            : gapText(item.gap_value, privateMoney)}
                        </span>
                      </div>
                    </button>
                    <Expand open={open}>
                      <div className="border-t border-zinc-100 bg-zinc-50/60 px-5 py-3 sm:px-6">
                        {!item.has_asset_targets && item.assets.length > 1 ? (
                          <p className="mb-2 text-xs text-zinc-500">Sem meta por ativo nesta classe: o aporte fica no nível da classe.</p>
                        ) : null}
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="text-left text-xs text-zinc-500">
                              <th className="py-1.5 font-medium">Ativo</th>
                              <th className="num py-1.5 pl-3 font-medium">Valor</th>
                              <th className="num py-1.5 pl-3 font-medium">Na classe</th>
                              <th className="num hidden py-1.5 pl-3 font-medium sm:table-cell">Meta</th>
                              <th className="num py-1.5 pl-3 font-medium">{hasContribution ? 'Aportar' : 'Para a meta'}</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-zinc-100">
                            {item.assets.map((asset) => (
                              <tr key={asset.asset_id || asset.ticker}>
                                <td className="py-2 font-medium text-zinc-900">
                                  {asset.ticker}
                                  {asset.below_average_price ? <span className="block text-xs font-normal text-zinc-500 sm:ml-2 sm:inline">abaixo do médio</span> : null}
                                </td>
                                <td className="num py-2 pl-3 text-zinc-700">{privateMoney(asset.value)}</td>
                                <td className="num py-2 pl-3 text-zinc-700">{formatPercent(asset.percent_in_class, 1)}</td>
                                <td className="num hidden py-2 pl-3 text-zinc-500 sm:table-cell">{asset.target_percent !== null ? formatPercent(asset.target_percent, 1) : '—'}</td>
                                <td className="num py-2 pl-3 text-zinc-700">
                                  {hasContribution
                                    ? (asset.suggested > 0 ? <span className="font-semibold text-sky-700">{formatCurrency(asset.suggested)}</span> : '—')
                                    : (gapText(asset.gap_value, privateMoney) || '—')}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </Expand>
                  </li>
                )
              })}
            </ul>
          </Panel>

          <SectorAllocation classes={data.classes} />
        </>
      ) : null}

      <TargetsSheet open={editing} onClose={() => setEditing(false)} allocation={data} />
    </div>
  )
}
