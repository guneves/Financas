import { useEffect, useState } from 'react'
import { Plus, Trash2, Wand2 } from 'lucide-react'
import { categoriesApi, importRulesApi } from '../../lib/dataApi'
import {
  AlertMessage,
  Badge,
  Button,
  Collapsible,
  EmptyState,
  Field,
  IconButton,
  Panel,
  PanelHeader,
  cx,
} from '../../components/ui'

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

// Regras de categorizacao da importacao de extrato (Fase 4). Elas rodam na
// previa da importacao, nunca sobre um lancamento ja gravado: mudar uma regra
// aqui nao reescreve o passado.
export default function RegrasSection({ refreshKey = 0 }) {
  const [rules, setRules] = useState([])
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [form, setForm] = useState(emptyForm)

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

  const handleCreate = async (event) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      await importRulesApi.create({
        pattern: form.pattern,
        match_type: form.match_type,
        applies_to: form.applies_to,
        category: form.category,
        priority: Number(form.priority) || 0,
      })
      setForm(emptyForm())
      setFormOpen(false)
      await loadAll()
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível criar a regra.')
    } finally {
      setSaving(false)
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
    if (!window.confirm(`Apagar a regra "${rule.pattern}"? Os lançamentos já categorizados continuam como estão.`)) return
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
      />
      <div className="space-y-4">
        <AlertMessage message={error} onDismiss={() => setError('')} />

        {loading ? (
          <p className="text-sm text-zinc-500">Carregando...</p>
        ) : rules.length ? (
          <div className="divide-y divide-zinc-100 rounded-lg border border-zinc-200">
            {rules.map((rule) => (
              <div key={rule.id} className="flex flex-wrap items-center gap-3 p-3">
                <div className="min-w-0 flex-1">
                  <p className={cx('truncate text-sm font-semibold', rule.active ? 'text-zinc-900' : 'text-zinc-500 line-through')}>
                    {MATCH_LABELS[rule.match_type]} “{rule.pattern}” → {rule.category}
                  </p>
                  <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
                    <span>{APPLIES_LABELS[rule.applies_to]}</span>
                    <span>prioridade {rule.priority}</span>
                    {rule.hits ? <Badge>{rule.hits} lançamento(s)</Badge> : null}
                  </p>
                </div>
                <Button variant="secondary" size="sm" onClick={() => handleToggle(rule)}>
                  {rule.active ? 'Desativar' : 'Ativar'}
                </Button>
                <IconButton label="Apagar regra" icon={Trash2} variant="danger" onClick={() => handleRemove(rule)} />
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

        <Collapsible label="Nova regra" icon={Plus} open={formOpen} onOpenChange={setFormOpen}>
          <form onSubmit={handleCreate} className="grid grid-cols-1 gap-4 rounded-lg border border-zinc-200 bg-zinc-50 p-4 sm:grid-cols-2 xl:grid-cols-5">
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
            <div className="flex items-end xl:col-span-5">
              <Button type="submit" loading={saving}>Salvar regra</Button>
            </div>
          </form>
        </Collapsible>
      </div>
    </Panel>
  )
}
