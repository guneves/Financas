import { useEffect, useState } from 'react'
import { ccExpensesApi } from '../../lib/dataApi'
import { formatCurrency } from '../../lib/format'
import { othersAmount, shareFormError, shareFormFrom, sharePayload } from '../../lib/sharing'
import { toast } from '../../lib/toast'
import ShareFields from '../../components/ShareFields'
import { AlertMessage, Button, Sheet } from '../../components/ui'

const toCents = (value) => Math.round((Number(value) || 0) * 100)

// "De quem é?" de uma compra no cartao (032) — a unica coisa que se edita
// numa compra. Vale para a compra inteira: o servidor reparte a parte dos
// outros pelas parcelas. A tela de Cartoes so tem as parcelas em aberto, entao
// o total e a divisao atual vem de todas as parcelas (candidates).
export default function CardShareSheet({ purchase, onClose, onSaved }) {
  const [rows, setRows] = useState(null)
  const [form, setForm] = useState(shareFormFrom(null))
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!purchase) return undefined
    let cancelled = false
    setRows(null)
    setError('')
    ccExpensesApi.candidates({
      card_id: purchase.card_id,
      description: purchase.description,
      purchase_date: purchase.purchase_date,
      category: purchase.category_raw ?? purchase.category,
    }).then((items) => {
      if (cancelled) return
      const list = items || []
      setRows(list)
      const first = list.find((row) => row.share_mode) || list[0] || null
      const othersTotal = list.reduce((acc, row) => acc + toCents(othersAmount(row)), 0) / 100
      setForm(shareFormFrom(first && first.share_mode === 'SPLIT'
        ? { ...first, share_others_amount: othersTotal }
        : first))
    }).catch((err) => {
      if (!cancelled) setError(err.message || 'Não foi possível carregar a compra.')
    })
    return () => { cancelled = true }
  }, [purchase])

  const total = (rows || []).reduce((acc, row) => acc + toCents(row.amount), 0) / 100

  const handleSave = async () => {
    const message = shareFormError(form, total)
    if (message) {
      setError(message)
      return
    }
    setSaving(true)
    setError('')
    try {
      await ccExpensesApi.updateShare(purchase.id, sharePayload(form))
      toast(form.share_mode ? 'Compra marcada.' : 'Compra voltou a ser só sua.')
      onSaved?.()
      onClose()
    } catch (err) {
      setError(err.message || 'Não foi possível salvar.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Sheet
      open={Boolean(purchase)}
      onClose={onClose}
      title="De quem é esta compra?"
      description={purchase
        ? `${purchase.description}${rows ? ` · ${formatCurrency(total)}${rows.length > 1 ? ` em ${rows.length} parcelas` : ''}` : ''}`
        : ''}
      footer={(
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button type="button" loading={saving} disabled={!rows} onClick={handleSave}>Salvar</Button>
        </div>
      )}
    >
      <div className="space-y-4">
        <AlertMessage tone="danger" message={error} onDismiss={() => setError('')} />
        <ShareFields form={form} onChange={setForm} disabled={!rows || saving} />
        <p className="text-xs text-zinc-500">
          A fatura não muda. A parte da outra pessoa fica fora de Despesas por categoria e do orçamento,
          aparece à parte no Fluxo de caixa e fica em A receber até você marcar que ela pagou.
        </p>
      </div>
    </Sheet>
  )
}
