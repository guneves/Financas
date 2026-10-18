import { useState } from 'react'
import { AlertMessage, Panel, PanelHeader } from '../../components/ui'
import { inboxApi } from '../../lib/dataApi'
import { queryErrorMessage, useQuery } from '../../lib/queries'
import { toast } from '../../lib/toast'

// Aprovar: "Sempre perguntar a conta/cartão" (desligado por padrão). Vale em
// todo aparelho — fica no servidor, que decide o que está pronto para "Aprovar
// prontos".
export default function AprovarSection() {
  const settingsQuery = useQuery({ queryKey: ['aprovar', 'ajustes'], queryFn: () => inboxApi.settings() })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const alwaysAsk = Boolean(settingsQuery.data?.always_ask)

  const toggle = async (value) => {
    setSaving(true)
    setError('')
    try {
      await inboxApi.updateSettings({ always_ask: value })
      toast(value ? 'Aprovar vai pedir a conta/cartão de todo item.' : 'Aprovar volta a usar as escolhas lembradas.')
    } catch (toggleError) {
      setError(toggleError.message || 'Não foi possível salvar.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Panel id="aprovar" className="scroll-mt-20 lg:scroll-mt-8">
      <PanelHeader
        title="Aprovar"
        description="Os avisos dos bancos que esperam você em Lançamentos › Aprovar."
      />
      <div className="space-y-3 p-5">
        {settingsQuery.isError ? <AlertMessage message={queryErrorMessage(settingsQuery, 'Não foi possível ler os ajustes de Aprovar.')} /> : null}
        {error ? <AlertMessage message={error} onDismiss={() => setError('')} /> : null}
        <label className="flex items-start gap-3">
          <input
            type="checkbox"
            checked={alwaysAsk}
            disabled={saving || settingsQuery.isLoading}
            onChange={(event) => toggle(event.target.checked)}
            className="mt-0.5 h-5 w-5 shrink-0 accent-emerald-600"
          />
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-zinc-900">Sempre perguntar a conta/cartão</span>
            <span className="block text-sm text-zinc-600">
              Todo item pede que você confirme para onde vai, mesmo o que o app já lembra. &quot;Aprovar prontos&quot; não leva nenhum: aprove um a um.
            </span>
          </span>
        </label>
      </div>
    </Panel>
  )
}
