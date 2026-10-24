import { useMemo, useState } from 'react'
import {
  CalendarClock,
  Check,
  Pause,
  Pencil,
  Play,
  Plus,
  Repeat,
  Trash2,
  X,
} from 'lucide-react'
import { accountsApi, categoriesApi, recurringApi } from '../lib/dataApi'
import { formatCurrency, formatDateBR, formatSignedCurrency, getLocalDateString } from '../lib/format'
import { invalidateServerData, useQuery, useReportQueryError } from '../lib/queries'
import { blockedRecurringMessage } from '../lib/transactions'
import { frequencyLabel, recurringAccountOptions, recurringEditPatch } from '../lib/recurring'
import {
  AlertMessage,
  Badge,
  Button,
  Collapsible,
  EmptyState,
  ListSkeleton,
  Field,
  IconButton,
  Menu,
  PageHeader,
  Panel,
  PanelHeader,
  SummaryPanel,
} from '../components/ui'
import { toast } from '../lib/toast'
import { confirmAction } from '../lib/confirm'

// Estado da recorrencia e rotulo, nao alerta: sem cor. Pendente (venceu) e
// que pede atencao, e tem o seu badge ambar.
const STATUS_TONES = {
  ACTIVE: 'neutral',
  PAUSED: 'neutral',
  FINISHED: 'neutral',
}

const STATUS_LABELS = {
  ACTIVE: 'Ativa',
  PAUSED: 'Pausada',
  FINISHED: 'Encerrada',
}

const emptyForm = () => ({
  description: '',
  amount: '',
  type: 'EXPENSE',
  category_id: '',
  account_id: '',
  frequency: 'MONTHLY',
  interval_count: '1',
  start_date: getLocalDateString(),
  end_date: '',
})


const NO_ITEMS = []

