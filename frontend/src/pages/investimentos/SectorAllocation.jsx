import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, Layers, Pencil, RefreshCw, RotateCcw } from 'lucide-react'
import { allocationApi } from '../../lib/dataApi'
import { formatCurrency, formatPercent } from '../../lib/format'
import { usePrivateFormatter } from '../../lib/privacy'
import { invalidateServerData, keepPreviousData, queryErrorMessage, useQuery } from '../../lib/queries'
import { toast } from '../../lib/toast'
import { DonutChart, LegendDot, OTHER_COLOR, SERIES } from '../../components/charts'
import {
  AlertMessage,
  Button,
  EmptyState,
  Expand,
  Field,
  IconButton,
  ListSkeleton,
  Panel,
  PanelHeader,
  SegmentedControl,
  Sheet,
  cx,
} from '../../components/ui'
import { getClassLabel } from './helpers'

const CLASS_ORDER = ['STOCKS', 'REIT', 'FIXED_INCOME', 'CATTLE', 'OTHER']
const MAX_SLICES = SERIES.length + 1

// A cor segue o setor na ordem do servidor (maior primeiro); "Sem setor" e o
// que passa da paleta ficam neutros — mesma regra do DonutChart.
function withColors(sectors) {
  let index = 0
  return sectors.map((item) => {
    if (item.sector === null) return { ...item, color: OTHER_COLOR }
    const color = SERIES[index] || OTHER_COLOR
    index += 1
    return { ...item, color }
  })
}

function SectorSheet({ asset, suggestions, onClose }) {
  const [sector, setSector] = useState('')
  const [segment, setSegment] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!asset) return
    setSector(asset.sector || '')
    setSegment(asset.segment || '')
    setError('')
  }, [asset])

  const save = async (payload, message) => {
    setSaving(true)
    setError('')
    try {
      await allocationApi.setSector(asset.asset_id, payload)
      await invalidateServerData()
      toast(message)
      onClose()
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível salvar o setor.')
    } finally {
      setSaving(false)
    }
  }

  const handleSubmit = (event) => {
    event.preventDefault()
    if (!sector.trim()) {
      setError('Informe o setor.')
      return
    }
    save({ sector, segment }, `Setor de ${asset.ticker} salvo.`)
  }

  return (
    <Sheet
      open={Boolean(asset)}
      onClose={onClose}
      title={asset ? `Setor de ${asset.ticker}` : 'Setor'}
      description="O setor escrito aqui vale sobre o da brapi e não é trocado por ela."
      footer={(
        <div className="flex flex-wrap items-center justify-between gap-3">
          {asset?.source === 'MANUAL' ? (
            <Button
              type="button"
              variant="secondary"
              icon={RotateCcw}
              disabled={saving}
              onClick={() => save({ sector: '' }, `${asset.ticker} volta ao setor automático.`)}
            >
              Voltar ao automático
            </Button>
          ) : <span />}
          <Button type="submit" form="sector-form" icon={Pencil} loading={saving}>Salvar setor</Button>
        </div>
      )}
    >
      <form id="sector-form" onSubmit={handleSubmit} className="space-y-4">
        <AlertMessage message={error} onDismiss={() => setError('')} />
        <Field label="Setor">
          <input
            type="text"
            list="sector-suggestions"
            maxLength={60}
            required
            placeholder="Ex.: Financeiro, Logística, Títulos públicos"
            value={sector}
            onChange={(event) => setSector(event.target.value)}
            className="app-input"
          />
          <datalist id="sector-suggestions">
            {suggestions.map((item) => <option key={item} value={item} />)}
          </datalist>
        </Field>
        <Field label="Segmento (opcional)" hint="Só aparece na lista; a alocação agrupa pelo setor.">
          <input
            type="text"
            maxLength={60}
            placeholder="Ex.: Bancos, Shoppings"
            value={segment}
            onChange={(event) => setSegment(event.target.value)}
            className="app-input"
          />
        </Field>
      </form>
    </Sheet>
  )
}

function fetchNotice(fetch, unassigned) {
  if (!fetch || !(unassigned > 0)) return null
  if (fetch.status === 'unconfigured') {
    return { tone: 'info', message: 'Sem token da brapi (BRAPI_TOKEN): preencha o setor dos ativos à mão, no lápis de cada um.' }
  }
  if (fetch.status === 'error') {
    return { tone: 'warning', message: fetch.message || 'Não foi possível consultar os setores na brapi agora.' }
  }
  return null
}

