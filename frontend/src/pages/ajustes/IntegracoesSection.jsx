import { useState } from 'react'
import { Activity, RefreshCw } from 'lucide-react'
import { systemApi } from '../../lib/dataApi'
import { AlertMessage, Badge, Button, ListSkeleton, Panel, PanelHeader } from '../../components/ui'
import { formatDateBR, getLocalDateString } from '../../lib/format'
import { queryClient, queryErrorMessage, useQuery } from '../../lib/queries'

const STATUS = {
  ok: { label: 'Funcionando', tone: 'success' },
  error: { label: 'Com falha', tone: 'danger' },
  stale: { label: 'Atrasado', tone: 'warning' },
  not_configured: { label: 'Não configurado', tone: 'neutral' },
  unavailable: { label: 'Indisponível', tone: 'neutral' },
}

const OVERALL = {
  ok: { text: 'Cotações e índices chegando normalmente.', tone: 'success' },
  degraded: { text: 'Uma integração falhou; o resto segue funcionando.', tone: 'warning' },
  down: { text: 'Nenhum provedor de cotação respondeu: a carteira fica com os últimos preços salvos.', tone: 'danger' },
}

function whenLabel(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  const time = date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
  return `${formatDateBR(getLocalDateString(date))} ${time}`
}

// Integracoes: teste ativo de yfinance, brapi, BCB e Pluggy (GET /api/health/integrations).
// O backend guarda o resultado por 10 minutos; "Verificar agora" refaz.
export default function IntegracoesSection() {
  const [refreshing, setRefreshing] = useState(false)
  const [refreshError, setRefreshError] = useState('')
  const healthQuery = useQuery({
    queryKey: ['integracoes'],
    queryFn: () => systemApi.integrations(),
    staleTime: 5 * 60_000,
  })
  const data = healthQuery.data
  const overall = data ? OVERALL[data.status] || OVERALL.degraded : null

  const handleRefresh = async () => {
    setRefreshing(true)
    setRefreshError('')
    try {
      queryClient.setQueryData(['integracoes'], await systemApi.integrations({ refresh: 1 }))
    } catch (error) {
      setRefreshError(error.message || 'Não foi possível verificar as integrações.')
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <Panel id="integracoes" className="scroll-mt-20 lg:scroll-mt-8">
      <PanelHeader
        title="Integrações"
        description="De onde vêm as cotações, os índices da renda fixa e o extrato dos bancos."
        actions={(
          <Button variant="secondary" size="sm" icon={RefreshCw} loading={refreshing} onClick={handleRefresh}>
            Verificar agora
          </Button>
        )}
      />
      <div className="space-y-4 p-5">
        <AlertMessage message={refreshError || queryErrorMessage(healthQuery, 'Não foi possível verificar as integrações.')} onDismiss={refreshError ? () => setRefreshError('') : undefined} />
        {healthQuery.isPending ? (
          <ListSkeleton rows={3} className="p-0" />
        ) : data ? (
          <>
            <AlertMessage tone={overall.tone} message={overall.text} />
            <ul className="divide-y divide-zinc-100 rounded-2xl border border-zinc-200">
              {data.items.map((item) => {
                const status = STATUS[item.status] || STATUS.error
                return (
                  <li key={item.key} className="flex flex-wrap items-start gap-3 p-3">
                    <Activity className="mt-0.5 h-4 w-4 shrink-0 text-zinc-400" aria-hidden="true" />
                    <div className="min-w-[14rem] flex-1">
                      <p className="text-sm font-semibold text-zinc-900">{item.label}</p>
                      <p className="text-xs text-zinc-500">{item.purpose}</p>
                      {item.detail ? <p className="mt-1 text-xs text-zinc-700">{item.detail}</p> : null}
                      {item.last_failure && item.last_error ? (
                        <p className="mt-1 text-xs text-zinc-500">
                          Última falha numa busca real: {whenLabel(item.last_failure)} — {item.last_error}
                        </p>
                      ) : null}
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <Badge tone={status.tone}>{status.label}</Badge>
                      {Number.isFinite(item.latency_ms) ? <span className="text-xs text-zinc-500 tabular">{item.latency_ms} ms</span> : null}
                    </div>
                  </li>
                )
              })}
            </ul>
            <p className="text-xs text-zinc-500">Verificado em {whenLabel(data.checked_at)}{data.cached ? ' (guardado)' : ''}.</p>
          </>
        ) : null}
      </div>
    </Panel>
  )
}
