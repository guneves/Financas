import { useEffect, useState } from 'react'
import { ListChecks, PauseCircle, Pencil, PlayCircle, Plus, Trash2, Wand2 } from 'lucide-react'
import { categoriesApi, importRulesApi } from '../../lib/dataApi'
import {
  AlertMessage,
  Badge,
  Button,
  Collapsible,
  EmptyState,
  Field,
  Menu,
  Panel,
  PanelHeader,
  Sheet,
  cx,
} from '../../components/ui'
import { toast } from '../../lib/toast'
import { formatDateBR, formatSignedCurrency } from '../../lib/format'
import { confirmAction } from '../../lib/confirm'

const MATCH_LABELS = {
  CONTAINS: 'contém',
  STARTS_WITH: 'começa com',
  EQUALS: 'é igual a',
}

const APPLIES_LABELS = {
  BOTH: 'Entradas e saídas',
  INCOME: 'Só entradas',
  EXPENSE: 'Só saídas',
}

const emptyForm = () => ({
  pattern: '',
  match_type: 'CONTAINS',
  applies_to: 'BOTH',
  category: '',
  priority: 0,
})

const formFromRule = (rule) => ({
  pattern: rule.pattern,
  match_type: rule.match_type,
  applies_to: rule.applies_to,
  category: rule.category,
  priority: rule.priority,
})

