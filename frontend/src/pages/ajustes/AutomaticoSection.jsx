import { useState } from 'react'
import { AlertMessage, Badge, Button, EmptyState, ListSkeleton, Panel, PanelHeader } from '../../components/ui'
import { canUndo, decisionDetail, decisionTitle, undoToast } from '../../lib/autoDecisions'
import { reviewApi } from '../../lib/dataApi'
import { formatDateBR } from '../../lib/format'
import { queryErrorMessage, useQuery } from '../../lib/queries'
import { toast } from '../../lib/toast'

const KEY = ['review', 'automatic']

// Decidido sozinho (dono, 2026-11-18: "tudo automatico"): o que o app antes
// perguntava e agora decide por uma regra escrita — a categoria da Pluggy, o
// Revisar que passou do prazo, a ponta so da Corretora, o cambio sem a PTAX do
// dia, o conflito com o banco. Cada uma com "Desfazer"; desfeita, a regra nao
// decide de novo aquele lancamento.
export default function AutomaticoSection() {
  const query = useQuery({ queryKey: KEY, queryFn: () => reviewApi.automatic() })
  const [busyId, setBusyId] = useState('')
  const [error, setError] = useState('')
  const items = query.data?.items || []

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

  return (
    <Panel id="automatico" className="scroll-mt-20 lg:scroll-mt-8">
      <PanelHeader
        title="Decidido sozinho"
        description="O que o app resolveu sem perguntar. Desfazer devolve a linha como era e a regra não volta a mexer nela."
      />
      <div className="p-5">
        {error || query.isError ? (
          <AlertMessage
            message={error || queryErrorMessage(query, 'Não foi possível ler as decisões automáticas.')}
            onDismiss={error ? () => setError('') : undefined}
            className="mb-4"
          />
        ) : null}
        {query.isLoading ? <ListSkeleton rows={3} /> : items.length === 0 ? (
          <EmptyState title="Nada decidido sozinho ainda" message="Quando o app resolver algo por você, aparece aqui." />
        ) : (
          <ul className="divide-y divide-zinc-100">
            {items.map((decision) => (
              <li key={decision.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-zinc-900">{decisionTitle(decision)}</p>
                  <p className="text-sm text-zinc-600">
                    {formatDateBR(decision.created_at?.slice(0, 10))}
                    {decisionDetail(decision) ? ` · ${decisionDetail(decision)}` : ''}
                  </p>
                </div>
                {canUndo(decision) ? (
                  <Button variant="secondary" size="sm" loading={busyId === decision.id} onClick={() => undo(decision)}>
                    Desfazer
                  </Button>
                ) : <Badge>Desfeito</Badge>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Panel>
  )
}
