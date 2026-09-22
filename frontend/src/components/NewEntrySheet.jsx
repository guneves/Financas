import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowDownCircle, ArrowLeftRight, ArrowUpCircle, Briefcase, CreditCard } from 'lucide-react'
import {
  accountsApi,
  categoriesApi,
  ccExpensesApi,
  creditCardsApi,
  transactionsApi,
  transfersApi,
} from '../lib/dataApi'
import {
  buildCategoryOptions,
  filterCategoryOptions,
  getLocalDateString,
  parseLocalDate,
  pickDefaultAccountId,
} from '../pages/lancamentos/helpers'
import { AlertMessage, Button, EmptyState, Field, SegmentedControl, Sheet } from './ui'

const FORM_ID = 'new-entry-form'

export const NEW_ENTRY_TYPES = [
  { value: 'EXPENSE', label: 'Despesa', icon: ArrowDownCircle },
  { value: 'INCOME', label: 'Receita', icon: ArrowUpCircle },
  { value: 'TRANSFER', label: 'Transferência', icon: ArrowLeftRight },
  { value: 'CARD', label: 'Compra no cartão', icon: CreditCard },
  { value: 'INVESTMENT', label: 'Investimento', icon: Briefcase },
]

const settingsLink = (hash, text) => (
  <Link to={`/ajustes#${hash}`} className="font-semibold text-emerald-700 underline-offset-2 hover:underline">{text}</Link>
)

// Defaults (docs/ux-reorganization.md D6): data = hoje, conta = conta padrao,
// cartao = primeiro cartao, 1 parcela.
const emptyBankForm = (type, accountId) => ({ amount: '', date: getLocalDateString(), category: '', description: '', type, account_id: accountId })
const emptyTransferForm = (accountId) => ({ amount: '', date: getLocalDateString(), account_id: accountId, transfer_account_id: '', description: '' })
const emptyExpenseForm = (cardId) => ({ card_id: cardId, category: '', description: '', total_amount: '', purchase_date: getLocalDateString(), installments: '1' })