// Alocacao por setor (GET /api/allocation/sectors): valor liquido da carteira
// agrupado pelo setor de cada ativo — brapi para acao/FII, ou o que o dono
// escreveu. FII entra pelo segmento (Logistica, Shoppings...).
export default function SectorAllocation({ classes = [] }) {
  const privateMoney = usePrivateFormatter(formatCurrency)
  const [assetClass, setAssetClass] = useState('')
  const [openSectors, setOpenSectors] = useState({})
  const [editing, setEditing] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshError, setRefreshError] = useState('')

  const query = useQuery({
    queryKey: ['investimentos', 'alocacao', 'setores', assetClass],
    queryFn: () => allocationApi.sectors(assetClass ? { asset_class: assetClass } : {}),
    placeholderData: keepPreviousData,
  })
  const data = query.data
  const sectors = useMemo(() => withColors(data?.sectors || []), [data])
  const chartData = sectors.map((item) => ({ name: item.label, value: item.value, color: item.color }))

  const classItems = useMemo(() => {
    // So classes com posicao: uma classe que so tem meta daria um filtro vazio.
    const present = new Set(classes.filter((item) => item.value > 0).map((item) => item.asset_class))
    return [
      { value: '', label: 'Todas' },
      ...CLASS_ORDER.filter((key) => present.has(key)).map((key) => ({ value: key, label: getClassLabel(key) })),
    ]
  }, [classes])

  const handleRefresh = async () => {
    setRefreshing(true)
    setRefreshError('')
    try {
      const body = await allocationApi.refreshSectors()
      await invalidateServerData()
      const fetch = body?.fetch || {}
      if (fetch.status === 'ok') {
        toast(fetch.updated ? `Setor de ${fetch.updated} ativo(s) atualizado pela brapi.` : 'Nenhum setor novo na brapi.')
      } else if (fetch.status === 'skipped') {
        toast('Nenhum ativo de bolsa para consultar: os demais têm setor manual.')
      } else {
        setRefreshError(fetch.message || 'Não foi possível consultar os setores na brapi agora.')
      }
    } catch (requestError) {
      setRefreshError(requestError.message || 'Não foi possível consultar os setores na brapi agora.')
    } finally {
      setRefreshing(false)
    }
  }

  const toggle = (key) => setOpenSectors((current) => ({ ...current, [key]: !current[key] }))
  const notice = fetchNotice(data?.fetch, data?.unassigned_value)

  return (
    <Panel className="overflow-clip">
      <PanelHeader
        title="Por setor"
        description="Valor líquido agrupado pelo setor de cada ativo. Ações e FIIs vêm da brapi; o resto, e o que estiver errado, você define no lápis."
        actions={(
          <Button type="button" variant="secondary" icon={RefreshCw} loading={refreshing} onClick={handleRefresh}>
            Buscar setores
          </Button>
        )}
      />
      <div className="space-y-4 px-5 py-4 sm:px-6">
        {classItems.length > 2 ? (
          <SegmentedControl items={classItems} value={assetClass} onChange={setAssetClass} />
        ) : null}
        <AlertMessage message={queryErrorMessage(query, 'Não foi possível calcular a alocação por setor.')} />
        <AlertMessage message={refreshError} onDismiss={() => setRefreshError('')} />
        {notice ? <AlertMessage tone={notice.tone} message={notice.message} /> : null}

        {query.isPending ? (
          <ListSkeleton rows={4} />
        ) : data && !sectors.length ? (
          <EmptyState icon={Layers} title="Nada nesta classe" message="Sem posição aberta para agrupar por setor." className="min-h-40" />
        ) : data ? (
          <DonutChart data={chartData} centerLabel="Carteira" formatter={privateMoney} maxSlices={MAX_SLICES} legend={false} height={200} />
        ) : null}
      </div>

      {sectors.length ? (
        <ul className="divide-y divide-zinc-100 border-t border-zinc-100">
          {sectors.map((item) => {
            const key = item.sector ?? '__none__'
            const open = Boolean(openSectors[key])
            return (
              <li key={key}>
                <button
                  type="button"
                  onClick={() => toggle(key)}
                  aria-expanded={open}
                  className="w-full px-5 py-3.5 text-left transition hover:bg-zinc-50 sm:px-6"
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-2">
                      <ChevronDown className={cx('h-4 w-4 shrink-0 text-zinc-500 transition-transform', open && 'rotate-180')} />
                      <LegendDot color={item.color} label="" className="gap-0" />
                      <span className={cx('font-semibold', item.sector === null ? 'text-zinc-500' : 'text-zinc-900')}>{item.label}</span>
                      <span className="text-xs text-zinc-500">{item.assets.length} ativo(s)</span>
                    </div>
                    <div className="flex items-center gap-3 text-sm">
                      <span className="num text-zinc-500">{privateMoney(item.value)}</span>
                      <span className="num w-14 font-semibold text-zinc-900">{formatPercent(item.percent, 1)}</span>
                    </div>
                  </div>
                </button>
                <Expand open={open}>
                  <div className="border-t border-zinc-100 bg-zinc-50/60 px-5 py-3 sm:px-6">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-xs text-zinc-500">
                          <th className="py-1.5 font-medium">Ativo</th>
                          <th className="num py-1.5 pl-3 font-medium">Valor</th>
                          <th className="num py-1.5 pl-3 font-medium">No setor</th>
                          <th className="num hidden py-1.5 pl-3 font-medium sm:table-cell">Na carteira</th>
                          <th className="py-1.5 pl-3"><span className="sr-only">Ações</span></th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-100">
                        {item.assets.map((asset) => (
                          <tr key={asset.asset_id || asset.ticker}>
                            <td className="py-2">
                              <span className="font-medium text-zinc-900">{asset.ticker}</span>
                              <span className="block text-xs text-zinc-500">
                                {[asset.class_label, asset.segment, asset.source === 'MANUAL' ? 'manual' : null].filter(Boolean).join(' · ')}
                              </span>
                            </td>
                            <td className="num py-2 pl-3 text-zinc-700">{privateMoney(asset.value)}</td>
                            <td className="num py-2 pl-3 text-zinc-700">{formatPercent(asset.percent_in_sector, 1)}</td>
                            <td className="num hidden py-2 pl-3 text-zinc-500 sm:table-cell">{formatPercent(asset.percent_of_total, 1)}</td>
                            <td className="py-2 pl-3 text-right">
                              {asset.asset_id ? (
                                <IconButton
                                  size="sm"
                                  variant="subtle"
                                  icon={Pencil}
                                  label={`Editar setor de ${asset.ticker}`}
                                  onClick={() => setEditing({ ...asset, sector: item.sector })}
                                />
                              ) : null}
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
      ) : null}

      <SectorSheet asset={editing} suggestions={data?.suggestions || []} onClose={() => setEditing(null)} />
    </Panel>
  )
}
