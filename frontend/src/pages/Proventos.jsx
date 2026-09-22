import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { CHART, ChartTooltip, FLOW, axisProps, compactCurrency, useChartAnimation } from '../components/charts'
import { useEffect, useMemo, useRef, useState } from 'react'
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
import { useDataVersion } from '../lib/newEntry'
import {
  AlertMessage,
  Badge,
  Button,
  Collapsible,
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
  { value: 'AMORTIZATION', label: 'Amortização', tone: 'info' },
]

const STATUS_ITEMS = [
  { value: 'ALL', label: 'Todos', icon: Filter },
  { value: 'PAID', label: 'Pagos', icon: Coins },
  { value: 'SCHEDULED', label: 'Agendados', icon: CalendarDays },
]

const ASSET_CLASS_LABELS = {
  STOCKS: 'Ações',
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
  const chartAnimation = useChartAnimation()
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
  const [formOpen, setFormOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const requestRef = useRef(0)

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

  // Os filtros valem ao mudar, como no extrato: cada mudanca refaz a busca.
  // So a resposta da ultima busca e aplicada, para uma lenta nao sobrescrever a nova.
  const fetchData = async () => {
    const requestId = ++requestRef.current
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
      if (requestId !== requestRef.current) return
      setAssets(assetData || [])
      setProceeds(proceedData || [])
      setSummary(summaryData || null)
      setCalendarEvents(calendarData || [])
    } catch (err) {
      if (requestId !== requestRef.current) return
      console.warn('Erro ao carregar proventos:', err)
      setError(err.message || 'Não foi possível carregar os proventos.')
      setProceeds([])
      setCalendarEvents([])
      setSummary(null)
    } finally {
      if (requestId === requestRef.current) setLoading(false)
    }
  }

  const dataVersion = useDataVersion()
  useEffect(() => {
    fetchData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filteredParams, dataVersion])

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
      throw new Error('Informe valores numéricos válidos.')
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
      setFormOpen(false)
      await fetchData()
    } catch (err) {
      setError(err.message || 'Não foi possível salvar o provento.')
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
    setFormOpen(true)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleDelete = async (item) => {
    const confirmed = window.confirm(`Excluir provento de ${item.asset?.ticker || 'ativo'} pago em ${formatDateBR(item.payment_date)}?`)
    if (!confirmed) return

    setError('')
    setNotice('')
    try {
      await investmentProceedsApi.remove(item.id)
      setNotice('Provento excluído.')
      await fetchData()
    } catch (err) {
      setError(err.message || 'Não foi possível excluir o provento.')
    }
  }

  const handleFormOpenChange = (next) => {
    setFormOpen(next)
    if (!next && editingId) resetForm()
  }

  const handleCancelEdit = () => {
    resetForm()
    setFormOpen(false)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Investimentos"
        title="Proventos"
        description="Dividendos, JCP, amortizações, yield on cost e agenda de pagamentos."
        actions={(
          <Button type="button" variant="secondary" icon={RefreshCw} loading={loading} onClick={fetchData}>
            Atualizar
          </Button>
        )}
      />

      <AlertMessage tone="danger" message={error} onDismiss={() => setError('')} />
      <AlertMessage tone="success" message={notice} onDismiss={() => setNotice('')} />

      <Collapsible
        label={editingId ? 'Editar provento' : 'Registrar provento'}
        icon={editingId ? Pencil : Plus}
        open={formOpen}
        onOpenChange={handleFormOpenChange}
        buttonClassName="w-full sm:w-auto"
      >
        <Panel>
          <PanelHeader
            title={editingId ? 'Editar provento' : 'Registrar provento'}
            description="Informe datas, tipo e valores para calcular o yield on cost."
            actions={editingId ? (
              <Button type="button" variant="secondary" icon={X} onClick={handleCancelEdit}>
                Cancelar edição
              </Button>
            ) : null}
          />
          <ProventoForm
            form={form}
            setForm={setForm}
            assets={assets}
            editingId={editingId}
            saving={saving}
            onSubmit={handleSubmit}
          />
        </Panel>
      </Collapsible>

      <div className="stagger grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={Coins}
          tone="success"
          title="Líquido no período"
          value={formatCurrency(summary?.net_amount)}
          subtitle={`${summary?.event_count || 0} evento(s)`}
        />
        <MetricCard
          icon={Landmark}
          tone="info"
          title="Yield on cost"
          value={formatPercent(summary?.yield_on_cost_percent)}
          valueClassName="text-sky-700"
          subtitle="Líquido / custo elegível"
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
        <Panel className={summary?.by_month?.length ? 'xl:col-span-2' : 'xl:col-span-5'}>
          <PanelHeader
            title="Calendário"
            description="Próximos pagamentos por data."
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
                      <p className="mt-1 truncate text-sm text-zinc-600">
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
        {summary?.by_month?.length ? (
          <Panel className="xl:col-span-3">
            <PanelHeader title="Recebimentos por mês" description="Total líquido agrupado por pagamento." />
            <div className="p-5">
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={[...summary.by_month]
                      .sort((a, b) => String(a.month).localeCompare(String(b.month)))
                      .map((item) => ({ ...item, net: Number(item.net_amount || 0) }))}
                    margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
                  >
                    <CartesianGrid vertical={false} stroke={CHART.grid} />
                    <XAxis dataKey="month" {...axisProps} />
                    <YAxis tickFormatter={compactCurrency} {...axisProps} width={76} />
                    <Tooltip
                      cursor={{ fill: 'rgba(24,24,27,0.04)' }}
                      content={(
                        <ChartTooltip
                          names={{ net: 'Líquido' }}
                          footer={(payload) => `${payload?.[0]?.payload?.event_count || 0} evento(s)`}
                        />
                      )}
                    />
                    <Bar dataKey="net" fill={FLOW.income} maxBarSize={24} radius={[4, 4, 0, 0]} {...chartAnimation} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </Panel>
        ) : null}
      </div>

      <Panel>
        <PanelHeader
          title="Filtros"
          description="Período, status, ativo e tipo de provento. Valem ao mudar."
          actions={loading ? <Badge>Atualizando...</Badge> : null}
        />
        <div className="grid grid-cols-1 gap-4 p-5 md:grid-cols-2 xl:grid-cols-6">
          <Field label="Início">
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
        </div>
      </Panel>

      <Panel>
        <PanelHeader
          title="Histórico de proventos"
          description="Eventos registrados com YOC e impostos."
          actions={<Badge>{proceeds.length} registro(s)</Badge>}
        />
        {proceeds.length > 0 ? (
          <>
          <ul className="divide-y divide-zinc-100 md:hidden">
            {proceeds.map((item) => (
              <li key={item.id} className="space-y-2 px-4 py-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-semibold text-zinc-950">{item.asset?.ticker}</p>
                    <p className="text-xs text-zinc-600">
                      {formatDateBR(item.payment_date)} · {ASSET_CLASS_LABELS[item.asset?.asset_class] || item.asset?.asset_class}
                    </p>
                  </div>
                  <p className="shrink-0 font-bold tabular text-emerald-700">{formatCurrency(item.net_amount)}</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={item.status === 'PAID' ? 'success' : 'warning'}>
                    {item.status === 'PAID' ? 'Pago' : 'Agendado'}
                  </Badge>
                  <Badge tone={typeTone(item.proceeds_type)}>{typeLabel(item.proceeds_type)}</Badge>
                </div>
                <p className="text-xs text-zinc-600 tabular">
                  {formatUnitCurrency(item.amount_per_unit)}/cota · {Number(item.eligible_quantity || 0).toLocaleString('pt-BR', { maximumFractionDigits: 6 })} cotas ·
                  {' '}Bruto {formatCurrency(item.gross_amount)} · Imposto {formatCurrency(item.tax_amount)} · YOC {formatPercent(item.yield_on_cost_percent, 4)}
                </p>
                <div className="flex justify-end gap-2">
                  <IconButton label="Editar provento" icon={Pencil} onClick={() => handleEdit(item)} />
                  <IconButton label="Excluir provento" icon={Trash2} variant="danger" onClick={() => handleDelete(item)} />
                </div>
              </li>
            ))}
          </ul>
          <div className="hidden overflow-x-auto md:block">
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
                  <th>Líquido</th>
                  <th>YOC</th>
                  <th className="text-right">Ações</th>
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
          </>
        ) : (
          <div className="p-5">
            <EmptyState icon={Coins} title="Nenhum provento" message="Registre dividendos, JCP ou amortizações para acompanhar o calendário." />
          </div>
        )}
      </Panel>
    </div>
  )
}

