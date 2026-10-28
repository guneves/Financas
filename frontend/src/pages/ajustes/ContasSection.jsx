import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Archive, Landmark, Pencil, Plus, RotateCcw, Star, TrendingUp, Unlink } from 'lucide-react'
import { accountsApi } from '../../lib/dataApi'
import { formatCurrency } from '../../lib/format'
import { moneyInputValue, parseMoneyInput } from '../../lib/monthlyPlan'
import { usePrivateFormatter } from '../../lib/privacy'
import { PORTFOLIO_ACCOUNT_TYPE, isBrlAccount, pickPortfolioAccountId } from '../../lib/portfolioAccount'
import { accountBalanceBrl } from '../../lib/transactions'
import { GLOBAL_ACCOUNT_LABEL, accountCurrency, isGlobalAccount } from '../../lib/globalAccount'
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
  Sheet,
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

// O app e em reais: a unica moeda a escolher e a da Conta global (US$), um
// tipo so desta lista (lib/globalAccount.js); no servidor ela e CHECKING em USD.
const GLOBAL_TYPE = 'GLOBAL_USD'
const NEW_ACCOUNT_TYPES = { ...ACCOUNT_TYPE_LABELS, [GLOBAL_TYPE]: 'Conta global (US$)' }
const emptyAccountForm = () => ({ name: '', type: 'CHECKING', institution: '', initial_balance: '' })

const NO_ITEMS = []

// Saldo inicial pode ser negativo (cheque especial): o sinal fica de fora da
// leitura do valor (parseMoneyInput so le positivos).
function parseBalanceInput(value) {
  const text = String(value ?? '').trim()
  const negative = text.startsWith('-')
  const amount = parseMoneyInput(negative ? text.slice(1) : text)
  return negative && Number.isFinite(amount) ? -amount : amount
}

