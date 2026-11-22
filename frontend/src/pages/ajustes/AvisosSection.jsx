import { useState } from 'react'
import { AlertMessage, ListSkeleton, Panel, PanelHeader } from '../../components/ui'
import { BANK_NOTIFICATIONS_HINT, bankNotificationsOn, bankNotificationsToast } from '../../lib/bankNotifications'
import { inboxApi } from '../../lib/dataApi'
import { queryClient, queryErrorMessage, useQuery } from '../../lib/queries'
import { toast } from '../../lib/toast'

const SETTINGS_KEY = ['inbox', 'settings']

// Avisos do celular (Fase 2): o interruptor bank_notifications. Ligado, o aviso
// do Itau, BB e BTG grava na hora e a Pluggy confere depois; desligado, so o
// Flash. O leitor de notificacoes mora no APK (Ajustes > Notificacoes do celular).
export default function AvisosSection() {
  const settingsQuery = useQuery({ queryKey: SETTINGS_KEY, queryFn: () => inboxApi.settings() })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const on = bankNotificationsOn(settingsQuery.data)

  const save = async (value) => {
    setBusy(true)
    setError('')
    try {
      const body = await inboxApi.updateSettings({ bank_notifications: value })
      queryClient.setQueryData(SETTINGS_KEY, body)
      toast(bankNotificationsToast(bankNotificationsOn(body)))
    } catch (failure) {
      setError(failure?.message || 'Não foi possível salvar os avisos dos bancos.')
    } finally {
      setBusy(false)
    }
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
      </div>
    </Panel>
  )
}
