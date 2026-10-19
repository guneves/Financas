import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Search, Trash2, TrendingUp } from 'lucide-react'
import { investmentProceedsApi, investmentsApi } from '../../lib/dataApi'
import {
  AlertMessage,
  Badge,
  Button,
  EmptyState,
  ListSkeleton,
  Menu,
  Panel,
  PageHeader,
  PanelHeader,
  SegmentedControl,
  SummaryPanel,
  cx,
} from '../../components/ui'
import { formatCurrency, formatSignedCurrency, formatUnitCurrency, getLocalDateString } from '../../lib/format'
import { usePrivateFormatter } from '../../lib/privacy'
import { queryErrorMessage, useQuery } from '../../lib/queries'
import { useProceedsSync } from '../../lib/proceedsSync'
import { buildInvestmentStatement, groupEntriesByDay, statementTotals } from '../../lib/investmentStatement'
import { confirmAction } from '../../lib/confirm'
import { toast } from '../../lib/toast'

// Extrato de investimentos (Extrato > Investimentos): operacoes da carteira e
// proventos. Uma operacao se exclui daqui (com o aporte/resgate dela na
// conta); editar continua em Investimentos > Operacoes e em Proventos.

const KIND_ITEMS = [
  { value: 'ALL', label: 'Tudo' },
  { value: 'MOVEMENTS', label: 'Operações' },
  { value: 'PROCEEDS', label: 'Proventos' },
]

const PAGE_SIZE = 100
const NO_ITEMS = []

function dayLabel(date) {
  if (!date) return 'Sem data'
  const [year, month, dayOfMonth] = date.split('-').map(Number)
  const value = new Date(year, month - 1, dayOfMonth)
  return value.toLocaleDateString('pt-BR', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    ...(year !== new Date().getFullYear() ? { year: 'numeric' } : {}),
  })
}

function amountClass(entry) {
  if (entry.scheduled || entry.amount === 0) return 'text-zinc-500'
  return entry.amount > 0 ? 'text-emerald-700' : 'text-zinc-950'
}

function detailText(entry) {
  const parts = []
  if (entry.quantity) {
    parts.push(`${entry.quantity.toLocaleString('pt-BR', { maximumFractionDigits: 6 })} ${entry.source === 'proceed' ? 'cotas' : 'un.'}`)
  }
  if (entry.unitPrice) parts.push(`${formatUnitCurrency(entry.unitPrice)}${entry.source === 'proceed' ? '/cota' : ''}`)
  if (entry.tax) parts.push(`IR ${formatCurrency(entry.tax)}`)
  return parts.join(' · ')
}