export default function Recorrentes() {
  const [form, setForm] = useState(emptyForm)
  const [formOpen, setFormOpen] = useState(false)
  const [editingId, setEditingId] = useState('')
  const [editDraft, setEditDraft] = useState({ amount: '', account_id: '' })
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const recurringQuery = useQuery({
    queryKey: ['recorrentes'],
    queryFn: async () => {
      const [listData, forecastData, categoryData, accountData] = await Promise.all([
        recurringApi.list(),
        recurringApi.forecast({ days: 90 }),
        categoriesApi.list(),
        accountsApi.list(),
      ])
      return {
        items: listData?.items || [],
        forecast: forecastData || null,
        categories: categoryData || [],
        accounts: accountData || [],
      }
    },
  })
  useReportQueryError(recurringQuery, setError, 'Não foi possível carregar os lançamentos recorrentes.')
  const items = recurringQuery.data?.items || NO_ITEMS
  const forecast = recurringQuery.data?.forecast || null
  const categories = recurringQuery.data?.categories || NO_ITEMS
  const accounts = recurringQuery.data?.accounts || NO_ITEMS
  const loading = recurringQuery.isPending

  const loadAll = () => invalidateServerData()

  const pendingCount = useMemo(
    () => items.reduce((total, item) => total + Number(item.pending_count || 0), 0),
    [items]
  )

  const windows = forecast?.windows || {}
  const window30 = windows['30'] || {}

  const handleCreate = async (event) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      await recurringApi.create({
        description: form.description,
        amount: Number(form.amount),
        type: form.type,
        category_id: form.category_id,
        account_id: form.account_id || null,
        frequency: form.frequency,
        interval_count: Number(form.interval_count || 1),
        start_date: form.start_date,
        end_date: form.end_date || null,
      })
      setForm(emptyForm())
      setFormOpen(false)
      await loadAll()
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível criar a recorrência.')
    } finally {
      setSaving(false)
    }
  }

  const handleRun = async () => {
    setSaving(true)
    setError('')
    try {
      const result = await recurringApi.run()
      toast(
        result.created
          ? `${result.created} lançamento(s) gerado(s) até ${formatDateBR(result.through)}.`
          : 'Nada pendente: todos os lançamentos recorrentes já estão em dia.',
        { tone: result.created ? 'success' : 'info' }
      )
      // Uma recorrencia numa conta arquivada nao lanca (o servidor a devolve em blocked).
      if (result.blocked?.length) setError(blockedRecurringMessage(result.blocked))
      await loadAll()
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível gerar os lançamentos.')
    } finally {
      setSaving(false)
    }
  }

  const handleToggleActive = async (item) => {
    setSaving(true)
    setError('')
    try {
      await recurringApi.update(item.id, { active: !item.active })
      await loadAll()
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível atualizar a recorrência.')
    } finally {
      setSaving(false)
    }
  }

  const handleSaveEdit = async (item) => {
    const patch = recurringEditPatch(item, editDraft)
    if (!Object.keys(patch).length) {
      setEditingId('')
      return
    }
    setSaving(true)
    setError('')
    try {
      await recurringApi.update(item.id, patch)
      setEditingId('')
      await loadAll()
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível atualizar a recorrência.')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (item) => {
    const confirmed = await confirmAction({
      title: `Excluir a recorrência "${item.description || item.category}"?`,
      message: 'Os lançamentos já gerados continuam no extrato.',
      confirmLabel: 'Excluir',
    })
    if (!confirmed) return

    setSaving(true)
    setError('')
    try {
      const result = await recurringApi.remove(item.id)
      toast(
        result.kept_transactions
          ? `Recorrência excluída. ${result.kept_transactions} lançamento(s) já gerado(s) foram mantidos.`
          : 'Recorrência excluída.'
      )
      await loadAll()
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível excluir a recorrência.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Recorrentes"
        description="Aluguel, salário, mensalidade, assinatura: o molde fica aqui e o lançamento é gerado quando vence."
        actions={
          <Button icon={CalendarClock} onClick={handleRun} loading={saving} className="h-11 lg:h-10">
            {pendingCount ? `Lançar ${pendingCount} pendente(s)` : 'Lançar pendentes'}
          </Button>
        }
      />

      <AlertMessage message={error} onDismiss={() => setError('')} />

      <SummaryPanel
        lead={{
          label: 'Saldo previsto em 30 dias',
          value: formatSignedCurrency(window30.net),
          hint: windows['90'] ? `Em 90 dias: ${formatSignedCurrency(windows['90'].net)}` : 'Recorrências ativas',
          tone: Number(window30.net || 0) < 0 ? 'loss' : 'neutral',
        }}
        figures={[
          { label: 'Receitas previstas', value: formatCurrency(window30.income), hint: 'Próximos 30 dias' },
          { label: 'Saídas previstas', value: formatCurrency(window30.expense), hint: 'Próximos 30 dias' },
          {
            label: 'Pendentes',
            value: String(pendingCount),
            hint: pendingCount ? 'Venceram e não foram lançados' : 'Tudo em dia',
            tone: pendingCount ? 'neutral' : 'muted',
          },
        ]}
      />

      <Panel>
        <PanelHeader
          title="Recorrências"
          description="Pausar interrompe a geração sem apagar o histórico: ao retomar, só o período pausado é pulado — o que já tinha vencido antes continua pendente. Excluir mantém os lançamentos já gerados."
        />

        <div className="border-b border-zinc-100 px-5 py-4">
          <Collapsible label="Nova recorrência" icon={Plus} variant="secondary" open={formOpen} onOpenChange={setFormOpen} buttonClassName="h-11 lg:h-10">
            <form onSubmit={handleCreate} className="grid grid-cols-1 gap-4 rounded-2xl border border-zinc-200 bg-zinc-50 p-4 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4">
              <p className="text-sm text-zinc-600 sm:col-span-2 md:col-span-3 xl:col-span-4">
                O lançamento só nasce quando a data chega — nada é antecipado no extrato.
              </p>
              <Field label="Descrição">
                <input
                  type="text"
                  value={form.description}
                  onChange={(event) => setForm({ ...form, description: event.target.value })}
                  placeholder="Aluguel"
                  className="app-input"
                  required
                />
              </Field>
              <Field label="Valor">
                <input
                  type="number" inputMode="decimal"
                  step="0.01"
                  min="0"
                  placeholder="0,00"
                  value={form.amount}
                  onChange={(event) => setForm({ ...form, amount: event.target.value })}
                  className="app-input"
                  required
                />
              </Field>
              <Field label="Tipo">
                <select
                  value={form.type}
                  onChange={(event) => setForm({ ...form, type: event.target.value })}
                  className="app-select"
                >
                  <option value="EXPENSE">Despesa</option>
                  <option value="INCOME">Receita</option>
                </select>
              </Field>
              <Field label="Categoria">
                <select
                  value={form.category_id}
                  onChange={(event) => setForm({ ...form, category_id: event.target.value })}
                  className="app-select"
                  required
                >
                  <option value="">Selecione</option>
                  {categories.map((category) => (
                    <option key={category.id} value={category.id}>
                      {category.parent_name ? `${category.parent_name} › ${category.name}` : category.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Conta" hint="Opcional — usa a conta padrão">
                <select
                  value={form.account_id}
                  onChange={(event) => setForm({ ...form, account_id: event.target.value })}
                  className="app-select"
                >
                  <option value="">Conta padrão</option>
                  {accounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Frequência">
                <select
                  value={form.frequency}
                  onChange={(event) => setForm({ ...form, frequency: event.target.value })}
                  className="app-select"
                >
                  <option value="MONTHLY">Mensal</option>
                  <option value="WEEKLY">Semanal</option>
                  <option value="YEARLY">Anual</option>
                </select>
              </Field>
              <Field label="A cada" hint="1 = todo período">
                <input
                  type="number" inputMode="numeric"
                  min="1"
                  max="60"
                  step="1"
                  value={form.interval_count}
                  onChange={(event) => setForm({ ...form, interval_count: event.target.value })}
                  className="app-input"
                />
              </Field>
              <Field label="Primeira data" hint="Define o dia de ancoragem">
                <input
                  type="date"
                  value={form.start_date}
                  onChange={(event) => setForm({ ...form, start_date: event.target.value })}
                  className="app-input"
                  required
                />
              </Field>
              <Field label="Até" hint="Opcional — sem data, não termina">
                <input
                  type="date"
                  value={form.end_date}
                  onChange={(event) => setForm({ ...form, end_date: event.target.value })}
                  className="app-input"
                />
              </Field>
              <div className="flex items-end">
                <Button type="submit" icon={Check} loading={saving} className="h-11 w-full lg:h-10">
                  Salvar
                </Button>
              </div>
            </form>
          </Collapsible>
        </div>

        {loading ? (
          <ListSkeleton rows={5} />
        ) : !items.length ? (
          <EmptyState
            icon={Repeat}
            title="Nenhuma recorrência cadastrada"
            message="Cadastre o aluguel, o salário e as assinaturas uma vez — depois é só lançar os pendentes."
            className="m-5"
          />
        ) : (
          <div className="divide-y divide-zinc-100">
            {items.map((item) => (
              <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className={`truncate font-semibold ${item.status === 'FINISHED' ? 'text-zinc-500' : 'text-zinc-900'}`}>
                      {item.description || item.category}
                    </p>
                    <Badge tone={STATUS_TONES[item.status] || 'neutral'}>
                      {STATUS_LABELS[item.status] || item.status}
                    </Badge>
                    {item.pending_count ? (
                      <Badge tone="warning">{item.pending_count} pendente(s)</Badge>
                    ) : null}
                  </div>
                  <p className="mt-1 text-sm text-zinc-600">
                    {item.type === 'INCOME' ? 'Receita' : 'Despesa'} · {item.category} · {frequencyLabel(item)} ·{' '}
                    {item.status === 'PAUSED' && item.paused_at
                      ? `pausada desde ${formatDateBR(item.paused_at)}`
                      : item.next_run_date
                        ? `próxima em ${formatDateBR(item.next_run_date)}`
                        : 'sem próxima data'}
                    {item.end_date ? ` · até ${formatDateBR(item.end_date)}` : ''}
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {editingId === item.id ? (
                    <>
                      <input
                        type="number" inputMode="decimal"
                        step="0.01"
                        min="0"
                        value={editDraft.amount}
                        onChange={(event) => setEditDraft({ ...editDraft, amount: event.target.value })}
                        aria-label="Valor"
                        className="app-input w-32"
                      />
                      <select
                        value={editDraft.account_id}
                        onChange={(event) => setEditDraft({ ...editDraft, account_id: event.target.value })}
                        aria-label="Conta"
                        className="app-select w-44"
                      >
                        {!editDraft.account_id ? <option value="">Conta padrão</option> : null}
                        {recurringAccountOptions(item, accounts).map((option) => (
                          <option key={option.id} value={option.id} disabled={option.disabled}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                      <IconButton
                        label="Salvar"
                        icon={Check}
                        variant="primary"
                        disabled={saving}
                        onClick={() => handleSaveEdit(item)}
                      />
                      <IconButton label="Cancelar" icon={X} onClick={() => setEditingId('')} />
                    </>
                  ) : (
                    <>
                      <span
                        className={
                          item.type === 'INCOME'
                            ? 'mr-1 whitespace-nowrap text-base font-semibold text-emerald-700'
                            : 'mr-1 whitespace-nowrap text-base font-semibold text-zinc-950'
                        }
                      >
                        {formatSignedCurrency(item.amount, item.type === 'INCOME' ? 1 : -1)}
                      </span>
                      <Menu
                        label={`Ações de ${item.description || item.category}`}
                        size="md"
                        items={[
                          {
                            label: 'Editar valor e conta',
                            icon: Pencil,
                            onSelect: () => {
                              setEditingId(item.id)
                              setEditDraft({ amount: String(item.amount ?? ''), account_id: item.account_id || '' })
                            },
                          },
                          {
                            label: item.active ? 'Pausar' : 'Retomar',
                            icon: item.active ? Pause : Play,
                            onSelect: () => handleToggleActive(item),
                          },
                          { label: 'Excluir recorrência', icon: Trash2, tone: 'danger', onSelect: () => handleDelete(item) },
                        ]}
                      />
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel>
        <PanelHeader
          title="Próximos 90 dias"
          description="Projeção das recorrências ativas. Nada aqui existe no extrato ainda."
        />
        {!forecast?.occurrences?.length ? (
          <EmptyState
            icon={CalendarClock}
            title="Nada previsto"
            message="Cadastre uma recorrência ativa para ver a projeção de caixa."
            className="m-5"
          />
        ) : (
          <div className="divide-y divide-zinc-100">
            {forecast.occurrences.map((occurrence) => (
              <div
                key={`${occurrence.recurring_id}-${occurrence.date}`}
                className="flex items-center justify-between gap-3 px-5 py-3"
              >
                {/* No celular a descricao desce para a segunda linha; no desktop fica na mesma. */}
                <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1 sm:flex-nowrap">
                  <span className="w-24 shrink-0 text-sm font-semibold text-zinc-600">
                    {formatDateBR(occurrence.date)}
                  </span>
                  <span className="order-last min-w-0 basis-full truncate text-sm text-zinc-800 sm:order-none sm:basis-auto">
                    {occurrence.description || occurrence.category}
                  </span>
                  {occurrence.pending ? <Badge tone="warning" className="shrink-0">venceu</Badge> : null}
                </div>
                <span
                  className={
                    occurrence.type === 'INCOME'
                      ? 'shrink-0 whitespace-nowrap text-sm font-semibold text-emerald-700'
                      : 'shrink-0 whitespace-nowrap text-sm font-semibold text-zinc-950'
                  }
                >
                  {formatSignedCurrency(occurrence.amount, occurrence.type === 'INCOME' ? 1 : -1)}
                </span>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  )
}
