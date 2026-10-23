import { useEffect, useState } from 'react'
import { ccExpensesApi } from '../../lib/dataApi'
import { formatCurrency, getLocalDateString } from '../../lib/format'
import { parseMoneyInput } from '../../lib/monthlyPlan'
import { newClientId } from '../../lib/outboxRules'
import { refundPrefillAmount } from '../../lib/cardPurchase'
import { toast } from '../../lib/toast'
import { AlertMessage, Button, Field, Sheet } from '../../components/ui'

const AMOUNT_INPUT = 'app-input py-3 text-2xl font-bold tabular'

const emptyForm = { card_id: '', amount: '', purchase_date: '', description: '' }

// Estorno no cartao (033, POST /api/cc-expenses/refunds): um credito que abate
// a fatura. Aberto pelo menu de uma compra (ja com cartao, valor e categoria
// dela) ou pelo botao "Estorno" do topo. O servidor escolhe a fatura: a da
// data, ou a seguinte em aberto se essa ja foi paga.
export default function CardRefundSheet({ target, cards = [], onClose, onSaved }) {
  const [form, setForm] = useState(emptyForm)
  const [clientId, setClientId] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const purchase = target?.purchase || null

  useEffect(() => {
    if (!target) return undefined
    const amountText = (value) => String(value).replace('.', ',')
    setForm({
      card_id: purchase?.card_id || cards[0]?.id || '',
      amount: purchase ? amountText(refundPrefillAmount(purchase, [])) : '',
      purchase_date: getLocalDateString(),
      description: purchase ? `Estorno · ${purchase.description}` : '',
    })
    setClientId(newClientId())
    setError('')
    // Parcelada, o total e a soma das parcelas (a primeira leva o centavo da
    // divisao); ate a resposta fica a estimativa, e o que o dono digitou fica.
    if (!purchase || (purchase.installmentTotal || 1) <= 1) return undefined
    let cancelled = false
    const estimate = amountText(refundPrefillAmount(purchase, []))
    ccExpensesApi.candidates({ id: purchase.id })
      .then((candidates) => {
        if (cancelled) return
        const total = amountText(refundPrefillAmount(purchase, candidates))
        setForm((current) => (current.amount === estimate ? { ...current, amount: total } : current))
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [target]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleSave = async (event) => {
    event?.preventDefault()
    const amount = parseMoneyInput(form.amount)
    if (!Number.isFinite(amount) || amount <= 0) {
      setError('Informe o valor do estorno.')
      return
    }
    setSaving(true)
    setError('')
    try {
      const created = await ccExpensesApi.createRefund({
        card_id: form.card_id,
        amount,
        purchase_date: form.purchase_date,
        description: form.description.trim(),
        category: purchase?.category_raw || undefined,
        refund_of: purchase?.id || undefined,
        client_id: clientId,
      })
      const invoice = created ? ` na fatura ${String(created.invoice_month).padStart(2, '0')}/${created.invoice_year}` : ''
      toast(`Estorno de ${formatCurrency(amount)} lançado${invoice}.`)
      onSaved?.()
      onClose()
    } catch (err) {
      setError(err.message || 'Não foi possível registrar o estorno.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Sheet
      open={Boolean(target)}
      onClose={onClose}
      title="Registrar estorno"
      description={purchase ? purchase.description : 'Um crédito no cartão, que abate a fatura.'}
      footer={(
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button type="button" loading={saving} onClick={handleSave}>Lançar estorno</Button>
        </div>
      )}
    >
      <form id="card-refund-form" onSubmit={handleSave} className="space-y-4">
        <AlertMessage tone="danger" message={error} onDismiss={() => setError('')} />
        <Field label="Valor do estorno">
          <input type="text" inputMode="decimal" placeholder="0,00" value={form.amount} onChange={(event) => setForm({ ...form, amount: event.target.value })} className={AMOUNT_INPUT} required autoFocus />
        </Field>
        <Field label="Descrição">
          <input type="text" placeholder="Ex: Estorno da loja" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} className="app-input" required />
        </Field>
        <Field label="Cartão">
          <select value={form.card_id} onChange={(event) => setForm({ ...form, card_id: event.target.value })} className="app-select" required disabled={Boolean(purchase)}>
            {cards.map((card) => <option key={card.id} value={card.id}>{card.name}</option>)}
          </select>
        </Field>
        <Field label="Data do estorno" hint="Entra na fatura desta data; se ela já foi paga, na próxima em aberto.">
          <input type="date" value={form.purchase_date} onChange={(event) => setForm({ ...form, purchase_date: event.target.value })} className="app-input" required />
        </Field>
      </form>
    </Sheet>
  )
}
