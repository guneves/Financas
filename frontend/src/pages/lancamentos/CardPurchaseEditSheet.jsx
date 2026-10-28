import { useEffect, useState } from 'react'
import { ccExpensesApi, transactionsApi } from '../../lib/dataApi'
import { formatCurrency } from '../../lib/format'
import { toast } from '../../lib/toast'
import { AlertMessage, Button, Field, Sheet } from '../../components/ui'
import { purchaseEditPayload } from '../../lib/cardPurchaseEdit'

// Editar uma compra no cartao: categoria e descricao. `target.kind` 'card'
// (credito ou estorno: todas as parcelas juntas, PATCH /api/cc-expenses/purchases)
// ou 'debit' (a despesa na conta do cartao, PATCH /api/transactions). Valor,
// data e parcelas decidem as faturas: para muda-los, exclua e lance de novo.
export default function CardPurchaseEditSheet({ target, categoryOptions, onClose, onSaved }) {
  const [form, setForm] = useState({ description: '', category_id: '' })
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!target) return
    setForm({ description: target.description || '', category_id: target.category_id || '' })
    setError('')
  }, [target])

  const options = categoryOptions || []
  const knownCategory = options.some((category) => category.id === (target?.category_id || ''))

  const handleSave = async () => {
    const { payload, error: message } = purchaseEditPayload(target, form)
    if (message) {
      setError(message)
      return
    }
    if (!payload) {
      onClose()
      return
    }
    setSaving(true)
    setError('')
    try {
      if (target.kind === 'debit') await transactionsApi.update(target.id, payload)
      else await ccExpensesApi.updatePurchase(target.id, payload)
      toast('Compra atualizada.')
      onSaved?.()
      onClose()
    } catch (err) {
      setError(err.message || 'Não foi possível salvar a compra.')
    } finally {
      setSaving(false)
    }
  }

  // Em Cartoes o valor e o da parcela desta fatura; no Extrato, o total da compra.
  const installments = !(target?.installmentTotal > 1) ? ''
    : target.installmentCurrent ? ` · parcela ${target.installmentCurrent}/${target.installmentTotal}`
      : ` em ${target.installmentTotal} parcelas`
  return (
    <Sheet
      open={Boolean(target)}
      onClose={onClose}
      title={target?.refund ? 'Editar estorno' : 'Editar compra'}
      description={target ? `${target.cardName ? `${target.cardName} · ` : ''}${formatCurrency(target.amount)}${installments}` : ''}
      footer={(
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button type="button" loading={saving} onClick={handleSave}>Salvar</Button>
        </div>
      )}
    >
      <div className="space-y-4">
        <AlertMessage tone="danger" message={error} onDismiss={() => setError('')} />
        <Field label="Descrição">
          <input
            type="text"
            value={form.description}
            onChange={(event) => setForm({ ...form, description: event.target.value })}
            className="app-input"
            maxLength={500}
          />
        </Field>
        <Field label="Categoria" hint={target?.kind === 'card' && target?.installmentTotal > 1 ? 'Vale para todas as parcelas, inclusive as já pagas.' : undefined}>
          <select
            value={form.category_id}
            onChange={(event) => setForm({ ...form, category_id: event.target.value })}
            className="app-select"
          >
            {/* A categoria que a compra ja tem, quando ela nao esta na lista (arquivada). */}
            {!knownCategory ? <option value={target?.category_id || ''}>{target?.category || 'Sem categoria'}</option> : null}
            {options.map((category) => (
              <option key={category.id} value={category.id}>{category.label}</option>
            ))}
          </select>
        </Field>
        <p className="text-xs text-zinc-500">Valor, data e parcelas não mudam aqui: para corrigi-los, exclua a compra e lance de novo.</p>
      </div>
    </Sheet>
  )
}
