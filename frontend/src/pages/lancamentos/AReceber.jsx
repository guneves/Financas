import { useMemo, useState } from 'react'
import { CheckCheck, Coins, CreditCard } from 'lucide-react'
import { Link } from 'react-router-dom'
import { receivablesApi } from '../../lib/dataApi'
import { formatCurrency, formatDateBR, localDateOfTimestamp } from '../../lib/format'
import { queryErrorMessage, useQuery } from '../../lib/queries'
import { groupReceivables, settlePayload } from '../../lib/sharing'
import { toast } from '../../lib/toast'
import PaidBySheet from './PaidBySheet'
import {
  AlertMessage,
  Button,
  EmptyState,
  Menu,
  ListSkeleton,
  PageHeader,
  Panel,
  PanelHeader,
  SegmentedControl,
  SummaryPanel,
} from '../../components/ui'

const VIEWS = [
  { value: 'pending', label: 'Pendentes' },
  { value: 'all', label: 'Todos' },
]

// A receber (032, lib/sharing.js): a parte dos outros nas despesas e compras
// no cartao marcadas como "De outra pessoa" ou "Dividida", por pessoa. Fica
// pendente ate o dono marcar que a pessoa pagou; marcar nao grava dinheiro (o Pix
// que chega e um lancamento proprio): "Pago" pergunta com que entrada
// (PaidBySheet), e a parte dos outros deixa de ser receita. Depois de pago, o
// menu troca a entrada ou volta para pendente.
export default function AReceber() {
  const [view, setView] = useState('pending')
  const [savingKey, setSavingKey] = useState('')
  const [error, setError] = useState('')
  const [paying, setPaying] = useState(null)
  const query = useQuery({
    queryKey: ['lancamentos', 'a-receber', view],
    queryFn: () => receivablesApi.list(view === 'all'),
  })
  const items = useMemo(() => query.data || [], [query.data])
  const pending = useMemo(() => items.filter((item) => !item.settled_at), [items])
  const groups = useMemo(() => groupReceivables(view === 'all' ? items : pending), [items, pending, view])
  const pendingTotal = useMemo(() => groupReceivables(pending).reduce((acc, group) => acc + group.total, 0), [pending])
  const loadError = queryErrorMessage(query, 'Não foi possível carregar o que você tem a receber.')

  const settle = async (key, list, settled) => {
    setSavingKey(key)
    setError('')
    try {
      await receivablesApi.settle(settlePayload(list, settled))
      toast(settled ? 'Marcado como pago.' : 'Voltou para pendente.')
    } catch (err) {
      setError(err.message || 'Não foi possível atualizar.')
    } finally {
      setSavingKey('')
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="A receber"
        description="O que você pagou por outras pessoas. Marque um lançamento ou uma compra como de outra pessoa ao editá-lo no Extrato ou em Cartões; ele fica aqui até você marcar que ela pagou."
        actions={<SegmentedControl items={VIEWS} value={view} onChange={setView} />}
      />

      <AlertMessage tone="danger" message={error || loadError} onDismiss={() => setError('')} />

      {query.isPending ? (
        <Panel><ListSkeleton rows={4} /></Panel>
      ) : (
        <>
          {pending.length > 0 ? (
            <SummaryPanel
              lead={{ label: 'Pendente', value: formatCurrency(pendingTotal) }}
              figures={[
                { label: 'Pessoas', value: String(groupReceivables(pending).length) },
                { label: 'Itens', value: String(pending.length) },
              ]}
            />
          ) : null}

          {groups.length === 0 ? (
            <Panel className="p-5">
              <EmptyState
                icon={Coins}
                title="Nada a receber"
                message="Ao editar uma despesa no Extrato ou uma compra em Cartões, escolha De quem é? › Dividida ou De outra pessoa e informe o nome."
                action={<Link to="/lancamentos/extrato"><Button type="button" variant="secondary">Abrir o Extrato</Button></Link>}
              />
            </Panel>
          ) : (
            groups.map((group) => {
              const open = group.items.filter((item) => !item.settled_at)
              const openTotal = groupReceivables(open)[0]?.total || 0
              return (
                <Panel key={group.person} className="overflow-clip">
                  <PanelHeader
                    title={open.length > 0 ? `${group.person} · ${formatCurrency(openTotal)}` : group.person}
                    description={open.length > 1 ? `${open.length} itens pendentes` : open.length === 0 ? 'Tudo pago' : ''}
                    actions={open.length > 1 ? (
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        icon={CheckCheck}
                        loading={savingKey === `person:${group.person}`}
                        onClick={() => setPaying(open)}
                      >
                        Tudo pago
                      </Button>
                    ) : null}
                  />
                  <ul className="divide-y divide-zinc-100">
                    {group.items.map((item) => (
                      <li key={`${item.kind}:${item.id}`} className="flex items-center gap-3 px-5 py-2.5">
                        <div className="min-w-0 flex-1">
                          <p className="flex min-w-0 items-center gap-1.5 font-medium text-zinc-900">
                            {item.kind === 'CARD_PURCHASE' ? <CreditCard className="h-3.5 w-3.5 shrink-0 text-zinc-400" aria-label="Compra no cartão" /> : null}
                            <span className="truncate">{item.description}</span>
                          </p>
                          <p className="truncate text-xs text-zinc-500">
                            {formatDateBR(item.date)}
                            {item.card_name ? ` · ${item.card_name}` : ''}
                            {item.share_mode === 'SPLIT' ? ` · dividida, total ${formatCurrency(item.amount)}` : ''}
                            {item.settled_at ? ` · pago em ${formatDateBR(localDateOfTimestamp(item.settled_at))}` : ''}
                            {item.paid_by ? ` com ${item.paid_by.description} (${formatCurrency(item.paid_by.amount)})` : ''}
                          </p>
                        </div>
                        <p className={item.settled_at ? 'num whitespace-nowrap font-semibold text-zinc-400 line-through' : 'num whitespace-nowrap font-semibold text-zinc-950'}>
                          {formatCurrency(item.others_amount)}
                        </p>
                        {item.settled_at ? (
                          <Menu
                            label="Ações do item pago"
                            items={[
                              { label: item.paid_by ? 'Trocar a entrada' : 'Escolher a entrada', onSelect: () => setPaying([item]) },
                              { label: 'Voltar para pendente', onSelect: () => settle(`item:${item.id}`, [item], false) },
                            ]}
                          />
                        ) : (
                          <Button
                            type="button"
                            size="sm"
                            icon={CheckCheck}
                            loading={savingKey === `item:${item.id}`}
                            onClick={() => setPaying([item])}
                          >
                            Pago
                          </Button>
                        )}
                      </li>
                    ))}
                  </ul>
                </Panel>
              )
            })
          )}
        </>
      )}
      <PaidBySheet items={paying} onClose={() => setPaying(null)} />
    </div>
  )
}