export default function ExtratoInvestimentos({ viewSwitch }) {
  useProceedsSync()
  const [kind, setKind] = useState('ALL')
  const [query, setQuery] = useState('')
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  useEffect(() => setVisibleCount(PAGE_SIZE), [kind, query])

  const movementsQuery = useQuery({
    queryKey: ['investimentos', 'operacoes'],
    queryFn: () => investmentsApi.list({ order: 'created_at', ascending: false }),
  })
  const proceedsQuery = useQuery({
    queryKey: ['proventos', 'extrato'],
    queryFn: () => investmentProceedsApi.list({}),
  })
  const movements = movementsQuery.data || NO_ITEMS
  const proceeds = proceedsQuery.data || NO_ITEMS
  const loading = (movementsQuery.isPending || proceedsQuery.isPending)
  const error = queryErrorMessage(movementsQuery, '') || queryErrorMessage(proceedsQuery, '')

  const money = usePrivateFormatter(formatCurrency)
  const signed = usePrivateFormatter(formatSignedCurrency)

  const today = getLocalDateString()
  const entries = useMemo(
    () => buildInvestmentStatement(movements, proceeds, { today, kind, query }),
    [movements, proceeds, today, kind, query],
  )
  const totals = useMemo(() => statementTotals(entries), [entries])
  const visible = entries.slice(0, visibleCount)
  const days = useMemo(() => groupEntriesByDay(visible), [visible])
  const hiddenCount = entries.length - visible.length

  // Excluir a operacao leva junto o aporte/resgate que ela escreveu na conta
  // (o servidor apaga o lancamento vinculado no mesmo DELETE).
  const [deleteError, setDeleteError] = useState('')
  const handleDeleteMovement = async (entry) => {
    if (!(await confirmAction({
      title: `Excluir ${entry.kind.toLowerCase()} de ${entry.title}?`,
      message: entry.inStatement
        ? 'A operação sai da carteira e o lançamento dela sai do extrato da conta; o saldo é recalculado.'
        : 'Só esta operação sai do histórico; as outras do ativo continuam.',
      confirmLabel: 'Excluir',
    }))) return
    setDeleteError('')
    try {
      await investmentsApi.remove(entry.movementId)
      toast('Operação excluída.')
    } catch (deleteFailure) {
      setDeleteError(deleteFailure.message || 'Não foi possível excluir a operação.')
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Extrato" description="Operações da carteira e proventos recebidos." />
      {viewSwitch}

      <AlertMessage tone="warning" message={error ? 'Não foi possível carregar o extrato de investimentos.' : ''} />
      <AlertMessage tone="warning" message={deleteError} onDismiss={() => setDeleteError('')} />

      <SummaryPanel
        lead={{ label: 'Proventos recebidos', value: money(totals.proceeds), tone: 'gain', hint: totals.scheduled > 0 ? `${money(totals.scheduled)} agendados` : undefined }}
        figures={[
          { label: 'Aportes e compras', value: money(totals.invested) },
          { label: 'Vendas e resgates', value: money(totals.withdrawn) },
        ]}
      />

      <Panel className="overflow-clip">
        <PanelHeader
          title="Extrato de investimentos"
          description="Operações da carteira e proventos. Não altera o saldo das contas."
          actions={<Badge>{`${entries.length} registro(s)`}</Badge>}
        />

        <div className="flex flex-col gap-2 border-b border-zinc-100 px-5 py-4 sm:flex-row sm:items-center">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
            <input
              type="search"
              aria-label="Buscar no extrato de investimentos"
              placeholder="Buscar por ativo ou tipo"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="app-input h-11 pl-9"
            />
          </div>
          <SegmentedControl items={KIND_ITEMS} value={kind} onChange={setKind} />
        </div>

        {loading ? (
          <ListSkeleton rows={8} />
        ) : entries.length > 0 ? (
          <>
            {days.map((group) => (
              <section key={group.date} aria-label={dayLabel(group.date)}>
                <h3 className="flex items-baseline justify-between gap-3 bg-zinc-50/70 px-5 py-2 text-sm">
                  <span className="font-bold text-zinc-700 first-letter:uppercase">{dayLabel(group.date)}</span>
                  <span className="whitespace-nowrap font-semibold text-zinc-500 tabular">{signed(group.total)}</span>
                </h3>
                <ul className="divide-y divide-zinc-100">
                  {group.items.map((entry) => (
                    <li key={entry.id} className="flex min-h-[56px] items-center gap-3 px-5 py-2.5">
                      <div className="min-w-0 flex-1">
                        <p className="flex min-w-0 items-center gap-2">
                          <span className="truncate font-medium text-zinc-900">{entry.title}</span>
                          <Badge>{entry.kind}</Badge>
                          {entry.scheduled ? <Badge tone="info">Agendado</Badge> : null}
                        </p>
                        <p className="mt-0.5 truncate text-xs text-zinc-500">
                          {[detailText(entry), entry.inStatement ? 'no extrato da conta' : ''].filter(Boolean).join(' · ')}
                        </p>
                      </div>
                      <p className={cx('shrink-0 whitespace-nowrap font-semibold tabular', amountClass(entry))}>
                        {entry.amount === 0 ? 'sem custo' : signed(entry.amount)}
                      </p>
                      {entry.deletable ? (
                        <Menu
                          label={`Ações de ${entry.kind} ${entry.title}`}
                          items={[
                            { label: 'Excluir operação', icon: Trash2, tone: 'danger', onSelect: () => handleDeleteMovement(entry) },
                          ]}
                        />
                      ) : null}
                    </li>
                  ))}
                </ul>
              </section>
            ))}
            {hiddenCount > 0 ? (
              <div className="flex flex-col items-center gap-2 border-t border-zinc-100 px-5 py-4 sm:flex-row sm:justify-between">
                <p className="text-sm text-zinc-500">Mostrando {visible.length} de {entries.length}</p>
                <Button type="button" variant="secondary" onClick={() => setVisibleCount((count) => count + PAGE_SIZE)}>
                  Mostrar mais {Math.min(PAGE_SIZE, hiddenCount)}
                </Button>
              </div>
            ) : null}
          </>
        ) : (
          <div className="p-5">
            <EmptyState
              icon={TrendingUp}
              title="Nada por aqui"
              message={query || kind !== 'ALL' ? 'Nenhum registro atende aos filtros.' : 'Operações e proventos da carteira aparecem aqui.'}
              action={<Link to="/investimentos/operacoes" className="text-sm font-semibold text-emerald-700">Ir para Operações</Link>}
            />
          </div>
        )}
      </Panel>
    </div>
  )
}
