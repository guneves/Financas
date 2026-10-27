import { useState } from 'react'
import { AlertMessage, Panel, PanelHeader } from '../../components/ui'
import { inboxApi } from '../../lib/dataApi'
import { queryErrorMessage, useQuery } from '../../lib/queries'
import { toast } from '../../lib/toast'

// Avisos do celular: "Gravar sozinho" (045, ligado por padrão: o aviso vira
// lançamento na hora e você só revisa no Extrato; desligado, espera em
// Aprovar) e "Sempre perguntar a conta/cartão" (só vale com ele desligado).
// Vale em todo aparelho — fica no servidor.
export default function AprovarSection() {
  const settingsQuery = useQuery({ queryKey: ['aprovar', 'ajustes'], queryFn: () => inboxApi.settings() })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const alwaysAsk = Boolean(settingsQuery.data?.always_ask)
  const autoRecord = settingsQuery.data?.auto_record !== false

  const save = async (payload, message) => {
    setSaving(true)
    setError('')
    try {
      await inboxApi.updateSettings(payload)
      toast(message)
    } catch (toggleError) {
      setError(toggleError.message || 'Não foi possível salvar.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Panel id="aprovar" className="scroll-mt-20 lg:scroll-mt-8">
      <PanelHeader
        title="Avisos do celular"
        description="Os avisos dos bancos e do Flash que o celular lê."
      />
      <div className="space-y-3 p-5">
        {settingsQuery.isError ? <AlertMessage message={queryErrorMessage(settingsQuery, 'Não foi possível ler os ajustes de Aprovar.')} /> : null}
        {error ? <AlertMessage message={error} onDismiss={() => setError('')} /> : null}
        <label className="flex items-start gap-3">
          <input
            type="checkbox"
            checked={autoRecord}
            disabled={saving || settingsQuery.isLoading}
            onChange={(event) => save(
              { auto_record: event.target.checked },
              event.target.checked ? 'Os avisos viram lançamento na hora; revise no Extrato.' : 'Os avisos voltam a esperar em Aprovar.',
            )}
            className="mt-0.5 h-5 w-5 shrink-0 accent-emerald-600"
          />
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-zinc-900">Gravar sozinho</span>
            <span className="block text-sm text-zinc-600">
              Cada aviso vira lançamento na hora, com a categoria sugerida; no Extrato você só confirma que é seu. O Open Finance confere depois e corrige data e conta do que você ainda não revisou.
            </span>
          </span>
        </label>
        <label className="flex items-start gap-3">
          <input
            type="checkbox"
            checked={alwaysAsk}
            disabled={saving || settingsQuery.isLoading || autoRecord}
            onChange={(event) => save(
              { always_ask: event.target.checked },
              event.target.checked ? 'Aprovar vai pedir a conta/cartão de todo item.' : 'Aprovar volta a usar as escolhas lembradas.',
            )}
            className="mt-0.5 h-5 w-5 shrink-0 accent-emerald-600"
          />
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-zinc-900">Sempre perguntar a conta/cartão</span>
            <span className="block text-sm text-zinc-600">
              Com &quot;Gravar sozinho&quot; desligado: todo item em Aprovar pede que você confirme para onde vai, mesmo o que o app já lembra.
            </span>
          </span>
        </label>
      </div>
    </Panel>
  )
}
