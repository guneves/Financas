import { useMemo, useState } from 'react'
import { Archive, Check, Pencil, Plus, Tags, X } from 'lucide-react'
import { categoriesApi } from '../../lib/dataApi'
import {
  AlertMessage,
  Badge,
  Button,
  Collapsible,
  EmptyState,
  Field,
  IconButton,
  Menu,
  Panel,
  PanelHeader,
  cx,
} from '../../components/ui'
import { confirmAction } from '../../lib/confirm'
import { invalidateServerData, useQuery, useReportQueryError } from '../../lib/queries'

const KIND_LABELS = {
  INCOME: 'Receita',
  EXPENSE: 'Despesa',
  BOTH: 'Ambos',
}

const emptyCategoryForm = () => ({ name: '', kind: 'EXPENSE', parent_id: '' })

const NO_ITEMS = []

// Categorias: criar (raiz ou subcategoria), renomear, arquivar e reativar.
// Veio da aba Categorias de Orcamento.jsx. Categoria nunca e apagada:
// DELETE /api/categories/<id> so preenche archived_at.
export default function CategoriasSection() {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [categoryForm, setCategoryForm] = useState(emptyCategoryForm)
  const [editingCategoryId, setEditingCategoryId] = useState('')
  const [categoryEdit, setCategoryEdit] = useState({ name: '', kind: 'EXPENSE' })

  const categoriesQuery = useQuery({
    queryKey: ['categorias', 'todas'],
    queryFn: () => categoriesApi.list({ include_archived: 1 }),
  })
  useReportQueryError(categoriesQuery, setError, 'Não foi possível carregar as categorias.')
  const categories = categoriesQuery.data || NO_ITEMS
  const loading = categoriesQuery.isPending
  const loadAll = () => invalidateServerData()

  const rootCategories = useMemo(
    () => categories.filter((category) => !category.archived_at && !category.parent_id),
    [categories]
  )

  const handleCreateCategory = async (event) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      await categoriesApi.create({
        name: categoryForm.name,
        kind: categoryForm.kind,
        parent_id: categoryForm.parent_id || undefined,
      })
      setCategoryForm(emptyCategoryForm())
      setFormOpen(false)
      await loadAll()
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível criar a categoria.')
    } finally {
      setSaving(false)
    }
  }

  const handleSaveCategory = async (category) => {
    setSaving(true)
    setError('')
    try {
      await categoriesApi.update(category.id, { name: categoryEdit.name, kind: categoryEdit.kind })
      setEditingCategoryId('')
      await loadAll()
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível atualizar a categoria.')
    } finally {
      setSaving(false)
    }
  }

  const handleArchiveCategory = async (category) => {
    if (!(await confirmAction({ title: `Arquivar "${category.name}"?`, message: 'Os lançamentos continuam, e dá para reativar depois.', confirmLabel: 'Arquivar', tone: 'neutral' }))) return
    setSaving(true)
    setError('')
    try {
      await categoriesApi.archive(category.id)
      await loadAll()
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível arquivar a categoria.')
    } finally {
      setSaving(false)
    }
  }

  const handleRestoreCategory = async (category) => {
    setSaving(true)
    setError('')
    try {
      await categoriesApi.update(category.id, { archived_at: null })
      await loadAll()
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível reativar a categoria.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Panel id="categorias" className="scroll-mt-20 lg:scroll-mt-8">
      <PanelHeader
        title="Categorias"
        description="Renomear leva o nome novo para os lançamentos, compras no cartão, recorrências e regras dela. Arquivar não apaga histórico."
        actions={<Badge>{categories.filter((category) => !category.archived_at).length} ativa(s)</Badge>}
      />

      <div className="space-y-4 p-5">
        <AlertMessage message={error} onDismiss={() => setError('')} />

        <Collapsible label="Nova categoria" icon={Plus} open={formOpen} onOpenChange={setFormOpen}>
          <form onSubmit={handleCreateCategory} className="grid grid-cols-1 gap-4 rounded-2xl border border-zinc-200 bg-zinc-50 p-4 sm:grid-cols-2 xl:grid-cols-4">
            <Field label="Nome">
              <input
                type="text"
                placeholder="Ex: Delivery"
                value={categoryForm.name}
                onChange={(event) => setCategoryForm({ ...categoryForm, name: event.target.value })}
                className="app-input"
                required
              />
            </Field>
            <Field label="Tipo">
              <select
                value={categoryForm.kind}
                onChange={(event) => setCategoryForm({ ...categoryForm, kind: event.target.value })}
                className="app-select"
              >
                <option value="EXPENSE">Despesa</option>
                <option value="INCOME">Receita</option>
                <option value="BOTH">Ambos</option>
              </select>
            </Field>
            <Field label="Categoria pai" hint="Opcional. Uma subcategoria precisa de uma categoria pai — só existe um nível.">
              <select
                value={categoryForm.parent_id}
                onChange={(event) => setCategoryForm({ ...categoryForm, parent_id: event.target.value })}
                className="app-select"
              >
                <option value="">Nenhuma (categoria raiz)</option>
                {rootCategories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </select>
            </Field>
            <div className="flex items-end">
              <Button type="submit" loading={saving} className="w-full">
                Salvar
              </Button>
            </div>
          </form>
        </Collapsible>

        {loading ? (
          <p className="py-6 text-center text-sm text-zinc-600">Carregando...</p>
        ) : categories.length === 0 ? (
          <EmptyState icon={Tags} title="Nenhuma categoria" message="Crie a primeira categoria acima." className="min-h-40" />
        ) : (
          <div className="divide-y divide-zinc-100 rounded-2xl border border-zinc-200">
            {categories.map((category) => {
              const isEditing = editingCategoryId === category.id
              return (
                <div key={category.id} className={cx('px-4 py-3', isEditing && 'bg-zinc-50')}>
                  {isEditing ? (
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                      <Field label="Nome" className="flex-1">
                        <input
                          type="text"
                          value={categoryEdit.name}
                          onChange={(event) => setCategoryEdit({ ...categoryEdit, name: event.target.value })}
                          className="app-input"
                        />
                      </Field>
                      <Field label="Tipo" className="sm:w-40">
                        <select
                          value={categoryEdit.kind}
                          onChange={(event) => setCategoryEdit({ ...categoryEdit, kind: event.target.value })}
                          className="app-select"
                        >
                          <option value="EXPENSE">Despesa</option>
                          <option value="INCOME">Receita</option>
                          <option value="BOTH">Ambos</option>
                        </select>
                      </Field>
                      <div className="flex gap-2">
                        <IconButton
                          label="Salvar"
                          icon={Check}
                          variant="primary"
                          onClick={() => handleSaveCategory(category)}
                        />
                        <IconButton label="Cancelar" icon={X} onClick={() => setEditingCategoryId('')} />
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className={cx('truncate', category.parent_id ? 'text-zinc-700' : 'font-semibold text-zinc-900', category.archived_at && 'text-zinc-500')}>
                          {category.parent_name ? `${category.parent_name} › ${category.name}` : category.name}
                        </p>
                        <div className="mt-1 flex flex-wrap items-center gap-2">
                          <span className="text-sm text-zinc-600">{KIND_LABELS[category.kind] || category.kind}</span>
                          {category.archived_at ? <Badge tone="neutral">Arquivada</Badge> : null}
                        </div>
                      </div>
                      <div className="flex shrink-0 gap-2">
                        {category.archived_at ? (
                          <Button size="sm" variant="secondary" onClick={() => handleRestoreCategory(category)}>
                            Reativar
                          </Button>
                        ) : (
                          <Menu
                            label={`Ações da categoria ${category.name}`}
                            size="md"
                            items={[
                              {
                                label: 'Renomear ou mudar tipo',
                                icon: Pencil,
                                onSelect: () => {
                                  setEditingCategoryId(category.id)
                                  setCategoryEdit({ name: category.name, kind: category.kind })
                                },
                              },
                              { label: 'Arquivar categoria', icon: Archive, onSelect: () => handleArchiveCategory(category) },
                            ]}
                          />
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </Panel>
  )
}
