import { useMemo, useState } from 'react'
import { Plus, Shuffle, Trash2 } from 'lucide-react'
import { corporateActionsApi } from '../../lib/dataApi'
import { confirmAction } from '../../lib/confirm'
import { formatCurrency, formatDateBR, getLocalDateString } from '../../lib/format'
import { useQuery, useReportQueryError } from '../../lib/queries'
import { toast } from '../../lib/toast'
import { AlertMessage, Button, EmptyState, Field, IconButton, Panel, PanelHeader, SegmentedControl, Sheet } from '../../components/ui'

const TYPE_ITEMS = [
  { value: 'SPLIT', label: 'Desdobramento' },
  { value: 'REVERSE_SPLIT', label: 'Grupamento' },
  { value: 'BONUS', label: 'Bonificação' },
]

const TYPE_HINTS = {
  SPLIT: 'Cada cota vira mais de uma. Ex.: 1 para 2 dobra a quantidade e divide o preço médio por 2.',
  REVERSE_SPLIT: 'Várias cotas viram uma. Ex.: 10 para 1. Sobra de fração vendida pela corretora entra como venda.',
  BONUS: 'Cotas novas sem pagamento. Ex.: 10 para 1 = 1 cota nova para cada 10. O custo atribuído vem no aviso da empresa.',
}

const DEFAULT_RATIOS = { SPLIT: ['1', '2'], REVERSE_SPLIT: ['10', '1'], BONUS: ['10', '1'] }

const NO_ITEMS = []

const emptyForm = () => ({
  asset_id: '',
  action_type: 'SPLIT',
  ex_date: getLocalDateString(),
  ratio_from: '1',
  ratio_to: '2',
  bonus_unit_cost: '',
  notes: '',
})

function ratioLabel(action) {
  const format = (value) => Number(value).toLocaleString('pt-BR', { maximumFractionDigits: 6 })
  return `${format(action.ratio_from)} para ${format(action.ratio_to)}`
}

// "1.234,5" ou "1234.5" -> numero; vazio -> undefined.
function parseDecimal(value) {
  const text = String(value ?? '').trim()
  if (!text) return undefined
  return Number(text.includes(',') ? text.replace(/[.]/g, '').replace(',', '.') : text)
}