// O "+ Novo": todos os formularios de lancamento num lugar so. Os handlers de
// envio vieram de Transactions.jsx (banco, transferencia) e de Carteira.jsx
// (compra no cartao, via POST /api/cc-expenses/purchases — a regra da fatura
// fica no backend). "Investimento" nao tem formulario aqui: `onPickInvestment`
// abre o InvestmentLaunchModal.
export default function NewEntrySheet({ open, initialType = 'EXPENSE', onClose, onSaved, onPickInvestment }) {
  const [type, setType] = useState(initialType)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const [accounts, setAccounts] = useState([])
  const [categories, setCategories] = useState([])
  const [cards, setCards] = useState([])

  const [transForm, setTransForm] = useState(() => emptyBankForm('EXPENSE', ''))
  const [transferForm, setTransferForm] = useState(() => emptyTransferForm(''))
  const [expenseForm, setExpenseForm] = useState(() => emptyExpenseForm(''))

  const defaultAccountId = useMemo(() => pickDefaultAccountId(accounts), [accounts])
  const categoryOptions = useMemo(() => buildCategoryOptions(categories), [categories])

  // Ao abrir: tipo pedido, formularios limpos com a data de hoje, e contas,
  // cartoes e categorias frescos (podem ter mudado em Ajustes).
  useEffect(() => {
    if (!open) return undefined
    let cancelled = false

    setType(initialType === 'INVESTMENT' ? 'EXPENSE' : initialType || 'EXPENSE')
    setError('')
    setTransForm(emptyBankForm(initialType === 'INCOME' ? 'INCOME' : 'EXPENSE', ''))
    setTransferForm(emptyTransferForm(''))
    setExpenseForm(emptyExpenseForm(''))
    setLoading(true)

    Promise.all([accountsApi.list(), categoriesApi.list(), creditCardsApi.list()])
      .then(([accountData, categoryData, cardData]) => {
        if (cancelled) return
        const safeAccounts = accountData || []
        const safeCards = cardData || []
        const accountId = pickDefaultAccountId(safeAccounts)
        setAccounts(safeAccounts)
        setCategories(categoryData || [])
        setCards(safeCards)
        setTransForm((current) => ({ ...current, account_id: current.account_id || accountId }))
        setTransferForm((current) => ({ ...current, account_id: current.account_id || accountId }))
        setExpenseForm((current) => ({ ...current, card_id: current.card_id || safeCards[0]?.id || '' }))
      })
      .catch((loadError) => {
        if (!cancelled) setError(loadError.message || 'Nao foi possivel carregar contas, cartoes e categorias.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [open, initialType])

  const handleTypeChange = (nextType) => {
    if (nextType === 'INVESTMENT') {
      onPickInvestment?.()
      return
    }
    setType(nextType)
    setError('')
    if (nextType === 'EXPENSE' || nextType === 'INCOME') {
      // A categoria depende do tipo (receita x despesa); o resto do que foi digitado fica.
      setTransForm((current) => (current.type === nextType ? current : { ...current, type: nextType, category: '' }))
    }
  }

  const finish = async () => {
    await onSaved?.()
    onClose()
  }

  const handleBankSubmit = async (event) => {
    event.preventDefault()
    const amount = Number(transForm.amount)
    if (!Number.isFinite(amount) || amount <= 0) {
      setError('Informe um valor bancario valido.')
      return
    }

    setSaving(true)
    setError('')
    try {
      await transactionsApi.create({
        amount,
        date: transForm.date,
        category: transForm.category,
        description: transForm.description,
        type: transForm.type,
        account_id: transForm.account_id || defaultAccountId || undefined,
      })
      await finish()
    } catch (submitError) {
      setError(submitError.message || 'Nao foi possivel criar o lancamento.')
    } finally {
      setSaving(false)
    }
  }

  const handleTransferSubmit = async (event) => {
    event.preventDefault()
    const amount = Number(transferForm.amount)
    if (!Number.isFinite(amount) || amount <= 0) {
      setError('Informe um valor valido para a transferencia.')
      return
    }
    if (transferForm.account_id === transferForm.transfer_account_id) {
      setError('Origem e destino devem ser contas diferentes.')
      return
    }

    setSaving(true)
    setError('')
    try {
      await transfersApi.create({
        amount,
        date: transferForm.date,
        account_id: transferForm.account_id,
        transfer_account_id: transferForm.transfer_account_id,
        description: transferForm.description,
      })
      await finish()
    } catch (submitError) {
      setError(submitError.message || 'Nao foi possivel registrar a transferencia.')
    } finally {
      setSaving(false)
    }
  }

  const handleCCExpenseSubmit = async (event) => {
    event.preventDefault()
    const totalAmount = Number(expenseForm.total_amount)
    const installmentsCount = Number(expenseForm.installments)
    const purchaseDate = parseLocalDate(expenseForm.purchase_date)
    const selectedCard = cards.find((card) => card.id === expenseForm.card_id)

    if (!selectedCard || !purchaseDate || Number.isNaN(purchaseDate.getTime()) || !Number.isFinite(totalAmount) || totalAmount <= 0 || !Number.isInteger(installmentsCount) || installmentsCount <= 0) {
      setError('Preencha a compra no cartao com valores validos.')
      return
    }

    setSaving(true)
    setError('')
    try {
      // O parcelamento e a fatura de cada parcela sao calculados no backend
      // (POST /api/cc-expenses/purchases), junto do cartao que define a regra.
      await ccExpensesApi.createPurchase({
        card_id: expenseForm.card_id,
        category: expenseForm.category,
        description: expenseForm.description,
        total_amount: totalAmount,
        purchase_date: expenseForm.purchase_date,
        installments: installmentsCount,
      })
      await finish()
    } catch (submitError) {
      setError(submitError.message || 'Nao foi possivel criar a compra no cartao.')
    } finally {
      setSaving(false)
    }
  }

  const onSubmit = type === 'TRANSFER'
    ? handleTransferSubmit
    : type === 'CARD'
      ? handleCCExpenseSubmit
      : handleBankSubmit

  const cannotSave = loading
    || (type === 'TRANSFER' && accounts.length < 2)
    || (type === 'CARD' && cards.length === 0)

  const renderBankForm = () => (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <Field label="Valor">
        <input type="number" inputMode="decimal" step="0.01" placeholder="0,00" value={transForm.amount} onChange={(event) => setTransForm({ ...transForm, amount: event.target.value })} className="app-input" required autoFocus />
      </Field>
      <Field label="Data">
        <input type="date" value={transForm.date} onChange={(event) => setTransForm({ ...transForm, date: event.target.value })} className="app-input" required />
      </Field>
      <Field label="Categoria">
        <select value={transForm.category} onChange={(event) => setTransForm({ ...transForm, category: event.target.value })} className="app-select" required>
          <option value="">Selecione...</option>
          {filterCategoryOptions(categoryOptions, transForm.type).map((category) => (
            <option key={category.id} value={category.name}>{category.label}</option>
          ))}
        </select>
      </Field>
      <Field label="Descrição">
        <input type="text" placeholder={transForm.type === 'INCOME' ? 'Ex: Salário' : 'Ex: Mercado'} value={transForm.description} onChange={(event) => setTransForm({ ...transForm, description: event.target.value })} className="app-input" required />
      </Field>
      <Field label="Conta" className="sm:col-span-2">
        <select value={transForm.account_id || defaultAccountId} onChange={(event) => setTransForm({ ...transForm, account_id: event.target.value })} className="app-select" required>
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>{account.name}</option>
          ))}
        </select>
        {!loading && accounts.length === 0 ? (
          <span className="block text-sm text-zinc-600">Nenhuma conta. {settingsLink('contas', 'Cadastre em Ajustes')}.</span>
        ) : null}
      </Field>
    </div>
  )

  const renderTransferForm = () => (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <Field label="De">
        <select value={transferForm.account_id} onChange={(event) => setTransferForm({ ...transferForm, account_id: event.target.value })} className="app-select" required>
          <option value="">Selecione...</option>
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>{account.name}</option>
          ))}
        </select>
      </Field>
      <Field label="Para">
        <select value={transferForm.transfer_account_id} onChange={(event) => setTransferForm({ ...transferForm, transfer_account_id: event.target.value })} className="app-select" required>
          <option value="">Selecione...</option>
          {accounts.filter((account) => account.id !== transferForm.account_id).map((account) => (
            <option key={account.id} value={account.id}>{account.name}</option>
          ))}
        </select>
      </Field>
      <Field label="Valor">
        <input type="number" inputMode="decimal" step="0.01" placeholder="0,00" value={transferForm.amount} onChange={(event) => setTransferForm({ ...transferForm, amount: event.target.value })} className="app-input" required />
      </Field>
      <Field label="Data">
        <input type="date" value={transferForm.date} onChange={(event) => setTransferForm({ ...transferForm, date: event.target.value })} className="app-input" required />
      </Field>
      <Field label="Descrição" hint="Opcional" className="sm:col-span-2">
        <input type="text" placeholder="Ex: Reserva do mês" value={transferForm.description} onChange={(event) => setTransferForm({ ...transferForm, description: event.target.value })} className="app-input" />
      </Field>
      {!loading && accounts.length < 2 ? (
        <p className="text-sm text-zinc-600 sm:col-span-2">
          Cadastre uma segunda conta em {settingsLink('contas', 'Ajustes › Contas')} para transferir.
        </p>
      ) : null}
    </div>
  )

  const renderCardForm = () => {
    if (!loading && cards.length === 0) {
      return (
        <EmptyState
          icon={CreditCard}
          title="Cadastre um cartão primeiro"
          message="Os cartões ficam em Ajustes. Depois disso, a compra no cartão fica disponível aqui."
          action={settingsLink('cartoes', 'Cadastrar cartão em Ajustes')}
          className="min-h-40"
        />
      )
    }
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Valor total">
          <input type="number" inputMode="decimal" step="0.01" placeholder="0,00" value={expenseForm.total_amount} onChange={(event) => setExpenseForm({ ...expenseForm, total_amount: event.target.value })} className="app-input" required />
        </Field>
        <Field label="Parcelas">
          <input type="number" min="1" max="48" value={expenseForm.installments} onChange={(event) => setExpenseForm({ ...expenseForm, installments: event.target.value })} className="app-input" required />
        </Field>
        <Field label="Categoria">
          <select value={expenseForm.category} onChange={(event) => setExpenseForm({ ...expenseForm, category: event.target.value })} className="app-select" required>
            <option value="">Selecione...</option>
            {filterCategoryOptions(categoryOptions, 'EXPENSE').map((category) => (
              <option key={category.id} value={category.name}>{category.label}</option>
            ))}
          </select>
        </Field>
        <Field label="Descrição">
          <input type="text" placeholder="O que você comprou?" value={expenseForm.description} onChange={(event) => setExpenseForm({ ...expenseForm, description: event.target.value })} className="app-input" required />
        </Field>
        <Field label="Cartão">
          <select value={expenseForm.card_id} onChange={(event) => setExpenseForm({ ...expenseForm, card_id: event.target.value })} className="app-select" required>
            <option value="">Selecione...</option>
            {cards.map((card) => <option key={card.id} value={card.id}>{card.name} (vence dia {card.due_day})</option>)}
          </select>
        </Field>
        <Field label="Data da compra">
          <input type="date" value={expenseForm.purchase_date} onChange={(event) => setExpenseForm({ ...expenseForm, purchase_date: event.target.value })} className="app-input" required />
        </Field>
      </div>
    )
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="Novo lançamento"
      footer={(
        <div className="flex gap-2 sm:justify-end">
          <Button type="button" variant="secondary" size="lg" onClick={onClose} className="flex-1 sm:flex-none">Cancelar</Button>
          <Button type="submit" form={FORM_ID} size="lg" loading={saving} disabled={cannotSave} className="flex-1 sm:flex-none">Salvar</Button>
        </div>
      )}
    >
      <form id={FORM_ID} onSubmit={onSubmit} className="space-y-4">
        <SegmentedControl items={NEW_ENTRY_TYPES} value={type} onChange={handleTypeChange} className="w-full flex-wrap" />
        <AlertMessage tone="danger" message={error} onDismiss={() => setError('')} />
        {type === 'TRANSFER' ? renderTransferForm() : type === 'CARD' ? renderCardForm() : renderBankForm()}
      </form>
    </Sheet>
  )
}
