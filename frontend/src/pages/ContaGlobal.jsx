import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowLeft, CheckCheck, Globe2, Plus } from 'lucide-react'
import { accountsApi, reviewApi, transactionsApi, transfersApi } from '../lib/dataApi'
import {
  formatCurrency,
  formatDateBR,
  formatForeignCurrency,
  formatSignedForeignCurrency,
  getLocalDateString,
} from '../lib/format'
import {
  GLOBAL_ACCOUNT_LABEL,
  accountCurrency,
  brlHint,
  globalAccounts,
  globalStatement,
  globalTotals,
  impliedRate,
} from '../lib/globalAccount'
import { parseMoneyInput } from '../lib/monthlyPlan'
import { usePrivateFormatter } from '../lib/privacy'
import { queryErrorMessage, useQuery } from '../lib/queries'
import { isBrlAccount } from '../lib/portfolioAccount'
import { toast } from '../lib/toast'
import {
  AlertMessage,
  Badge,
  Button,
  EmptyState,
  Field,
  ListSkeleton,
  PageHeader,
  Panel,
  PanelHeader,
  SegmentedControl,
  Sheet,
  SummaryPanel,
  cx,
} from '../components/ui'

const NO_ITEMS = []
const MASKED_FOREIGN = 'US$ ••••••'

const emptyPix = () => ({ account_id: '', amount: '', transfer_amount: '', date: getLocalDateString(), description: '' })

