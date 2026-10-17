import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Archive, Landmark, TrendingUp, Plus } from 'lucide-react'
import { accountsApi } from '../../lib/dataApi'
import { formatCurrency } from '../../lib/format'
import { usePrivateFormatter } from '../../lib/privacy'
import { PORTFOLIO_ACCOUNT_TYPE, isBrlAccount, pickPortfolioAccountId } from '../../lib/portfolioAccount'
import { accountBalanceBrl } from '../../lib/transactions'
import {
  AlertMessage,
  Badge,
  Button,
  Collapsible,
  EmptyState,
  Field,
  IconButton,
  Menu,
  Panel,
  PanelHeader,
  cx,
} from '../../components/ui'
import { toast } from '../../lib/toast'
import { confirmAction } from '../../lib/confirm'
import { invalidateServerData, useQuery, useReportQueryError } from '../../lib/queries'

export const ACCOUNT_TYPE_LABELS = {
  CHECKING: 'Conta corrente',
  SAVINGS: 'Poupança',
  BROKERAGE: 'Corretora',
  CASH: 'Dinheiro',
  OTHER: 'Outra',
}

// O app e so em reais: a conta nao tem moeda para escolher.
const emptyAccountForm = () => ({ name: '', type: 'CHECKING', institution: '', initial_balance: '' })

const NO_ITEMS = []

