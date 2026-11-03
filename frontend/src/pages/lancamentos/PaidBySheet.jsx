import { useEffect, useMemo, useState } from 'react'
import { receivablesApi } from '../../lib/dataApi'
import { formatCurrency, formatDateBR } from '../../lib/format'
import { paymentChoices, settlePayload, suggestedPayment } from '../../lib/sharing'
import { toast } from '../../lib/toast'
import { AlertMessage, Button, ListSkeleton, Sheet, cx } from '../../components/ui'

// "Com que entrada pagou?" (052): ao marcar como pago, ou ao trocar depois, o dono
// diz qual receita pagou estes itens. A parte dos outros sai dessa receita, no mes
// dela; "Nenhuma" abate a receita do mes em que marcou.
export default function PaidBySheet({ items, onClose }) {
  const open = Boolean(items?.length)
  const [candidates, setCandidates] = useState(null)
  const [choice, setChoice] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const total = useMemo(() => (items || []).reduce((acc, item) => acc + Math.round(Number(item.others_amount || 0) * 100), 0) / 100, [items])
  const choices = useMemo(() => paymentChoices(candidates || [], items || []), [candidates, items])
  const editing = (items || []).some((item) => item.settled_at)

  useEffect(() => {
    if (!open) return undefined
    let cancelled = false
    setCandidates(null)
    setError('')
    const since = items.map((item) => item.date || '').sort()[0]
    receivablesApi.incomes(since)
      .then((rows) => {
        if (cancelled) return
        setCandidates(rows)
        setChoice(suggestedPayment(paymentChoices(rows, items), items))
      })
      .catch((err) => { if (!cancelled) { setCandidates([]); setError(err.message || 'Não foi possível carregar as entradas.') } })
    return () => { cancelled = true }
  }, [open, items])

  const save = async () => {
    setSaving(true)
    setError('')
    try {
      await receivablesApi.settle(settlePayload(items, true, choice || null))
      toast(choice ? 'Pago. A entrada deixou de contar como receita nesse valor.' : 'Marcado como pago.')
      onClose()
    } catch (err) {
      setError(err.message || 'Não foi possível atualizar.')
    } finally {
      setSaving(false)
    }
  }

  const option = (id, title, detail, extra = '') => (
    <button
      key={id || 'none'}
      type="button"
      onClick={() => setChoice(id)}
      aria-pressed={choice === id}
      className={cx(
        'flex min-h-[44px] w-full items-center gap-3 rounded-2xl border px-4 py-2.5 text-left transition',
        choice === id ? 'border-emerald-500 bg-emerald-50' : 'border-zinc-200 bg-white hover:bg-zinc-50',
      )}
    >
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium text-zinc-900">{title}</span>
        <span className="block truncate text-xs text-zinc-500">{detail}</span>
      </span>
      {extra ? <span className="num whitespace-nowrap font-semibold text-zinc-950">{extra}</span> : null}
    </button>
  )

  return (
    <Sheet
      open={open}
      onClose={saving ? () => {} : onClose}
      title={editing ? 'Trocar a entrada' : 'Com que entrada pagou?'}
      description={open ? `${items[0].person} · ${formatCurrency(total)}. A entrada escolhida deixa de contar como receita nesse valor.` : ''}
      footer={(
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose} disabled={saving}>Cancelar</Button>
          <Button type="button" loading={saving} disabled={candidates === null} onClick={save}>{editing ? 'Salvar' : 'Marcar como pago'}</Button>
        </div>
      )}
    >
      <div className="space-y-2">
        <AlertMessage tone="danger" message={error} onDismiss={() => setError('')} />
        {candidates === null ? <ListSkeleton rows={3} /> : (
          <>
            {choices.map((income) => option(
              income.id,
              income.description,
              `${formatDateBR(income.date)}${income.room < income.amount ? ` · livre ${formatCurrency(income.room)}` : ''}`,
              formatCurrency(income.amount),
            ))}
            {option('', 'Nenhuma entrada', 'Abate da receita do mês em que você marcar')}
          </>
        )}
      </div>
    </Sheet>
  )
}
