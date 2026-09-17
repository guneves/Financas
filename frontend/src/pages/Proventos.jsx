import { useEffect, useMemo, useState } from 'react'
import {
  CalendarDays,
  Coins,
  Filter,
  Landmark,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
  X,
} from 'lucide-react'
import { investmentProceedsApi, investmentsApi } from '../lib/dataApi'
import {
  Badge,
  Button,
  EmptyState,
  Field,
  IconButton,
  MetricCard,
  PageHeader,
  Panel,
  PanelHeader,
  SegmentedControl,
  cx,
} from '../components/ui'
import { formatCurrency, formatDateBR, formatUnitCurrency, getLocalDateString } from '../lib/format'

const PROCEEDS_TYPES = [
  { value: 'DIVIDEND', label: 'Dividendos', tone: 'success' },
  { value: 'JCP', label: 'JCP', tone: 'warning' },
  { value: 'AMORTIZATION', label: 'Amortizacao', tone: 'info' },
]

const STATUS_ITEMS = [
  { value: 'ALL', label: 'Todos', icon: Filter },
  { value: 'PAID', label: 'Pagos', icon: Coins },
  { value: 'SCHEDULED', label: 'Agendados', icon: CalendarDays },
]

const ASSET_CLASS_LABELS = {
  STOCKS: 'Acoes',
  FIXED_INCOME: 'Renda fixa',
  REIT: 'FIIs',
  CATTLE: 'Gado',
  OTHER: 'Outros',
}

const currentYear = new Date().getFullYear()

const formatPercent = (value, digits = 2) => `${Number(value || 0).toFixed(digits)}%`

const parseNumberInput = (value) => {
  if (value === '' || value === null || value === undefined) return null
  const normalized = String(value).trim().includes(',')
    ? String(value).trim().replace(/\./g, '').replace(',', '.')
    : String(value).trim()
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : NaN
}

const blankForm = () => ({
  asset_id: '',
  proceeds_type: 'DIVIDEND',
  declared_date: '',
  record_date: getLocalDateString(),
  ex_date: '',
  payment_date: getLocalDateString(),
  amount_per_unit: '',
  eligible_quantity: '',
  gross_amount: '',
  tax_amount: '',
  notes: '',
})

const typeLabel = (value) => PROCEEDS_TYPES.find((item) => item.value === value)?.label || value
const typeTone = (value) => PROCEEDS_TYPES.find((item) => item.value === value)?.tone || 'neutral'