// Contas bancarias: lista com saldo, arquivar e criar. Veio de Transactions.jsx.
// Conta nunca e apagada: DELETE /api/accounts/<id> so preenche archived_at.
export default function ContasSection() {
  const privateMoney = usePrivateFormatter(formatCurrency)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [accountForm, setAccountForm] = useState(emptyAccountForm)

  const accountsQuery = useQuery({ queryKey: ['contas', 'ativas'], queryFn: () => accountsApi.list() })
  useReportQueryError(accountsQuery, setError, 'Não foi possível carregar as contas.')
  const accounts = accountsQuery.data || NO_ITEMS
  const portfolioAccountId = pickPortfolioAccountId(accounts)
  const loading = accountsQuery.isPending
  const fetchAccounts = () => invalidateServerData()

  const handleCreateAccount = async (event) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      await accountsApi.create({
        name: accountForm.name,
        type: accountForm.type,
        institution: accountForm.institution,
        initial_balance: Number(accountForm.initial_balance || 0),
      })
      await fetchAccounts()
      toast(`Conta "${accountForm.name}" criada.`)
      setAccountForm(emptyAccountForm())
      setFormOpen(false)
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível criar a conta.')
    } finally {
      setSaving(false)
    }
  }

  // A conta da carteira e uma conta Corretora (lib/portfolioAccount.js): mudar o
  // tipo e o vinculo. Nao mexe em nenhum lancamento ja gravado.
  const handleLinkToPortfolio = async (account) => {
    if (!(await confirmAction({
      title: `Vincular "${account.name}" à carteira?`,
      message: 'A conta passa a ser do tipo Corretora, e as próximas operações de investimento saem dela. As operações já registradas não mudam.',
      confirmLabel: 'Vincular',
      tone: 'neutral',
    }))) return

    setError('')
    try {
      await accountsApi.update(account.id, { type: PORTFOLIO_ACCOUNT_TYPE })
      await fetchAccounts()
      toast(`"${account.name}" vinculada à carteira.`)
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível vincular a conta.')
    }
  }

  const handleArchiveAccount = async (account) => {
    if (!(await confirmAction({ title: `Arquivar a conta "${account.name}"?`, message: 'Os lançamentos dela continuam no extrato.', confirmLabel: 'Arquivar', tone: 'neutral' }))) return

    setError('')
    try {
      await accountsApi.archive(account.id)
      await fetchAccounts()
      toast(`Conta "${account.name}" arquivada.`)
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível arquivar a conta.')
    }
  }

  return (
    <Panel id="contas" className="scroll-mt-20 lg:scroll-mt-8">
      <PanelHeader
        title="Contas"
        description="Saldo de cada conta. Transferências entre elas não contam como receita nem despesa. As operações de investimento saem da conta da carteira (tipo Corretora)."
        actions={<Badge>{accounts.length} conta(s)</Badge>}
      />

      <div className="space-y-4 p-5">
        <AlertMessage message={error} onDismiss={() => setError('')} />

        {loading ? (
          <p className="py-6 text-center text-sm text-zinc-600">Carregando...</p>
        ) : accounts.length > 0 ? (
          <div className="divide-y divide-zinc-100 rounded-2xl border border-zinc-200">
            {accounts.map((account) => (
              <div key={account.id} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2 font-medium text-zinc-900">
                    <span className="truncate">{account.name}</span>
                    {account.is_default ? <Badge>Padrão</Badge> : null}
                    {account.id === portfolioAccountId ? <Badge>Carteira</Badge> : null}
                  </p>
                  <p className="text-sm text-zinc-600">
                    {ACCOUNT_TYPE_LABELS[account.type] || account.type}
                    {account.institution ? ` · ${account.institution}` : ''}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  {/* Sempre em reais (accountBalanceBrl), como no Inicio. O saldo da
                      Corretora so aparece em Investimentos (Posicao). */}
                  {account.type === PORTFOLIO_ACCOUNT_TYPE ? (
                    <Link to="/investimentos" className="whitespace-nowrap text-right text-sm font-semibold text-emerald-700 underline-offset-2 hover:underline">
                      Em Investimentos
                    </Link>
                  ) : (
                    <span className={cx('whitespace-nowrap text-right font-bold', (accountBalanceBrl(account) ?? 0) >= 0 ? 'text-zinc-950' : 'text-rose-600')}>
                      {accountBalanceBrl(account) === null ? 'sem câmbio hoje' : privateMoney(accountBalanceBrl(account))}
                    </span>
                  )}
                  {account.type === PORTFOLIO_ACCOUNT_TYPE || !isBrlAccount(account) ? (
                    <IconButton label="Arquivar conta" icon={Archive} onClick={() => handleArchiveAccount(account)} />
                  ) : (
                    <Menu
                      label={`Ações da conta ${account.name}`}
                      size="md"
                      items={[
                        { label: 'Vincular à carteira', icon: TrendingUp, onSelect: () => handleLinkToPortfolio(account) },
                        { label: 'Arquivar conta', icon: Archive, onSelect: () => handleArchiveAccount(account) },
                      ]}
                    />
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState icon={Landmark} title="Nenhuma conta" message="Cadastre a primeira conta para começar." className="min-h-40" />
        )}

        <Collapsible label="Nova conta" icon={Plus} open={formOpen} onOpenChange={setFormOpen}>
          <form onSubmit={handleCreateAccount} className="grid grid-cols-1 gap-4 rounded-2xl border border-zinc-200 bg-zinc-50 p-4 sm:grid-cols-2 xl:grid-cols-5">
            <Field label="Nome">
              <input type="text" placeholder="Ex: Nubank" value={accountForm.name} onChange={(event) => setAccountForm({ ...accountForm, name: event.target.value })} className="app-input" required />
            </Field>
            <Field label="Tipo" hint={accountForm.type === PORTFOLIO_ACCOUNT_TYPE ? 'Conta da carteira: as operações de investimento saem dela.' : undefined}>
              <select value={accountForm.type} onChange={(event) => setAccountForm({ ...accountForm, type: event.target.value })} className="app-select">
                {Object.entries(ACCOUNT_TYPE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </Field>
            <Field label="Instituição">
              <input type="text" placeholder="Opcional" value={accountForm.institution} onChange={(event) => setAccountForm({ ...accountForm, institution: event.target.value })} className="app-input" />
            </Field>
            <Field label="Saldo inicial">
              <input type="number" step="0.01" placeholder="0,00" value={accountForm.initial_balance} onChange={(event) => setAccountForm({ ...accountForm, initial_balance: event.target.value })} className="app-input" />
            </Field>
            <div className="flex items-end">
              <Button type="submit" loading={saving} className="w-full">Salvar</Button>
            </div>
          </form>
        </Collapsible>
      </div>
    </Panel>
  )
}
