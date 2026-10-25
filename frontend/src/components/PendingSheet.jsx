import { useState } from 'react'
import { CloudOff, Pencil, RefreshCw, Trash2 } from 'lucide-react'
import { confirmAction } from '../lib/confirm'
import { useServerReachable } from '../lib/connection'
import { formatCurrency, formatDateBR } from '../lib/format'
import { discardItem, flush, useOutbox } from '../lib/outbox'
import { KIND_LABELS, NEEDS_ATTENTION, isEditableKind, itemAmount, itemDate, itemTitle } from '../lib/outboxRules'
import { toast } from '../lib/toast'
import { AlertMessage, Badge, Button, EmptyState, Menu, Sheet } from './ui'

// "Pendentes": a fila de envio (lib/outbox.js) — o que foi lancado sem o
// servidor e ainda nao chegou la. Mora no Layout, como o "+ Novo".
export default function PendingSheet({ open, onClose, onEdit }) {
  const items = useOutbox()
  const reachable = useServerReachable()
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState('')

  const syncNow = async () => {
    setSyncing(true)
    setError('')
    try {
      // "Sincronizar agora" tenta tambem os recusados: o dono pode ter
      // resolvido o motivo no PC (uma categoria criada, uma conta reativada).
      const summary = await flush({ retryAttention: true })
      if (summary.stopped === 'login') setError('Entre novamente para enviar os lançamentos pendentes.')
      else if (summary.stopped === 'offline') setError('O servidor não respondeu. Os lançamentos continuam guardados neste aparelho.')
      else if (summary.attention) setError('O servidor recusou um ou mais lançamentos. Veja o motivo em cada um.')
      if (summary.sent) toast(summary.sent === 1 ? '1 lançamento enviado.' : `${summary.sent} lançamentos enviados.`)
    } catch (syncError) {
      setError(syncError.message || 'Não foi possível sincronizar.')
    } finally {
      setSyncing(false)
    }
  }

  const discard = async (item) => {
    const confirmed = await confirmAction({
      title: 'Descartar o lançamento pendente?',
      message: `${KIND_LABELS[item.kind]} de ${formatCurrency(itemAmount(item))} ainda não foi enviada. Descartar apaga do aparelho; ela não chega ao servidor.`,
      confirmLabel: 'Descartar',
    })
    if (confirmed) await discardItem(item.client_id)
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="Pendentes"
      description="Lançamentos guardados neste aparelho, à espera do servidor."
      footer={items.length ? (
        <div className="flex gap-2 sm:justify-end">
          <Button type="button" variant="secondary" size="lg" onClick={onClose} className="flex-1 sm:flex-none">Fechar</Button>
          <Button type="button" size="lg" icon={RefreshCw} loading={syncing} onClick={syncNow} className="flex-1 sm:flex-none">Sincronizar agora</Button>
        </div>
      ) : null}
    >
      <div className="space-y-3">
        <AlertMessage tone="warning" message={error} onDismiss={() => setError('')} />
        {!reachable && !error ? (
          <AlertMessage tone="info" message="Sem conexão com o servidor. Novos lançamentos ficam guardados aqui; o resto do app volta com a conexão." />
        ) : null}
        {items.length === 0 ? (
          <EmptyState
            icon={CloudOff}
            title="Nada pendente"
            message="Tudo o que foi lançado neste aparelho já chegou ao servidor."
            className="min-h-40"
          />
        ) : (
          <ul className="divide-y divide-zinc-100">
            {items.map((item) => (
              <li key={item.client_id} className="flex items-start gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate text-sm font-semibold text-zinc-950">
                      {itemTitle(item)}
                    </span>
                    <Badge tone={item.status === NEEDS_ATTENTION ? 'warning' : 'neutral'}>
                      {item.status === NEEDS_ATTENTION ? 'Recusado' : 'Pendente'}
                    </Badge>
                  </div>
                  <p className="mt-0.5 text-xs text-zinc-500">
                    {KIND_LABELS[item.kind]} · {formatDateBR(itemDate(item))}
                    {item.kind === 'CARD' && Number(item.payload.installments) > 1 ? ` · ${item.payload.installments}x` : ''}
                  </p>
                  {item.last_error ? <p className="mt-1 text-xs font-medium text-amber-700">{item.last_error}</p> : null}
                </div>
                <span className="num shrink-0 text-sm font-semibold text-zinc-950">{formatCurrency(itemAmount(item))}</span>
                <Menu
                  items={[
                    // Operacao e provento (Investimentos, no APK) nao tem formulario aqui.
                    ...(isEditableKind(item.kind) ? [{ label: 'Corrigir', icon: Pencil, onSelect: () => onEdit(item) }] : []),
                    { label: 'Descartar', icon: Trash2, tone: 'danger', onSelect: () => discard(item) },
                  ]}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
    </Sheet>
  )
}