// Conta global (dono, 2026-10-27; lib/globalAccount.js): a unica tela do app em
// outra moeda. Saldo e extrato na moeda da conta, e um "≈ R$" pelo cambio de
// hoje. O que a conta faz sozinha (receita/despesa em dolar) aparece so aqui e
// se revisa aqui; o Pix de reais para ela e uma transferencia.
export default function ContaGlobal() {
  const [params, setParams] = useSearchParams()
  const [error, setError] = useState('')
  const [savingKey, setSavingKey] = useState('')
  const [pixOpen, setPixOpen] = useState(false)
  const [pix, setPix] = useState(emptyPix)

  const accountsQuery = useQuery({ queryKey: ['contas', 'ativas'], queryFn: () => accountsApi.list() })
  const accounts = accountsQuery.data || NO_ITEMS
  const globals = useMemo(() => globalAccounts(accounts), [accounts])
  const account = globals.find((entry) => entry.id === params.get('conta')) || globals[0] || null
  const currency = account ? accountCurrency(account) : 'USD'
  const accountsById = useMemo(() => Object.fromEntries(accounts.map((entry) => [entry.id, entry])), [accounts])
  const reaisAccounts = useMemo(() => accounts.filter((entry) => isBrlAccount(entry) && entry.type !== 'BROKERAGE'), [accounts])

  const foreign = useMemo(() => (value) => formatForeignCurrency(value, currency), [currency])
  const signedForeign = useMemo(() => (value, sign) => formatSignedForeignCurrency(value, sign, currency), [currency])
  const privateForeign = usePrivateFormatter(foreign, MASKED_FOREIGN)
  const privateReais = usePrivateFormatter(formatCurrency)

  const statementQuery = useQuery({
    queryKey: ['lancamentos', 'conta-global', account?.id],
    queryFn: () => transactionsApi.list({ account_id: account.id }),
    enabled: Boolean(account),
  })
  const statement = useMemo(
    () => (account ? globalStatement(statementQuery.data || NO_ITEMS, account.id, accountsById) : NO_ITEMS),
    [statementQuery.data, account, accountsById],
  )
  const totals = globalTotals(statement)
  const toReview = statement.filter((row) => row.needs_review)
  const loadError = queryErrorMessage(accountsQuery, 'Não foi possível carregar as contas.')
    || queryErrorMessage(statementQuery, 'Não foi possível carregar o extrato da conta global.')

  const confirm = async (key, rows) => {
    setSavingKey(key)
    setError('')
    try {
      await reviewApi.confirm(rows.map((row) => ({ table: 'transactions', id: row.id })))
      toast(rows.length > 1 ? `${rows.length} lançamentos confirmados.` : 'Lançamento confirmado.')
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível confirmar.')
    } finally {
      setSavingKey('')
    }
  }

  const savePix = async (event) => {
    event.preventDefault()
    const amount = parseMoneyInput(pix.amount)
    const received = parseMoneyInput(pix.transfer_amount)
    if (!pix.account_id) return setError('Escolha a conta em reais de onde saiu o Pix.')
    if (!Number.isFinite(amount) || amount <= 0) return setError('Informe quanto saiu em reais.')
    if (!Number.isFinite(received) || received <= 0) return setError(`Informe quanto entrou em ${currency}.`)
    setSavingKey('pix')
    setError('')
    try {
      await transfersApi.create({
        account_id: pix.account_id,
        transfer_account_id: account.id,
        amount,
        transfer_amount: received,
        date: pix.date,
        description: pix.description || `Pix para ${account.name}`,
      })
      toast('Transferência registrada.')
      setPix(emptyPix())
      setPixOpen(false)
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível registrar a transferência.')
    } finally {
      setSavingKey('')
    }
  }

  const hint = account ? brlHint(account) : null
  const balance = Number(account?.balance) || 0

  return (
    <div className="space-y-6">
      <PageHeader
        title={GLOBAL_ACCOUNT_LABEL}
        description={account ? `${account.name} · em ${currency}. Fora daqui o app é em reais; o saldo dela não entra no saldo em contas do Início.` : 'A conta em dólar.'}
        actions={(
          <div className="flex flex-wrap items-center gap-2">
            {globals.length > 1 ? (
              <SegmentedControl
                items={globals.map((entry) => ({ value: entry.id, label: entry.name }))}
                value={account?.id}
                onChange={(value) => setParams({ conta: value })}
              />
            ) : null}
            <Link to="/inicio">
              <Button type="button" variant="secondary" icon={ArrowLeft}>Início</Button>
            </Link>
          </div>
        )}
      />

      <AlertMessage tone="danger" message={error || loadError} onDismiss={() => setError('')} />

      {accountsQuery.isPending ? (
        <Panel><ListSkeleton rows={3} /></Panel>
      ) : !account ? (
        <Panel className="p-5">
          <EmptyState
            icon={Globe2}
            title="Nenhuma conta global"
            message="Cadastre a conta em dólar em Ajustes › Contas, com o tipo Conta global (US$)."
            action={<Link to="/ajustes#contas"><Button type="button" variant="secondary">Abrir Ajustes</Button></Link>}
          />
        </Panel>
      ) : (
        <>
          <SummaryPanel
            lead={{
              label: 'Saldo em dólar',
              value: privateForeign(balance),
              tone: balance < 0 ? 'loss' : 'neutral',
              hint: hint === null ? 'sem câmbio hoje' : `≈ ${privateReais(hint)} pelo câmbio de hoje (PTAX)`,
            }}
            figures={[
              { label: 'Entradas', value: privateForeign(totals.in), hint: 'no extrato abaixo' },
              { label: 'Saídas', value: privateForeign(totals.out), hint: totals.pending ? `${totals.pending} a conferir` : 'no extrato abaixo' },
            ]}
          />

          <Panel className="overflow-clip">
            <PanelHeader
              title="Extrato"
              description={`Em ${currency}. Um Pix de uma conta em reais é uma transferência: não é despesa nem receita.`}
              actions={(
                <div className="flex flex-wrap gap-2">
                  {toReview.length > 1 ? (
                    <Button type="button" size="sm" variant="secondary" icon={CheckCheck} loading={savingKey === 'all'} onClick={() => confirm('all', toReview)}>
                      Confirmar todos
                    </Button>
                  ) : null}
                  <Button type="button" size="sm" icon={Plus} onClick={() => setPixOpen(true)}>Pix para cá</Button>
                </div>
              )}
            />
            {statementQuery.isPending ? (
              <ListSkeleton rows={4} />
            ) : statement.length === 0 ? (
              <div className="p-5">
                <EmptyState icon={Globe2} title="Nada por aqui ainda" message="Os movimentos chegam pela Pluggy, ou registre um Pix de uma conta em reais." />
              </div>
            ) : (
              <ul className="divide-y divide-zinc-100">
                {statement.map((row) => {
                  const rate = impliedRate(row)
                  return (
                    <li key={row.id} className="flex items-center gap-3 px-5 py-2.5">
                      <div className="min-w-0 flex-1">
                        <p className="flex min-w-0 items-center gap-1.5 font-medium text-zinc-900">
                          <span className="truncate">{row.description || (row.counterpart ? `${row.direction > 0 ? 'De' : 'Para'} ${row.counterpart}` : 'Movimento')}</span>
                          {row.needs_review ? <Badge tone="info">A revisar</Badge> : null}
                        </p>
                        <p className="truncate text-xs text-zinc-500">
                          {formatDateBR(row.date)}
                          {row.type === 'TRANSFER' && row.counterpart ? ` · ${row.direction > 0 ? 'de' : 'para'} ${row.counterpart}` : ''}
                          {row.source_amount ? ` · saiu ${formatCurrency(row.source_amount)}` : ''}
                          {rate ? ` · ${formatCurrency(rate)} por ${currency}` : ''}
                        </p>
                      </div>
                      {row.pending ? (
                        <p className="whitespace-nowrap text-sm font-medium text-amber-700">valor em {currency} a conferir</p>
                      ) : (
                        <p className={cx('num whitespace-nowrap font-semibold', row.direction > 0 ? 'text-emerald-700' : 'text-zinc-950')}>
                          {signedForeign(row.native, row.direction)}
                        </p>
                      )}
                      {row.needs_review ? (
                        <Button type="button" size="sm" variant="secondary" icon={CheckCheck} loading={savingKey === row.id} onClick={() => confirm(row.id, [row])}>
                          É meu
                        </Button>
                      ) : null}
                    </li>
                  )
                })}
              </ul>
            )}
          </Panel>
        </>
      )}

      <Sheet
        open={pixOpen}
        onClose={() => setPixOpen(false)}
        title={`Pix para ${account?.name || GLOBAL_ACCOUNT_LABEL}`}
        description={`Uma transferência só: o que saiu em reais e o que entrou em ${currency}.`}
        footer={(
          <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <Button type="button" variant="secondary" size="lg" onClick={() => setPixOpen(false)}>Cancelar</Button>
            <Button type="submit" form="global-pix-form" size="lg" loading={savingKey === 'pix'}>Salvar</Button>
          </div>
        )}
      >
        <form id="global-pix-form" onSubmit={savePix} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="De" className="sm:col-span-2">
            <select value={pix.account_id} onChange={(event) => setPix({ ...pix, account_id: event.target.value })} className="app-select" required>
              <option value="">Escolha a conta em reais</option>
              {reaisAccounts.map((entry) => <option key={entry.id} value={entry.id}>{entry.name}</option>)}
            </select>
          </Field>
          <Field label="Saiu (R$)">
            <input type="text" inputMode="decimal" placeholder="0,00" value={pix.amount} onChange={(event) => setPix({ ...pix, amount: event.target.value })} className="app-input" required />
          </Field>
          <Field label={`Entrou (${currency})`}>
            <input type="text" inputMode="decimal" placeholder="0,00" value={pix.transfer_amount} onChange={(event) => setPix({ ...pix, transfer_amount: event.target.value })} className="app-input" required />
          </Field>
          <Field label="Data">
            <input type="date" value={pix.date} onChange={(event) => setPix({ ...pix, date: event.target.value })} className="app-input" required />
          </Field>
          <Field label="Descrição">
            <input type="text" placeholder="Opcional" value={pix.description} onChange={(event) => setPix({ ...pix, description: event.target.value })} className="app-input" />
          </Field>
        </form>
      </Sheet>
    </div>
  )
}