// Regras de categorizacao da importacao de extrato (Fase 4). Sozinhas elas so
// rodam na previa da importacao: mudar uma regra nao reescreve o passado. Para
// o passado existe "Aplicar": mostra o que mudaria e so grava as linhas que o
// dono deixou marcadas.
export default function RegrasSection({ refreshKey = 0 }) {
  const [rules, setRules] = useState([])
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [form, setForm] = useState(emptyForm)
  const [editingId, setEditingId] = useState(null)
  // { rule: a regra, ou null para todas; items; total; truncated; selected: Set }
  const [applying, setApplying] = useState(null)
  const [applyLoading, setApplyLoading] = useState(false)
  const [applySaving, setApplySaving] = useState(false)
  const [applyError, setApplyError] = useState('')

  const loadAll = async () => {
    setError('')
    try {
      const [ruleData, categoryData] = await Promise.all([
        importRulesApi.list(),
        categoriesApi.list(),
      ])
      setRules(ruleData?.items || [])
      setCategories((categoryData || []).filter((category) => !category.archived_at))
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível carregar as regras.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAll()
  }, [refreshKey])

  const handleSubmit = async (event) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    const payload = {
      pattern: form.pattern,
      match_type: form.match_type,
      applies_to: form.applies_to,
      category: form.category,
      priority: Number(form.priority) || 0,
    }
    try {
      if (editingId) {
        await importRulesApi.update(editingId, payload)
      } else {
        await importRulesApi.create(payload)
      }
      setForm(emptyForm())
      setEditingId(null)
      setFormOpen(false)
      await loadAll()
    } catch (requestError) {
      setError(requestError.message || (editingId ? 'Não foi possível salvar a regra.' : 'Não foi possível criar a regra.'))
    } finally {
      setSaving(false)
    }
  }

  const handleEdit = (rule) => {
    setError('')
    setEditingId(rule.id)
    setForm(formFromRule(rule))
    setFormOpen(true)
  }

  const handleFormOpenChange = (next) => {
    setFormOpen(next)
    if (!next && editingId) {
      setEditingId(null)
      setForm(emptyForm())
    }
  }

  const openApply = async (rule = null) => {
    setApplyError('')
    setApplying({ rule, items: [], total: 0, truncated: false, selected: new Set() })
    setApplyLoading(true)
    try {
      const data = await importRulesApi.applyPreview(rule ? { rule_id: rule.id } : {})
      const items = data?.items || []
      setApplying({
        rule,
        items,
        total: data?.total || 0,
        truncated: Boolean(data?.truncated),
        selected: new Set(items.map((item) => item.id)),
      })
    } catch (requestError) {
      setApplyError(requestError.message || 'Não foi possível ver o que as regras mudariam.')
    } finally {
      setApplyLoading(false)
    }
  }

  const closeApply = () => setApplying(null)

  const toggleSelected = (id) => {
    setApplying((current) => {
      const selected = new Set(current.selected)
      if (selected.has(id)) selected.delete(id)
      else selected.add(id)
      return { ...current, selected }
    })
  }

  const toggleAll = () => {
    setApplying((current) => ({
      ...current,
      selected: current.selected.size === current.items.length
        ? new Set()
        : new Set(current.items.map((item) => item.id)),
    }))
  }

  const handleApply = async () => {
    if (!applying?.selected.size) return
    setApplySaving(true)
    setApplyError('')
    try {
      const result = await importRulesApi.apply({
        transaction_ids: [...applying.selected],
        ...(applying.rule ? { rule_id: applying.rule.id } : {}),
      })
      const updated = result?.updated || 0
      const skipped = result?.skipped || 0
      toast(
        `${updated} lançamento(s) recategorizado(s).`
        + (skipped ? ` ${skipped} mudou(aram) desde a prévia e ficou(aram) como estava(m).` : '')
      )
      setApplying(null)
      await loadAll()
    } catch (requestError) {
      setApplyError(requestError.message || 'Não foi possível aplicar as regras.')
    } finally {
      setApplySaving(false)
    }
  }

  const handleToggle = async (rule) => {
    setError('')
    try {
      await importRulesApi.update(rule.id, { active: !rule.active })
      await loadAll()
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível atualizar a regra.')
    }
  }

  const handleRemove = async (rule) => {
    if (!(await confirmAction({ title: `Apagar a regra "${rule.pattern}"?`, message: 'Os lançamentos já categorizados continuam como estão.', confirmLabel: 'Apagar' }))) return
    setError('')
    try {
      await importRulesApi.remove(rule.id)
      await loadAll()
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível apagar a regra.')
    }
  }

  return (
    <Panel id="regras-de-importacao" className="scroll-mt-20 lg:scroll-mt-8">
      <PanelHeader
        title="Regras de importação"
        description="Descrição do extrato → categoria. Aplicadas na prévia da importação, de maior para menor prioridade."
        actions={rules.some((rule) => rule.active) ? (
          <Button variant="secondary" size="sm" icon={ListChecks} onClick={() => openApply(null)}>
            Aplicar ao extrato
          </Button>
        ) : null}
      />
      <div className="space-y-4 p-5">
        <AlertMessage message={error} onDismiss={() => setError('')} />

        {loading ? (
          <p className="text-sm text-zinc-500">Carregando...</p>
        ) : rules.length ? (
          <div className="divide-y divide-zinc-100 rounded-2xl border border-zinc-200">
            {rules.map((rule) => (
              <div key={rule.id} className="flex flex-wrap items-center gap-3 p-3">
                <div className="min-w-[14rem] flex-1">
                  <p className={cx('truncate text-sm font-semibold', rule.active ? 'text-zinc-900' : 'text-zinc-500 line-through')}>
                    {MATCH_LABELS[rule.match_type]} “{rule.pattern}” → {rule.category}
                  </p>
                  <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
                    <span>{APPLIES_LABELS[rule.applies_to]}</span>
                    <span>prioridade {rule.priority}</span>
                    {rule.hits ? <Badge>{rule.hits} lançamento(s)</Badge> : null}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="secondary" size="sm" onClick={() => openApply(rule)}>
                    Aplicar
                  </Button>
                  <Menu
                    label={`Ações da regra ${rule.pattern}`}
                    items={[
                      { label: 'Editar regra', icon: Pencil, onSelect: () => handleEdit(rule) },
                      { label: rule.active ? 'Desativar' : 'Ativar', icon: rule.active ? PauseCircle : PlayCircle, onSelect: () => handleToggle(rule) },
                      { label: 'Apagar regra', icon: Trash2, tone: 'danger', onSelect: () => handleRemove(rule) },
                    ]}
                  />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            icon={Wand2}
            title="Nenhuma regra"
            message="Crie uma regra aqui, ou direto na prévia da importação com o botão “Criar regra”."
            className="min-h-40"
          />
        )}

        <Collapsible
          label={editingId ? 'Editar regra' : 'Nova regra'}
          icon={editingId ? Pencil : Plus}
          open={formOpen}
          onOpenChange={handleFormOpenChange}
        >
          <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-4 rounded-2xl border border-zinc-200 bg-zinc-50 p-4 sm:grid-cols-2 xl:grid-cols-5">
            <Field label="Texto" hint="Sem diferenciar maiúscula ou acento.">
              <input
                type="text"
                placeholder="Ex: uber"
                value={form.pattern}
                onChange={(event) => setForm({ ...form, pattern: event.target.value })}
                className="app-input"
                required
              />
            </Field>
            <Field label="Comparação">
              <select value={form.match_type} onChange={(event) => setForm({ ...form, match_type: event.target.value })} className="app-select">
                {Object.entries(MATCH_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </Field>
            <Field label="Categoria">
              <select value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })} className="app-select" required>
                <option value="">Escolha...</option>
                {categories.map((category) => (
                  <option key={category.id} value={category.name}>{category.name}</option>
                ))}
              </select>
            </Field>
            <Field label="Aplica-se a">
              <select value={form.applies_to} onChange={(event) => setForm({ ...form, applies_to: event.target.value })} className="app-select">
                {Object.entries(APPLIES_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </Field>
            <Field label="Prioridade" hint="Maior ganha do empate.">
              <input
                type="number"
                value={form.priority}
                onChange={(event) => setForm({ ...form, priority: event.target.value })}
                className="app-input"
              />
            </Field>
            <div className="flex items-end gap-2 xl:col-span-5">
              <Button type="submit" loading={saving}>{editingId ? 'Salvar alterações' : 'Salvar regra'}</Button>
              {editingId ? (
                <Button type="button" variant="secondary" onClick={() => handleFormOpenChange(false)}>Cancelar</Button>
              ) : null}
            </div>
          </form>
        </Collapsible>
      </div>

      <Sheet
        open={Boolean(applying)}
        onClose={closeApply}
        title={applying?.rule ? `Aplicar “${applying.rule.pattern}”` : 'Aplicar regras ao extrato'}
        description={applying?.rule
          ? `Lançamentos já gravados que esta regra passaria para ${applying.rule.category}.`
          : 'Lançamentos já gravados que as regras ativas mudariam de categoria, na ordem de prioridade.'}
        footer={applying?.items.length ? (
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button variant="secondary" onClick={closeApply}>Cancelar</Button>
            <Button onClick={handleApply} loading={applySaving} disabled={!applying.selected.size}>
              Recategorizar {applying.selected.size}
            </Button>
          </div>
        ) : null}
      >
        <div className="space-y-3">
          <AlertMessage message={applyError} onDismiss={() => setApplyError('')} />
          {applyLoading ? (
            <p className="text-sm text-zinc-500">Procurando lançamentos...</p>
          ) : applying?.items.length ? (
            <>
              <div className="flex items-center justify-between gap-3 text-sm">
                <label className="flex items-center gap-2 font-medium text-zinc-700">
                  <input
                    type="checkbox"
                    checked={applying.selected.size === applying.items.length}
                    onChange={toggleAll}
                    className="h-4 w-4 rounded border-zinc-300 text-emerald-600"
                  />
                  Todos
                </label>
                <span className="text-zinc-500">
                  {applying.selected.size} de {applying.items.length} marcados
                  {applying.truncated ? ` · primeiros ${applying.items.length} de ${applying.total}` : ''}
                </span>
              </div>
              <ul className="divide-y divide-zinc-100 rounded-2xl border border-zinc-200">
                {applying.items.map((item) => (
                  <li key={item.id}>
                    <label className="flex cursor-pointer items-start gap-3 px-3 py-2.5">
                      <input
                        type="checkbox"
                        checked={applying.selected.has(item.id)}
                        onChange={() => toggleSelected(item.id)}
                        className="mt-0.5 h-4 w-4 shrink-0 rounded border-zinc-300 text-emerald-600"
                      />
                      <span className="min-w-0 flex-1">
                        <span className="flex items-baseline justify-between gap-3">
                          <span className="truncate text-sm font-medium text-zinc-900" title={item.description}>{item.description}</span>
                          <span className="num shrink-0 text-sm text-zinc-700">
                            {formatSignedCurrency(item.amount, item.type === 'INCOME' ? 1 : -1)}
                          </span>
                        </span>
                        <span className="mt-0.5 block truncate text-xs text-zinc-500">
                          {formatDateBR(item.date)}
                          {item.account_name ? ` · ${item.account_name}` : ''}
                          {' · '}{item.category} → <span className="font-medium text-zinc-700">{item.new_category}</span>
                          {applying.rule ? null : ` (“${item.rule_pattern}”)`}
                        </span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            </>
          ) : applying && !applyError ? (
            <EmptyState
              icon={ListChecks}
              title="Nada a mudar"
              message="Nenhum lançamento gravado mudaria de categoria. Transferências, investimentos e pagamentos de fatura ficam de fora."
              className="min-h-40"
            />
          ) : null}
        </div>
      </Sheet>
    </Panel>
  )
}