// Contas bancarias: lista com saldo, criar, editar (nome, instituicao, saldo
// inicial), tornar padrao, vincular/desvincular da carteira, arquivar e
// reativar. Conta nunca e apagada: DELETE /api/accounts/<id> so preenche
// archived_at. A padrao e sempre uma conta ativa fora da Corretora: o servidor
// passa a marca para outra quando a padrao e arquivada ou vira a da carteira.
export default function ContasSection() {
  const privateMoney = usePrivateFormatter(formatCurrency)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [accountForm, setAccountForm] = useState(emptyAccountForm)
  const [editing, setEditing] = useState(null)
  const [editForm, setEditForm] = useState({ name: '', institution: '', initial_balance: '' })

  const accountsQuery = useQuery({ queryKey: ['contas', 'todas'], queryFn: () => accountsApi.list({ include_archived: 1 }) })
  useReportQueryError(accountsQuery, setError, 'Não foi possível carregar as contas.')
  const allAccounts = accountsQuery.data || NO_ITEMS
  const accounts = allAccounts.filter((account) => !account.archived_at)
  const archivedAccounts = allAccounts.filter((account) => account.archived_at)
  const portfolioAccountId = pickPortfolioAccountId(accounts)
  const loading = accountsQuery.isPending
  const fetchAccounts = () => invalidateServerData()

  const handleCreateAccount = async (event) => {
    event.preventDefault()
    const initialBalance = parseBalanceInput(accountForm.initial_balance)
    if (Number.isNaN(initialBalance)) {
      setError('Informe um saldo inicial válido.')
      return
    }
    setSaving(true)
    setError('')
    try {
      const global = accountForm.type === GLOBAL_TYPE
      await accountsApi.create({
        name: accountForm.name,
        type: global ? 'CHECKING' : accountForm.type,
        institution: accountForm.institution,
        initial_balance: initialBalance ?? 0,
        ...(global ? { currency: 'USD' } : {}),
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

  // Volta a ser conta corrente: o saldo dela volta ao Inicio. As operacoes ja
  // registradas nao mudam; as proximas saem de outra Corretora (ou de nenhuma).
  const handleUnlinkFromPortfolio = async (account) => {
    if (!(await confirmAction({
      title: `Desvincular "${account.name}" da carteira?`,
      message: 'A conta volta a ser Conta corrente, e o saldo dela volta a aparecer no Início. As operações já registradas não mudam; as próximas precisam de outra conta Corretora, ou de "Não descontar de nenhuma conta".',
      confirmLabel: 'Desvincular',
      tone: 'neutral',
    }))) return
    await updateAccount(account, { type: 'CHECKING' }, `"${account.name}" desvinculada da carteira.`, 'Não foi possível desvincular a conta.')
  }

  const updateAccount = async (account, payload, success, failure) => {
    setSaving(true)
    setError('')
    try {
      await accountsApi.update(account.id, payload)
      await fetchAccounts()
      toast(success)
      return true
    } catch (requestError) {
      setError(requestError.message || failure)
      return false
    } finally {
      setSaving(false)
    }
  }

  const openEdit = (account) => {
    setEditing(account)
    setEditForm({
      name: account.name,
      institution: account.institution || '',
      initial_balance: moneyInputValue(account.initial_balance ?? 0),
    })
  }

  const handleSaveEdit = async (event) => {
    event.preventDefault()
    if (!editing) return
    const initialBalance = parseBalanceInput(editForm.initial_balance)
    if (Number.isNaN(initialBalance)) {
      setError('Informe um saldo inicial válido.')
      return
    }
    const saved = await updateAccount(editing, {
      name: editForm.name,
      institution: editForm.institution,
      initial_balance: initialBalance ?? 0,
    }, `Conta "${editForm.name}" atualizada.`, 'Não foi possível atualizar a conta.')
    if (saved) setEditing(null)
  }

  const accountMenuItems = (account) => {
    const isPortfolio = account.type === PORTFOLIO_ACCOUNT_TYPE
    return [
      { label: 'Editar conta', icon: Pencil, onSelect: () => openEdit(account) },
      !account.is_default && !isPortfolio && !isGlobalAccount(account)
        ? { label: 'Tornar padrão', icon: Star, onSelect: () => updateAccount(account, { is_default: true }, `"${account.name}" é a conta padrão.`, 'Não foi possível trocar a conta padrão.') }
        : null,
      !isPortfolio && !account.is_default && isBrlAccount(account)
        ? { label: 'Vincular à carteira', icon: TrendingUp, onSelect: () => handleLinkToPortfolio(account) }
        : null,
      isPortfolio
        ? { label: 'Desvincular da carteira', icon: Unlink, onSelect: () => handleUnlinkFromPortfolio(account) }
        : null,
      { label: 'Arquivar conta', icon: Archive, onSelect: () => handleArchiveAccount(account) },
    ].filter(Boolean)
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
                    {isGlobalAccount(account) ? `${GLOBAL_ACCOUNT_LABEL} (${accountCurrency(account)})` : ACCOUNT_TYPE_LABELS[account.type] || account.type}
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
                  ) : isGlobalAccount(account) ? (
                    // O saldo em dolar so na tela dela.
                    <Link to={`/inicio/conta-global?conta=${account.id}`} className="flex min-h-11 items-center whitespace-nowrap text-right text-sm font-semibold text-emerald-700 underline-offset-2 hover:underline">
                      {GLOBAL_ACCOUNT_LABEL}
                    </Link>
                  ) : (
                    <span className={cx('whitespace-nowrap text-right font-bold', (accountBalanceBrl(account) ?? 0) >= 0 ? 'text-zinc-950' : 'text-rose-600')}>
                      {accountBalanceBrl(account) === null ? 'sem câmbio hoje' : privateMoney(accountBalanceBrl(account))}
                    </span>
                  )}
                  <Menu label={`Ações da conta ${account.name}`} size="md" items={accountMenuItems(account)} />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState icon={Landmark} title="Nenhuma conta" message="Cadastre a primeira conta para começar." className="min-h-40" />
        )}

        {archivedAccounts.length > 0 ? (
          <Collapsible label={`Arquivadas (${archivedAccounts.length})`} icon={Archive}>
            <div className="divide-y divide-zinc-100 rounded-2xl border border-zinc-200">
              {archivedAccounts.map((account) => (
                <div key={account.id} className="flex items-center justify-between gap-3 px-4 py-3">
                  <div className="min-w-0">
                    <p className="truncate font-medium text-zinc-500">{account.name}</p>
                    <p className="text-sm text-zinc-500">{ACCOUNT_TYPE_LABELS[account.type] || account.type}</p>
                  </div>
                  <IconButton
                    label={`Reativar a conta ${account.name}`}
                    icon={RotateCcw}
                    disabled={saving}
                    onClick={() => updateAccount(account, { archived_at: null }, `Conta "${account.name}" reativada.`, 'Não foi possível reativar a conta.')}
                  />
                </div>
              ))}
            </div>
          </Collapsible>
        ) : null}

        <Collapsible label="Nova conta" icon={Plus} open={formOpen} onOpenChange={setFormOpen}>
          <form onSubmit={handleCreateAccount} className="grid grid-cols-1 gap-4 rounded-2xl border border-zinc-200 bg-zinc-50 p-4 sm:grid-cols-2 xl:grid-cols-5">
            <Field label="Nome">
              <input type="text" placeholder="Ex: Nubank" value={accountForm.name} onChange={(event) => setAccountForm({ ...accountForm, name: event.target.value })} className="app-input" required />
            </Field>
            <Field
              label="Tipo"
              hint={accountForm.type === PORTFOLIO_ACCOUNT_TYPE
                ? 'Conta da carteira: as operações de investimento saem dela.'
                : accountForm.type === GLOBAL_TYPE ? 'Em dólar: saldo e extrato em US$ na tela Conta global; no Início, convertida.' : undefined}
            >
              <select value={accountForm.type} onChange={(event) => setAccountForm({ ...accountForm, type: event.target.value })} className="app-select">
                {Object.entries(NEW_ACCOUNT_TYPES).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </Field>
            <Field label="Instituição">
              <input type="text" placeholder="Opcional" value={accountForm.institution} onChange={(event) => setAccountForm({ ...accountForm, institution: event.target.value })} className="app-input" />
            </Field>
            <Field label={accountForm.type === GLOBAL_TYPE ? 'Saldo inicial (US$)' : 'Saldo inicial'}>
              <input type="text" inputMode="decimal" placeholder="0,00" value={accountForm.initial_balance} onChange={(event) => setAccountForm({ ...accountForm, initial_balance: event.target.value })} className="app-input" />
            </Field>
            <div className="flex items-end">
              <Button type="submit" loading={saving} className="w-full">Salvar</Button>
            </div>
          </form>
        </Collapsible>
      </div>

      <Sheet
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={editing ? `Editar "${editing.name}"` : ''}
        description="Mudar o saldo inicial recalcula o saldo da conta; nenhum lançamento muda."
        footer={(
          <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <Button type="button" variant="secondary" size="lg" onClick={() => setEditing(null)}>Cancelar</Button>
            <Button type="submit" form="account-edit-form" size="lg" loading={saving}>Salvar</Button>
          </div>
        )}
      >
        <form id="account-edit-form" onSubmit={handleSaveEdit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Nome" className="sm:col-span-2">
            <input type="text" value={editForm.name} onChange={(event) => setEditForm({ ...editForm, name: event.target.value })} className="app-input" required />
          </Field>
          <Field label="Instituição">
            <input type="text" placeholder="Opcional" value={editForm.institution} onChange={(event) => setEditForm({ ...editForm, institution: event.target.value })} className="app-input" />
          </Field>
          <Field label={isGlobalAccount(editing) ? `Saldo inicial (${accountCurrency(editing)})` : 'Saldo inicial'}>
            <input type="text" inputMode="decimal" placeholder="0,00" value={editForm.initial_balance} onChange={(event) => setEditForm({ ...editForm, initial_balance: event.target.value })} className="app-input" />
          </Field>
        </form>
      </Sheet>
    </Panel>
  )
}
