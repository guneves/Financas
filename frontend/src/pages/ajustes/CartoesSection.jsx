import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { CreditCard, Plus, Trash2 } from 'lucide-react'
import { accountsApi, creditCardsApi } from '../../lib/dataApi'
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
} from '../../components/ui'

const emptyCardForm = () => ({ name: '', due_day: '', closing_day: '', autopay_account_id: '' })

// Cartoes de credito: lista, excluir e criar. Veio de Transactions.jsx.
// As compras e faturas continuam em Lancamentos > Cartoes.
//
// Debito automatico: com uma conta escolhida, cada fatura e paga sozinha no
// dia do vencimento, debitando essa conta. So vale para faturas que vencem a
// partir do dia em que foi ligado; as anteriores seguem para pagamento manual.
export default function CartoesSection({ refreshKey = 0 }) {
  const [cards, setCards] = useState([])
  const [accounts, setAccounts] = useState([])
  const [savingAutopayId, setSavingAutopayId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [cardForm, setCardForm] = useState(emptyCardForm)

  const fetchCards = async () => {
    try {
      const [data, accountData] = await Promise.all([creditCardsApi.list(), accountsApi.list()])
      setCards(data || [])
      setAccounts(accountData || [])
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível carregar os cartões.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchCards()
  }, [refreshKey])

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
    const dueDay = Number(cardForm.due_day)
    const closingDay = Number(cardForm.closing_day)
    if (!cardForm.name.trim() || !Number.isInteger(dueDay) || !Number.isInteger(closingDay)) {
      setError('Preencha os dados do cartão corretamente.')
      return
    }

    setSaving(true)
    setError('')
    setNotice('')
    try {
      await creditCardsApi.create({
        name: cardForm.name,
        due_day: dueDay,
        closing_day: closingDay,
        autopay_account_id: cardForm.autopay_account_id || null,
      })
      await fetchCards()
      setNotice(`Cartão "${cardForm.name}" criado.`)
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
    setNotice('')
    try {
      await creditCardsApi.setAutopay(card.id, accountId)
      await fetchCards()
      const account = accounts.find((item) => item.id === accountId)
      setNotice(account
        ? `Débito automático do "${card.name}" ligado: a fatura será paga no vencimento, dia ${card.due_day}, com saldo de ${account.name}.`
        : `Débito automático do "${card.name}" desligado.`)
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível alterar o débito automático.')
    } finally {
      setSavingAutopayId(null)
    }
  }

  const handleDeleteCard = async (id, name) => {
    if (!window.confirm(`ATENÇÃO: Deseja realmente excluir o cartão "${name}"?\nIsso apagará TODAS as faturas vinculadas a ele. Esta ação não pode ser desfeita.`)) return

    setError('')
    setNotice('')
    try {
      await creditCardsApi.remove(id)
      await fetchCards()
      setNotice(`Cartão "${name}" excluído.`)
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível excluir o cartão.')
    }
  }

  return (
    <Panel id="cartoes" className="scroll-mt-20 lg:scroll-mt-8">
      <PanelHeader
        title="Cartões"
        description="Vencimento e fechamento de cada cartão. Compras e faturas ficam em Lançamentos › Cartões."
        actions={<Badge>{cards.length} cartão(ões)</Badge>}
      />

      <div className="space-y-4 p-5">
        <AlertMessage message={error} onDismiss={() => setError('')} />
        <AlertMessage tone="success" message={notice} onDismiss={() => setNotice('')} />

        {loading ? (
          <p className="py-6 text-center text-sm text-zinc-600">Carregando...</p>
        ) : cards.length > 0 ? (
          <div className="divide-y divide-zinc-100 rounded-lg border border-zinc-200">
            {cards.map((card) => (
              <div key={card.id} className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="truncate font-medium text-zinc-900">{card.name}</p>
                    {card.autopay_account_id ? <Badge tone="success">Débito automático</Badge> : null}
                  </div>
                  <p className="text-sm text-zinc-600">Vence dia {card.due_day} • Fecha dia {card.closing_day}</p>
                </div>
                <div className="flex items-center gap-2">
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
                  <IconButton label="Excluir cartão" icon={Trash2} variant="danger" onClick={() => handleDeleteCard(card.id, card.name)} />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState icon={CreditCard} title="Nenhum cartão" message="Cadastre um cartão para lançar compras no crédito." className="min-h-40" />
        )}

        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <Collapsible label="Novo cartão" icon={Plus} open={formOpen} onOpenChange={setFormOpen} className="min-w-0 flex-1">
            <form onSubmit={handleCreateCard} className="grid grid-cols-1 gap-4 rounded-lg border border-zinc-200 bg-zinc-50 p-4 sm:grid-cols-2 xl:grid-cols-5">
              <Field label="Nome do cartão">
                <input type="text" placeholder="Ex: Nubank" value={cardForm.name} onChange={(event) => setCardForm({ ...cardForm, name: event.target.value })} className="app-input" required />
              </Field>
              <Field label="Vencimento">
                <input type="number" min="1" max="31" placeholder="Dia" value={cardForm.due_day} onChange={handleDueDayChange} className="app-input" required />
              </Field>
              <Field label="Fechamento" hint="Preenchido 7 dias antes; ajuste se precisar.">
                <input type="number" min="1" max="31" placeholder="Dia" value={cardForm.closing_day} onChange={(event) => setCardForm({ ...cardForm, closing_day: event.target.value })} className="app-input" required />
              </Field>
              <Field label="Débito automático" hint="Paga a fatura no vencimento com o saldo da conta.">
                <select value={cardForm.autopay_account_id} onChange={(event) => setCardForm({ ...cardForm, autopay_account_id: event.target.value })} className="app-input">
                  <option value="">Desligado</option>
                  {accounts.map((account) => (
                    <option key={account.id} value={account.id}>{account.name}</option>
                  ))}
                </select>
              </Field>
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
    </Panel>
  )
}