export default function Proventos() {
  const [assets, setAssets] = useState([])
  const [proceeds, setProceeds] = useState([])
  const [calendarEvents, setCalendarEvents] = useState([])
  const [summary, setSummary] = useState(null)
  const [filters, setFilters] = useState({
    date_from: `${currentYear}-01-01`,
    date_to: `${currentYear}-12-31`,
    proceeds_type: '',
    asset_id: '',
    status: 'ALL',
  })
  const [form, setForm] = useState(blankForm)
  const [editingId, setEditingId] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    fetchData()
  }, [])

  useEffect(() => {
    if (!form.asset_id && assets[0]?.id && !editingId) {
      setForm((current) => ({ ...current, asset_id: assets[0].id }))
    }
  }, [assets, form.asset_id, editingId])

  const filteredParams = useMemo(() => ({
    date_from: filters.date_from,
    date_to: filters.date_to,
    proceeds_type: filters.proceeds_type,
    asset_id: filters.asset_id,
    status: filters.status,
  }), [filters])

  const fetchData = async () => {
    setLoading(true)
    setError('')
    try {
      const [assetData, proceedData, summaryData, calendarData] = await Promise.all([
        investmentsApi.assets(),
        investmentProceedsApi.list(filteredParams),
        investmentProceedsApi.summary(filteredParams),
        investmentProceedsApi.calendar({
          asset_id: filters.asset_id,
          proceeds_type: filters.proceeds_type,
          status: 'SCHEDULED',
        }),
      ])
      setAssets(assetData || [])
      setProceeds(proceedData || [])
      setSummary(summaryData || null)
      setCalendarEvents(calendarData || [])
    } catch (err) {
      console.warn('Erro ao carregar proventos:', err)
      setError(err.message || 'Nao foi possivel carregar os proventos.')
      setProceeds([])
      setCalendarEvents([])
      setSummary(null)
    } finally {
      setLoading(false)
    }
  }

  const handleFilterSubmit = async (event) => {
    event.preventDefault()
    await fetchData()
  }

  const resetForm = () => {
    setEditingId('')
    setForm({
      ...blankForm(),
      asset_id: assets[0]?.id || '',
    })
  }

  const buildPayload = () => {
    const amountPerUnit = parseNumberInput(form.amount_per_unit)
    const eligibleQuantity = parseNumberInput(form.eligible_quantity)
    const grossAmount = parseNumberInput(form.gross_amount)
    const taxAmount = parseNumberInput(form.tax_amount)

    if (!form.asset_id) throw new Error('Selecione um ativo.')
    if (!form.record_date) throw new Error('Informe a data com.')
    if (!form.payment_date) throw new Error('Informe a data de pagamento.')
    if (Number.isNaN(amountPerUnit) || Number.isNaN(eligibleQuantity) || Number.isNaN(grossAmount) || Number.isNaN(taxAmount)) {
      throw new Error('Informe valores numericos validos.')
    }

    return {
      asset_id: form.asset_id,
      proceeds_type: form.proceeds_type,
      declared_date: form.declared_date || null,
      record_date: form.record_date,
      ex_date: form.ex_date || null,
      payment_date: form.payment_date,
      amount_per_unit: amountPerUnit,
      eligible_quantity: eligibleQuantity,
      gross_amount: grossAmount,
      tax_amount: taxAmount,
      notes: form.notes,
    }
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const payload = buildPayload()
      if (editingId) {
        await investmentProceedsApi.update(editingId, payload)
        setNotice('Provento atualizado.')
      } else {
        await investmentProceedsApi.create(payload)
        setNotice('Provento registrado.')
      }
      resetForm()
      await fetchData()
    } catch (err) {
      setError(err.message || 'Nao foi possivel salvar o provento.')
    } finally {
      setSaving(false)
    }
  }

  const handleEdit = (item) => {
    setEditingId(item.id)
    setForm({
      asset_id: item.asset_id || '',
      proceeds_type: item.proceeds_type || 'DIVIDEND',
      declared_date: item.declared_date || '',
      record_date: item.record_date || getLocalDateString(),
      ex_date: item.ex_date || '',
      payment_date: item.payment_date || getLocalDateString(),
      amount_per_unit: item.amount_per_unit ?? '',
      eligible_quantity: item.eligible_quantity ?? '',
      gross_amount: item.gross_amount ?? '',
      tax_amount: item.tax_amount ?? '',
      notes: item.notes || '',
    })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleDelete = async (item) => {
    const confirmed = window.confirm(`Excluir provento de ${item.asset?.ticker || 'ativo'} pago em ${formatDateBR(item.payment_date)}?`)
    if (!confirmed) return

    setError('')
    setNotice('')
    try {
      await investmentProceedsApi.remove(item.id)
      setNotice('Provento excluido.')
      await fetchData()
    } catch (err) {
      setError(err.message || 'Nao foi possivel excluir o provento.')
    }
  }

  const monthMax = useMemo(() => {
    return Math.max(...(summary?.by_month || []).map((item) => Number(item.net_amount || 0)), 0)
  }, [summary])

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Investimentos"
        title="Proventos"
        description="Dividendos, JCP, amortizacoes, yield on cost e agenda de pagamentos."
        actions={(
          <Button type="button" variant="secondary" icon={RefreshCw} loading={loading} onClick={fetchData}>
            Atualizar
          </Button>
        )}
      />

      {error ? <AlertMessage tone="danger" message={error} /> : null}
      {notice ? <AlertMessage tone="success" message={notice} /> : null}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={Coins}
          tone="success"
          title="Liquido no periodo"
          value={formatCurrency(summary?.net_amount)}
          subtitle={`${summary?.event_count || 0} evento(s)`}
        />
        <MetricCard
          icon={Landmark}
          tone="info"
          title="Yield on cost"
          value={formatPercent(summary?.yield_on_cost_percent)}
          valueClassName="text-sky-700"
          subtitle="Liquido / custo elegivel"
        />
        <MetricCard
          icon={CalendarDays}
          tone="warning"
          title="Agendado"
          value={formatCurrency(summary?.scheduled_net_amount)}
          subtitle="Pagamentos futuros"
        />
        <MetricCard
          icon={Coins}
          tone="neutral"
          title="Imposto retido"
          value={formatCurrency(summary?.tax_amount)}
          subtitle={`Bruto: ${formatCurrency(summary?.gross_amount)}`}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
        <Panel className="xl:col-span-3">
          <PanelHeader
            title={editingId ? 'Editar provento' : 'Registrar provento'}
            description="Informe datas, tipo e valores para calcular o yield on cost."
            actions={editingId ? (
              <Button type="button" variant="secondary" icon={X} onClick={resetForm}>
                Cancelar
              </Button>
            ) : null}
          />
          <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-4 p-5 md:grid-cols-2 xl:grid-cols-6">
            <Field label="Ativo" className="xl:col-span-2">
              <select value={form.asset_id} onChange={(event) => setForm({ ...form, asset_id: event.target.value })} className="app-select" required>
                <option value="">Selecione...</option>
                {assets.map((asset) => (
                  <option key={asset.id} value={asset.id}>
                    {asset.ticker} - {ASSET_CLASS_LABELS[asset.asset_class] || asset.asset_class}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Tipo">
              <select value={form.proceeds_type} onChange={(event) => setForm({ ...form, proceeds_type: event.target.value })} className="app-select" required>
                {PROCEEDS_TYPES.map((item) => (
                  <option key={item.value} value={item.value}>{item.label}</option>
                ))}
              </select>
            </Field>
            <Field label="Data com">
              <input type="date" value={form.record_date} onChange={(event) => setForm({ ...form, record_date: event.target.value })} className="app-input" required />
            </Field>
            <Field label="Data ex">
              <input type="date" value={form.ex_date} onChange={(event) => setForm({ ...form, ex_date: event.target.value })} className="app-input" />
            </Field>
            <Field label="Pagamento">
              <input type="date" value={form.payment_date} onChange={(event) => setForm({ ...form, payment_date: event.target.value })} className="app-input" required />
            </Field>
            <Field label="Declaracao">
              <input type="date" value={form.declared_date} onChange={(event) => setForm({ ...form, declared_date: event.target.value })} className="app-input" />
            </Field>
            <Field label="Valor por cota">
              <input type="text" inputMode="decimal" placeholder="0,00" value={form.amount_per_unit} onChange={(event) => setForm({ ...form, amount_per_unit: event.target.value })} className="app-input" />
            </Field>
            <Field label="Qtd. elegivel">
              <input type="text" inputMode="decimal" placeholder="auto" value={form.eligible_quantity} onChange={(event) => setForm({ ...form, eligible_quantity: event.target.value })} className="app-input" />
            </Field>
            <Field label="Valor bruto">
              <input type="text" inputMode="decimal" placeholder="auto" value={form.gross_amount} onChange={(event) => setForm({ ...form, gross_amount: event.target.value })} className="app-input" />
            </Field>
            <Field label="Imposto">
              <input type="text" inputMode="decimal" placeholder="auto" value={form.tax_amount} onChange={(event) => setForm({ ...form, tax_amount: event.target.value })} className="app-input" />
            </Field>
            <Field label="Observacoes" className="md:col-span-2 xl:col-span-2">
              <input type="text" value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} className="app-input" />
            </Field>
            <div className="flex items-end md:col-span-2 xl:col-span-6">
              <Button type="submit" icon={editingId ? Pencil : Plus} loading={saving} className="w-full sm:w-auto">
                {editingId ? 'Salvar alteracoes' : 'Registrar provento'}
              </Button>
            </div>
          </form>
        </Panel>

        <Panel className="xl:col-span-2">
          <PanelHeader
            title="Calendario"
            description="Proximos pagamentos por data."
            actions={<Badge tone="warning">{calendarEvents.length} evento(s)</Badge>}
          />
          <div className="p-5">
            {calendarEvents.length > 0 ? (
              <div className="space-y-3">
                {calendarEvents.slice(0, 8).map((item) => (
                  <div key={item.id} className="flex items-center justify-between gap-4 rounded-lg border border-zinc-200 px-4 py-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-semibold text-zinc-950">{formatDateBR(item.payment_date)}</p>
                        <Badge tone={typeTone(item.proceeds_type)}>{typeLabel(item.proceeds_type)}</Badge>
                      </div>
                      <p className="mt-1 truncate text-sm text-zinc-500">
                        {item.asset?.ticker} - {formatCurrency(item.net_amount)}
                      </p>
                    </div>
                    <CalendarDays className="h-5 w-5 shrink-0 text-amber-600" />
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState icon={CalendarDays} title="Sem agenda" message="Pagamentos futuros aparecem aqui." className="min-h-60" />
            )}
          </div>
        </Panel>
      </div>

      <Panel>
        <PanelHeader title="Filtros" description="Periodo, status, ativo e tipo de provento." />
        <form onSubmit={handleFilterSubmit} className="grid grid-cols-1 gap-4 p-5 md:grid-cols-2 xl:grid-cols-6">
          <Field label="Inicio">
            <input type="date" value={filters.date_from} onChange={(event) => setFilters({ ...filters, date_from: event.target.value })} className="app-input" />
          </Field>
          <Field label="Fim">
            <input type="date" value={filters.date_to} onChange={(event) => setFilters({ ...filters, date_to: event.target.value })} className="app-input" />
          </Field>
          <Field label="Ativo">
            <select value={filters.asset_id} onChange={(event) => setFilters({ ...filters, asset_id: event.target.value })} className="app-select">
              <option value="">Todos</option>
              {assets.map((asset) => (
                <option key={asset.id} value={asset.id}>{asset.ticker}</option>
              ))}
            </select>
          </Field>
          <Field label="Tipo">
            <select value={filters.proceeds_type} onChange={(event) => setFilters({ ...filters, proceeds_type: event.target.value })} className="app-select">
              <option value="">Todos</option>
              {PROCEEDS_TYPES.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
          </Field>
          <div className="md:col-span-2 xl:col-span-2">
            <p className="mb-1.5 text-sm font-medium text-zinc-700">Status</p>
            <SegmentedControl
              value={filters.status}
              onChange={(value) => setFilters({ ...filters, status: value })}
              items={STATUS_ITEMS}
              className="w-full"
            />
          </div>
          <div className="flex items-end md:col-span-2 xl:col-span-6">
            <Button type="submit" icon={Filter} loading={loading}>
              Aplicar filtros
            </Button>
          </div>
        </form>
      </Panel>

      {summary?.by_month?.length ? (
        <Panel>
          <PanelHeader title="Recebimentos por mes" description="Total liquido agrupado por pagamento." />
          <div className="grid grid-cols-1 gap-3 p-5 md:grid-cols-2 xl:grid-cols-4">
            {summary.by_month.map((item) => {
              const width = monthMax > 0 ? `${Math.max((Number(item.net_amount || 0) / monthMax) * 100, 3)}%` : '0%'
              return (
                <div key={item.month} className="rounded-lg border border-zinc-200 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="font-semibold text-zinc-950">{item.month}</p>
                    <Badge>{item.event_count}</Badge>
                  </div>
                  <p className="mt-2 text-lg font-bold text-emerald-700">{formatCurrency(item.net_amount)}</p>
                  <div className="mt-3 h-2 overflow-hidden rounded-full bg-zinc-100">
                    <div className="h-full rounded-full bg-emerald-500" style={{ width }} />
                  </div>
                </div>
              )
            })}
          </div>
        </Panel>
      ) : null}

      <Panel>
        <PanelHeader
          title="Historico de proventos"
          description="Eventos registrados com YOC e impostos."
          actions={<Badge>{proceeds.length} registro(s)</Badge>}
        />
        {proceeds.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="app-table min-w-[1120px]">
              <thead>
                <tr>
                  <th>Pagamento</th>
                  <th>Ativo</th>
                  <th>Tipo</th>
                  <th>Data com</th>
                  <th>Valor/cota</th>
                  <th>Qtd.</th>
                  <th>Bruto</th>
                  <th>Imposto</th>
                  <th>Liquido</th>
                  <th>YOC</th>
                  <th className="text-right">Acao</th>
                </tr>
              </thead>
              <tbody>
                {proceeds.map((item) => (
                  <tr key={item.id}>
                    <td className="font-medium text-zinc-800">
                      {formatDateBR(item.payment_date)}
                      <div className="mt-1">
                        <Badge tone={item.status === 'PAID' ? 'success' : 'warning'}>
                          {item.status === 'PAID' ? 'Pago' : 'Agendado'}
                        </Badge>
                      </div>
                    </td>
                    <td>
                      <p className="font-semibold text-zinc-950">{item.asset?.ticker}</p>
                      <p className="text-xs text-zinc-500">{ASSET_CLASS_LABELS[item.asset?.asset_class] || item.asset?.asset_class}</p>
                    </td>
                    <td><Badge tone={typeTone(item.proceeds_type)}>{typeLabel(item.proceeds_type)}</Badge></td>
                    <td className="text-zinc-600">{formatDateBR(item.record_date)}</td>
                    <td>{formatUnitCurrency(item.amount_per_unit)}</td>
                    <td>{Number(item.eligible_quantity || 0).toLocaleString('pt-BR', { maximumFractionDigits: 6 })}</td>
                    <td>{formatCurrency(item.gross_amount)}</td>
                    <td>
                      <p>{formatCurrency(item.tax_amount)}</p>
                      <p className="text-xs text-zinc-500">{formatPercent(item.effective_tax_rate_percent)}</p>
                    </td>
                    <td className="font-bold text-emerald-700">{formatCurrency(item.net_amount)}</td>
                    <td>
                      <p className={cx('font-bold', item.yield_on_cost_percent > 0 ? 'text-sky-700' : 'text-zinc-500')}>
                        {formatPercent(item.yield_on_cost_percent, 4)}
                      </p>
                      <p className="text-xs text-zinc-500">Custo: {formatCurrency(item.cost_basis_at_record_date)}</p>
                    </td>
                    <td className="text-right">
                      <div className="flex justify-end gap-2">
                        <IconButton label="Editar provento" icon={Pencil} onClick={() => handleEdit(item)} />
                        <IconButton label="Excluir provento" icon={Trash2} variant="danger" onClick={() => handleDelete(item)} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-5">
            <EmptyState icon={Coins} title="Nenhum provento" message="Registre dividendos, JCP ou amortizacoes para acompanhar o calendario." />
          </div>
        )}
      </Panel>
    </div>
  )
}

function AlertMessage({ tone = 'danger', message }) {
  const classes = tone === 'success'
    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
    : 'border-rose-200 bg-rose-50 text-rose-700'

  return (
    <div className={cx('rounded-lg border px-4 py-3 text-sm font-medium', classes)}>
      {message}
    </div>
  )
}