// Desdobramento, grupamento e bonificacao (017). Registrar reescala as
// operacoes anteriores a data ex no servidor; excluir desfaz (so o ultimo do
// ativo, sem operacao depois).
export default function CorporateActionsPanel({ assets }) {
  const [error, setError] = useState('')
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState(emptyForm)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')

  const actionsQuery = useQuery({ queryKey: ['investimentos', 'eventos'], queryFn: () => corporateActionsApi.list() })
  useReportQueryError(actionsQuery, setError, 'Não foi possível carregar os eventos corporativos.')
  const actions = actionsQuery.data || NO_ITEMS

  // Um ativo por id (a carteira lista um por ativo), so acoes e FIIs.
  const eligibleAssets = useMemo(() => {
    const seen = new Map()
    for (const asset of assets || []) {
      const id = asset.asset_id || asset.id
      if (['STOCKS', 'REIT'].includes(asset.class) && !seen.has(id)) {
        seen.set(id, { id, ticker: asset.ticker || asset.name })
      }
    }
    return [...seen.values()].sort((a, b) => a.ticker.localeCompare(b.ticker))
  }, [assets])

  const openSheet = () => {
    setForm({ ...emptyForm(), asset_id: eligibleAssets[0]?.id || '' })
    setFormError('')
    setOpen(true)
  }

  const setType = (actionType) => {
    const [ratioFrom, ratioTo] = DEFAULT_RATIOS[actionType]
    setForm((current) => ({ ...current, action_type: actionType, ratio_from: ratioFrom, ratio_to: ratioTo }))
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setSaving(true)
    setFormError('')
    try {
      const created = await corporateActionsApi.create({
        asset_id: form.asset_id,
        action_type: form.action_type,
        ex_date: form.ex_date,
        ratio_from: parseDecimal(form.ratio_from),
        ratio_to: parseDecimal(form.ratio_to),
        bonus_unit_cost: form.action_type === 'BONUS' ? parseDecimal(form.bonus_unit_cost) : undefined,
        notes: form.notes || undefined,
      })
      setOpen(false)
      const ticker = eligibleAssets.find((asset) => asset.id === form.asset_id)?.ticker || 'o ativo'
      toast(
        `Evento registrado: as operações de ${ticker} antes de ${formatDateBR(form.ex_date)} foram ajustadas.`
          + (created?.price_refreshed ? '' : ' A cotação não foi atualizada: use "Atualizar cotações" em Posição.'),
        { duration: 7000 }
      )
    } catch (submitError) {
      setFormError(submitError.message || 'Não foi possível registrar o evento.')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (action) => {
    const confirmed = await confirmAction({
      title: `Desfazer o ${action.label} de ${action.ticker}?`,
      message: action.action_type === 'BONUS'
        ? 'As cotas da bonificação saem da carteira.'
        : 'As operações anteriores voltam à quantidade e ao preço originais.',
      confirmLabel: 'Desfazer',
    })
    if (!confirmed) return
    setError('')
    try {
      await corporateActionsApi.remove(action.id)
      toast('Evento desfeito.')
    } catch (deleteError) {
      setError(deleteError.message || 'Não foi possível desfazer o evento.')
    }
  }

  return (
    <Panel>
      <PanelHeader
        title="Eventos corporativos"
        description="Desdobramentos, grupamentos e bonificações. As operações anteriores à data ex são ajustadas à base nova."
        actions={(
          <Button type="button" variant="secondary" size="sm" icon={Plus} disabled={!eligibleAssets.length} onClick={openSheet}>
            Registrar evento
          </Button>
        )}
      />
      <div className="space-y-3 p-5">
        <AlertMessage message={error} onDismiss={() => setError('')} />
        {actions.length ? (
          <ul className="divide-y divide-zinc-100 rounded-2xl border border-zinc-200">
            {actions.map((action) => (
              <li key={action.id} className="flex items-center gap-3 px-3 py-2.5">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-zinc-900">
                    {action.ticker} · {action.label} {ratioLabel(action)}
                  </p>
                  <p className="text-xs text-zinc-500">
                    Data ex {formatDateBR(action.ex_date)}
                    {action.action_type === 'BONUS' ? ` · custo atribuído ${formatCurrency(action.bonus_unit_cost || 0)} por cota` : ''}
                    {action.notes ? ` · ${action.notes}` : ''}
                  </p>
                </div>
                <IconButton
                  label={`Desfazer ${action.label} de ${action.ticker}`}
                  icon={Trash2}
                  size="sm"
                  variant="danger"
                  onClick={() => handleDelete(action)}
                />
              </li>
            ))}
          </ul>
        ) : actionsQuery.isPending ? null : (
          <EmptyState
            icon={Shuffle}
            title="Nenhum evento"
            message="Registre aqui um desdobramento, grupamento ou bonificação avisado pela empresa."
            className="min-h-32"
          />
        )}
      </div>

      <Sheet
        open={open}
        onClose={() => setOpen(false)}
        title="Registrar evento corporativo"
        description={TYPE_HINTS[form.action_type]}
        footer={(
          <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <Button type="button" variant="secondary" size="lg" onClick={() => setOpen(false)}>Cancelar</Button>
            <Button type="submit" form="corporate-action-form" size="lg" loading={saving}>Registrar</Button>
          </div>
        )}
      >
        <form id="corporate-action-form" onSubmit={handleSubmit} className="space-y-4">
          <AlertMessage message={formError} onDismiss={() => setFormError('')} />
          <SegmentedControl items={TYPE_ITEMS} value={form.action_type} onChange={setType} />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Ativo">
              <select className="app-select" value={form.asset_id} onChange={(event) => setForm({ ...form, asset_id: event.target.value })} required>
                {eligibleAssets.map((asset) => <option key={asset.id} value={asset.id}>{asset.ticker}</option>)}
              </select>
            </Field>
            <Field label="Data ex" hint="Operações antes desta data são ajustadas.">
              <input type="date" className="app-input" value={form.ex_date} onChange={(event) => setForm({ ...form, ex_date: event.target.value })} required />
            </Field>
            <Field label="De (cotas antes)">
              <input type="text" inputMode="decimal" className="app-input" value={form.ratio_from} onChange={(event) => setForm({ ...form, ratio_from: event.target.value })} required />
            </Field>
            <Field label={form.action_type === 'BONUS' ? 'Para (cotas novas)' : 'Para (cotas depois)'}>
              <input type="text" inputMode="decimal" className="app-input" value={form.ratio_to} onChange={(event) => setForm({ ...form, ratio_to: event.target.value })} required />
            </Field>
            {form.action_type === 'BONUS' ? (
              <Field label="Custo atribuído por cota" hint="Do aviso da empresa; entra no preço médio. Vazio = zero.">
                <input type="text" inputMode="decimal" placeholder="0,00" className="app-input" value={form.bonus_unit_cost} onChange={(event) => setForm({ ...form, bonus_unit_cost: event.target.value })} />
              </Field>
            ) : null}
            <Field label="Observação" className={form.action_type === 'BONUS' ? '' : 'sm:col-span-2'}>
              <input type="text" className="app-input" value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} />
            </Field>
          </div>
          <p className="text-xs text-zinc-500">
            Depois de registrado, operações deste ativo com data anterior à data ex ficam bloqueadas; desfaça o evento para lançar uma.
          </p>
        </form>
      </Sheet>
    </Panel>
  )
}