function ProventoForm({ form, setForm, assets, editingId, saving, onSubmit }) {
  return (
    <form onSubmit={onSubmit} className="grid grid-cols-1 gap-4 p-5 md:grid-cols-2 xl:grid-cols-6">
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
      <Field label="Declaração">
        <input type="date" value={form.declared_date} onChange={(event) => setForm({ ...form, declared_date: event.target.value })} className="app-input" />
      </Field>
      <Field label="Valor por cota">
        <input type="text" inputMode="decimal" placeholder="0,00" value={form.amount_per_unit} onChange={(event) => setForm({ ...form, amount_per_unit: event.target.value })} className="app-input" />
      </Field>
      <Field label="Qtd. elegível">
        <input type="text" inputMode="decimal" placeholder="auto" value={form.eligible_quantity} onChange={(event) => setForm({ ...form, eligible_quantity: event.target.value })} className="app-input" />
      </Field>
      <Field label="Valor bruto">
        <input type="text" inputMode="decimal" placeholder="auto" value={form.gross_amount} onChange={(event) => setForm({ ...form, gross_amount: event.target.value })} className="app-input" />
      </Field>
      <Field label="Imposto">
        <input type="text" inputMode="decimal" placeholder="auto" value={form.tax_amount} onChange={(event) => setForm({ ...form, tax_amount: event.target.value })} className="app-input" />
      </Field>
      <Field label="Observações" className="md:col-span-2 xl:col-span-2">
        <input type="text" value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} className="app-input" />
      </Field>
      <div className="flex items-end md:col-span-2 xl:col-span-6">
        <Button type="submit" icon={editingId ? Pencil : Plus} loading={saving} className="w-full sm:w-auto">
          Salvar
        </Button>
      </div>
    </form>
  )
}
