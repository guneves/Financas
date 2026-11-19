import { useState } from 'react'
import { AlertMessage, Badge, Button } from '../../components/ui'
import { canUndo, decisionDetail, decisionTitle, noUndoLabel, undoToast } from '../../lib/autoDecisions'
import { reviewApi } from '../../lib/dataApi'
import { formatDateBR } from '../../lib/format'
import { toast } from '../../lib/toast'

// As decisoes automaticas (058) com "Desfazer": a lista de Ajustes > "Decidido
// sozinho" e o "Resolvido automaticamente" da Conferencia. O servidor diz o que
// se desfaz aqui (`undoable`); o resto mostra como desfazer.
export default function AutoDecisionList({ items, compact = false }) {
  const [busyId, setBusyId] = useState('')
  const [error, setError] = useState('')

  const undo = async (decision) => {
    setBusyId(decision.id)
    setError('')
    try {
      await reviewApi.undoAutomatic(decision.id)
      toast(undoToast(decision))
    } catch (failure) {
      setError(failure?.message || 'Não foi possível desfazer.')
    } finally {
      setBusyId('')
    }
  }

  const titleClass = compact ? 'text-xs font-semibold text-zinc-700' : 'text-sm font-semibold text-zinc-900'
  const lineClass = compact ? 'text-xs text-zinc-600' : 'text-sm text-zinc-600'
  return (
    <div className="space-y-2">
      <AlertMessage tone="danger" message={error} onDismiss={error ? () => setError('') : undefined} />
      <ul className={compact ? 'space-y-1' : 'divide-y divide-zinc-100'}>
        {items.map((decision) => (
          <li key={decision.id} className={`flex flex-wrap items-center justify-between gap-3 ${compact ? 'py-1' : 'py-3'}`}>
            <div className="min-w-0">
              <p className={titleClass}>{decisionTitle(decision)}</p>
              <p className={lineClass}>
                {formatDateBR(decision.created_at?.slice(0, 10))}
                {decisionDetail(decision) ? ` · ${decisionDetail(decision)}` : ''}
              </p>
            </div>
            {canUndo(decision) ? (
              <Button
                variant="secondary"
                size="sm"
                loading={busyId === decision.id}
                disabled={Boolean(busyId)}
                onClick={() => undo(decision)}
              >
                Desfazer
              </Button>
            ) : <Badge>{noUndoLabel(decision)}</Badge>}
          </li>
        ))}
      </ul>
    </div>
  )
}
