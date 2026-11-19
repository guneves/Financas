import { useState } from 'react'
import { AlertMessage, ListSkeleton, Panel, PanelHeader, SegmentedControl } from '../../components/ui'
import { REVIEW_AUTO_HINT, reviewAutoDays, reviewAutoToast, reviewDayItems } from '../../lib/autoDecisions'
import { BANK_NOTIFICATIONS_HINT, bankNotificationsOn, bankNotificationsToast } from '../../lib/bankNotifications'
import { inboxApi } from '../../lib/dataApi'
import { queryClient, queryErrorMessage, useQuery } from '../../lib/queries'
import { toast } from '../../lib/toast'

const SETTINGS_KEY = ['inbox', 'settings']

// Avisos do celular (Fase 2): o interruptor bank_notifications. Ligado, o aviso
// do Itau, BB e BTG grava na hora e a Pluggy confere depois; desligado, so o
// Flash. O leitor de notificacoes mora no APK (Ajustes > Notificacoes do celular).
// E o prazo do Revisar (review_auto_days): depois dele a linha sai sozinha.
export default function AvisosSection() {
  const settingsQuery = useQuery({ queryKey: SETTINGS_KEY, queryFn: () => inboxApi.settings() })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const on = bankNotificationsOn(settingsQuery.data)

  const days = reviewAutoDays(settingsQuery.data)

  const update = async (payload, message, failureMessage) => {
    setBusy(true)
    setError('')
    try {
      const body = await inboxApi.updateSettings(payload)
      queryClient.setQueryData(SETTINGS_KEY, body)
      toast(message(body))
    } catch (failure) {
      setError(failure?.message || failureMessage)
    } finally {
      setBusy(false)
    }
  }

  const save = (value) => update(
    { bank_notifications: value }, (body) => bankNotificationsToast(bankNotificationsOn(body)),
    'Não foi possível salvar os avisos dos bancos.',
  )

  // Auto-confirmar o Revisar (automation-prompt 1.2): review_auto_days.
  const saveDays = (value) => {
    if (busy || value === days) return
    update(
      { review_auto_days: value }, (body) => reviewAutoToast(reviewAutoDays(body)),
      'Não foi possível salvar o prazo do Revisar.',
    )
  }

  return (
    <Panel id="avisos" className="scroll-mt-20 lg:scroll-mt-8">
      <PanelHeader title="Avisos do celular" description="O que o aviso do celular grava na hora. A Pluggy continua sendo o registro." />
      <div className="space-y-4 p-5">
        {error || settingsQuery.isError ? (
          <AlertMessage
            message={error || queryErrorMessage(settingsQuery, 'Não foi possível ler os avisos do celular.')}
            onDismiss={error ? () => setError('') : undefined}
          />
        ) : null}
        {settingsQuery.isLoading ? <ListSkeleton rows={1} /> : (
          <label className="flex items-start gap-3">
            <input
              type="checkbox"
              checked={on}
              disabled={busy || !settingsQuery.data}
              onChange={(event) => save(event.target.checked)}
              className="mt-0.5 h-5 w-5 shrink-0 accent-emerald-600"
            />
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-zinc-900">Avisos dos bancos</span>
              <span className="block text-sm text-zinc-600">{BANK_NOTIFICATIONS_HINT}</span>
            </span>
          </label>
        )}
        {settingsQuery.isLoading ? null : (
          <div className="space-y-2">
            <span className="block text-sm font-semibold text-zinc-900">Revisar sai sozinho depois de</span>
            <SegmentedControl items={reviewDayItems(days)} value={days} onChange={saveDays} />
            <span className="block text-sm text-zinc-600">{REVIEW_AUTO_HINT}</span>
          </div>
        )}
      </div>
    </Panel>
  )
}
