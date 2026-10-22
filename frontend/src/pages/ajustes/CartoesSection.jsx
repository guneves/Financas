import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CreditCard, Pencil, Plus, Trash2 } from 'lucide-react'
import { accountsApi, creditCardsApi } from '../../lib/dataApi'
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
  SegmentedControl,
  Sheet,
} from '../../components/ui'
import { toast } from '../../lib/toast'
import { confirmAction } from '../../lib/confirm'
import { invalidateServerData, useQuery, useReportQueryError } from '../../lib/queries'
import { CARD_FUNCTION_ITEMS, cardFormPayload, cardFunctionLabel, cardFunctionOf, hasCredit, hasDebit } from '../../lib/cardFunctions'

const emptyCardForm = () => ({ name: '', functions: 'CREDIT', due_day: '', closing_day: '', autopay_account_id: '', debit_account_id: '' })

// A conta do debito sai das contas do banco: a Corretora e da carteira.
const debitAccountsOf = (accounts) => accounts.filter((account) => account.type !== 'BROKERAGE')

const NO_ITEMS = []

// Cartoes de credito: lista, editar, excluir (arquivar, 037) e criar. Veio de Transactions.jsx.
// As compras e faturas continuam em Lancamentos > Cartoes.
//
// Funcoes (041): credito (fatura, vencimento, fechamento), debito (a compra e
// uma despesa na conta escolhida) ou os dois. Um cartao so debito (o Flash)
// nao tem fatura nem debito automatico.
//
// Debito automatico: com uma conta escolhida, cada fatura e paga sozinha no
// dia do vencimento, debitando essa conta. So vale para faturas que vencem a
// partir do dia em que foi ligado; as anteriores seguem para pagamento manual.
export default function CartoesSection() {
  const [savingAutopayId, setSavingAutopayId] = useState(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [cardForm, setCardForm] = useState(emptyCardForm)
  // Corrigir um cartao (nome, vencimento, fechamento): antes so restava excluir.
  const [editing, setEditing] = useState(null)
  const [editForm, setEditForm] = useState(emptyCardForm)

  const cardsQuery = useQuery({ queryKey: ['cartoes'], queryFn: () => creditCardsApi.list() })
  const accountsQuery = useQuery({ queryKey: ['contas', 'ativas'], queryFn: () => accountsApi.list() })
  useReportQueryError(cardsQuery, setError, 'Não foi possível carregar os cartões.')
  const cards = cardsQuery.data || NO_ITEMS
  const accounts = accountsQuery.data || NO_ITEMS
  const debitAccounts = debitAccountsOf(accounts)
  const accountName = (id) => accounts.find((account) => account.id === id)?.name || 'conta arquivada'
  const loading = cardsQuery.isPending
  const fetchCards = () => invalidateServerData()

  const handleDueDayChange = (event) => {
    const due = parseInt(event.target.value)
    let closing = ''
    if (!Number.isNaN(due)) {
      closing = due - 7
      if (closing <= 0) closing += 30
    }
    setCardForm({ ...cardForm, due_day: event.target.value, closing_day: closing.toString() })
  }

  const handleCreateCard = async (event) => {
    event.preventDefault()
    const { payload, error: formError } = cardFormPayload(cardForm)
    if (formError) {
      setError(formError)
      return
    }

    setSaving(true)
    setError('')
    try {
      await creditCardsApi.create(payload)
      await fetchCards()
      toast(`Cartão "${payload.name}" criado.`)
      setCardForm(emptyCardForm())
      setFormOpen(false)
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível criar o cartão.')
    } finally {
      setSaving(false)
    }
  }

  const handleAutopayChange = async (card, accountId) => {
    setSavingAutopayId(card.id)
    setError('')
    try {
      await creditCardsApi.setAutopay(card.id, accountId)
      await fetchCards()
      const account = accounts.find((item) => item.id === accountId)
      toast(account
        ? `Débito automático do "${card.name}" ligado: a fatura será paga no vencimento, dia ${card.due_day}, com saldo de ${account.name}.`
        : `Débito automático do "${card.name}" desligado.`)
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível alterar o débito automático.')
    } finally {
      setSavingAutopayId(null)
    }
  }

  const openEdit = (card) => {
    setEditing(card)
    // Um cartao so debito guarda 1 nas datas (041): o formulario abre vazio.
    const credit = hasCredit(card)
    setEditForm({
      name: card.name,
      functions: cardFunctionOf(card),
      due_day: credit ? String(card.due_day) : '',
      closing_day: credit ? String(card.closing_day) : '',
      debit_account_id: card.debit_account_id || '',
    })
  }

  const handleSaveEdit = async (event) => {
    event.preventDefault()
    if (!editing) return
    // Sem autopay_account_id: o debito automatico se muda na lista. Tirar o
    // credito o desliga no servidor.
    const { payload, error: formError } = cardFormPayload(editForm)
    if (formError) {
      setError(formError)
      return
    }
    setSaving(true)
    setError('')
    try {
      await creditCardsApi.update(editing.id, payload)
      await fetchCards()
      toast(`Cartão "${payload.name}" atualizado.`)
      setEditing(null)
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível atualizar o cartão.')
    } finally {
      setSaving(false)
    }
  }

  // O servidor decide (037): com item em aberto recusa; com historico arquiva
  // (compras, orcamentos e pagamentos ficam); sem nada, apaga.
  const handleDeleteCard = async (id, name) => {
    if (!(await confirmAction({
      title: `Excluir o cartão "${name}"?`,
      message: 'Ele sai das listas e não recebe compras novas. As compras já pagas e os pagamentos de fatura continuam no histórico e nos orçamentos. Um cartão com fatura em aberto não pode ser excluído.',
      confirmLabel: 'Excluir cartão',
    }))) return

    setError('')
    try {
      await creditCardsApi.remove(id)
      await fetchCards()
      toast(`Cartão "${name}" excluído.`)
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível excluir o cartão.')
    }
  }

  return (
    <Panel id="cartoes" className="scroll-mt-20 lg:scroll-mt-8">
      <PanelHeader
        title="Cartões"
        description="Crédito, débito ou os dois. Compras e faturas do crédito ficam em Lançamentos › Cartões."
        actions={<Badge>{cards.length} cartão(ões)</Badge>}
      />

      <div className="space-y-4 p-5">
        <AlertMessage message={error} onDismiss={() => setError('')} />

        {loading ? (
          <p className="py-6 text-center text-sm text-zinc-600">Carregando...</p>
        ) : cards.length > 0 ? (
          <div className="divide-y divide-zinc-100 rounded-2xl border border-zinc-200">
            {cards.map((card) => (
              <div key={card.id} className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="truncate font-medium text-zinc-900">{card.name}</p>
                    <Badge>{cardFunctionLabel(card)}</Badge>
                    {card.autopay_account_id ? <Badge>Débito automático</Badge> : null}
                  </div>
                  <p className="text-sm text-zinc-600">
                    {[
                      hasCredit(card) ? `Vence dia ${card.due_day} • Fecha dia ${card.closing_day}` : null,
                      hasDebit(card) ? `Débito em ${accountName(card.debit_account_id)}` : null,
                    ].filter(Boolean).join(' • ')}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {hasCredit(card) ? (
                    <label className="flex min-w-0 flex-1 flex-col gap-1 text-xs font-semibold text-zinc-600 sm:w-56 sm:flex-none">
                      Débito automático
                      <select
                        value={card.autopay_account_id || ''}
                        disabled={savingAutopayId === card.id}
                        onChange={(event) => handleAutopayChange(card, event.target.value)}
                        className="app-input"
                      >
                        <option value="">Desligado</option>
                        {accounts.map((account) => (
                          <option key={account.id} value={account.id}>{account.name}</option>
                        ))}
                      </select>
                    </label>
                  ) : null}
                  <Menu
                    label={`Ações do cartão ${card.name}`}
                    size="md"
                    items={[
                      { label: 'Editar cartão', icon: Pencil, onSelect: () => openEdit(card) },
                      { label: 'Excluir cartão', icon: Trash2, tone: 'danger', onSelect: () => handleDeleteCard(card.id, card.name) },
                    ]}
                  />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState icon={CreditCard} title="Nenhum cartão" message="Cadastre um cartão para lançar compras no crédito ou no débito." className="min-h-40" />
        )}

        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <Collapsible label="Novo cartão" icon={Plus} open={formOpen} onOpenChange={setFormOpen} className="min-w-0 flex-1">
            <form onSubmit={handleCreateCard} className="grid grid-cols-1 gap-4 rounded-2xl border border-zinc-200 bg-zinc-50 p-4 sm:grid-cols-2 xl:grid-cols-5">
              <Field label="Nome do cartão">
                <input type="text" placeholder="Ex: Nubank" value={cardForm.name} onChange={(event) => setCardForm({ ...cardForm, name: event.target.value })} className="app-input" required />
              </Field>
              <Field label="Funções" hint="Débito: a compra sai direto de uma conta, sem fatura." className="sm:col-span-2 xl:col-span-4">
                <SegmentedControl items={CARD_FUNCTION_ITEMS} value={cardForm.functions} onChange={(functions) => setCardForm({ ...cardForm, functions })} />
              </Field>
              {cardForm.functions !== 'DEBIT' ? (
                <>
                  <Field label="Vencimento">
                    <input type="number" inputMode="numeric" min="1" max="31" placeholder="Dia" value={cardForm.due_day} onChange={handleDueDayChange} className="app-input" required />
                  </Field>
                  <Field label="Fechamento" hint="Preenchido 7 dias antes; ajuste se precisar.">
                    <input type="number" inputMode="numeric" min="1" max="31" placeholder="Dia" value={cardForm.closing_day} onChange={(event) => setCardForm({ ...cardForm, closing_day: event.target.value })} className="app-input" required />
                  </Field>
                  <Field label="Débito automático" hint="Paga a fatura no vencimento com o saldo da conta.">
                    <select value={cardForm.autopay_account_id} onChange={(event) => setCardForm({ ...cardForm, autopay_account_id: event.target.value })} className="app-input">
                      <option value="">Desligado</option>
                      {accounts.map((account) => (
                        <option key={account.id} value={account.id}>{account.name}</option>
                      ))}
                    </select>
                  </Field>
                </>
              ) : null}
              {cardForm.functions !== 'CREDIT' ? (
                <Field label="Conta do débito" hint="De onde sai a compra no débito.">
                  <select value={cardForm.debit_account_id} onChange={(event) => setCardForm({ ...cardForm, debit_account_id: event.target.value })} className="app-input" required>
                    <option value="">Selecione...</option>
                    {debitAccounts.map((account) => (
                      <option key={account.id} value={account.id}>{account.name}</option>
                    ))}
                  </select>
                </Field>
              ) : null}
              <div className="flex items-end">
                <Button type="submit" loading={saving} className="w-full">Salvar</Button>
              </div>
            </form>
          </Collapsible>
          {cards.length > 0 && !formOpen ? (
            <Link to="/lancamentos/cartoes" className="inline-flex h-10 items-center text-sm font-semibold text-emerald-700 hover:text-emerald-800">
              Ver faturas →
            </Link>
          ) : null}
        </div>
      </div>

      <Sheet
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={editing ? `Editar "${editing.name}"` : ''}
        description="Vencimento e fechamento valem para as próximas compras e para quando cada fatura fecha. As parcelas já lançadas ficam na fatura em que estão. Tirar o crédito desliga o débito automático; com fatura em aberto, não dá."
        footer={(
          <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <Button type="button" variant="secondary" size="lg" onClick={() => setEditing(null)}>Cancelar</Button>
            <Button type="submit" form="card-edit-form" size="lg" loading={saving}>Salvar</Button>
          </div>
        )}
      >
        <form id="card-edit-form" onSubmit={handleSaveEdit} className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Field label="Nome do cartão" className="sm:col-span-3">
            <input type="text" value={editForm.name} onChange={(event) => setEditForm({ ...editForm, name: event.target.value })} className="app-input" required />
          </Field>
          <Field label="Funções" className="sm:col-span-3">
            <SegmentedControl items={CARD_FUNCTION_ITEMS} value={editForm.functions} onChange={(functions) => setEditForm({ ...editForm, functions })} />
          </Field>
          {editForm.functions !== 'DEBIT' ? (
            <>
              <Field label="Vencimento">
                <input type="number" inputMode="numeric" min="1" max="31" value={editForm.due_day} onChange={(event) => setEditForm({ ...editForm, due_day: event.target.value })} className="app-input" required />
              </Field>
              <Field label="Fechamento">
                <input type="number" inputMode="numeric" min="1" max="31" value={editForm.closing_day} onChange={(event) => setEditForm({ ...editForm, closing_day: event.target.value })} className="app-input" required />
              </Field>
            </>
          ) : null}
          {editForm.functions !== 'CREDIT' ? (
            <Field label="Conta do débito" className={editForm.functions === 'DEBIT' ? 'sm:col-span-3' : ''}>
              <select value={editForm.debit_account_id} onChange={(event) => setEditForm({ ...editForm, debit_account_id: event.target.value })} className="app-input" required>
                <option value="">Selecione...</option>
                {editing?.debit_account_id && !debitAccounts.some((account) => account.id === editing.debit_account_id) ? (
                  <option value={editing.debit_account_id}>{accountName(editing.debit_account_id)}</option>
                ) : null}
                {debitAccounts.map((account) => (
                  <option key={account.id} value={account.id}>{account.name}</option>
                ))}
              </select>
            </Field>
          ) : null}
        </form>
      </Sheet>
    </Panel>
  )
}
