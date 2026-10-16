import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowDownCircle, ArrowLeftRight, ArrowUpCircle, CreditCard } from 'lucide-react'
import { accountsApi, categoriesApi, creditCardsApi } from '../lib/dataApi'
import { createEntry, flush, updateItem } from '../lib/outbox'
import {
  buildCategoryOptions,
  filterCategoryOptions,
  getLocalDateString,
  parseLocalDate,
  pickDefaultAccountId,
} from '../pages/lancamentos/helpers'
import { AlertMessage, Button, cx, EmptyState, Field, Sheet } from './ui'
import { formatCurrency } from '../lib/format'
import { toast } from '../lib/toast'
import { useQuery } from '../lib/queries'

const FORM_ID = 'new-entry-form'

// `short` e o rotulo do botao: os quatro cabem lado a lado num celular de 360px.
export const NEW_ENTRY_TYPES = [
  { value: 'EXPENSE', label: 'Despesa', short: 'Despesa', icon: ArrowDownCircle },
  { value: 'INCOME', label: 'Receita', short: 'Receita', icon: ArrowUpCircle },
  { value: 'TRANSFER', label: 'Transferência', short: 'Transferir', icon: ArrowLeftRight },
  { value: 'CARD', label: 'Compra no cartão', short: 'Cartão', icon: CreditCard },
]

// O valor e o primeiro campo e o maior: e o que se digita assim que o sheet abre.
const AMOUNT_INPUT = 'app-input py-3 text-2xl font-bold tabular'

// Os quatro tipos numa linha so, icone sobre o rotulo, 56px de altura: o
// polegar acerta sem mirar, e o formulario sobe para caber acima do teclado.
function EntryTypePicker({ value, onChange }) {
  return (
    <div role="group" aria-label="Tipo de lançamento" className="grid grid-cols-4 gap-1 rounded-[1.375rem] border border-zinc-200 bg-white p-1">
      {NEW_ENTRY_TYPES.map((item) => {
        const Icon = item.icon
        const active = item.value === value
        return (
          <button
            key={item.value}
            type="button"
            aria-pressed={active}
            aria-label={item.label}
            title={item.label}
            onClick={() => onChange(item.value)}
            className={cx(
              'flex h-14 min-w-0 flex-col items-center justify-center gap-1 rounded-[1.125rem] text-xs font-semibold transition duration-150',
              active ? 'bg-zinc-100 text-zinc-950' : 'text-zinc-600 hover:text-zinc-950'
            )}
          >
            <Icon className="h-5 w-5" aria-hidden="true" />
            <span className="max-w-full truncate px-1">{item.short}</span>
          </button>
        )
      })}
    </div>
  )
}

const settingsLink = (hash, text) => (
  <Link to={`/ajustes#${hash}`} className="font-semibold text-emerald-700 underline-offset-2 hover:underline">{text}</Link>
)

// Defaults (docs/ux-reorganization.md D6): data = hoje, conta = conta padrao,
// cartao = primeiro cartao, 1 parcela.
const NO_ITEMS = []

const emptyBankForm = (type, accountId) => ({ amount: '', date: getLocalDateString(), category: '', description: '', type, account_id: accountId })
const emptyTransferForm = (accountId) => ({ amount: '', date: getLocalDateString(), account_id: accountId, transfer_account_id: '', description: '' })
const emptyExpenseForm = (cardId) => ({ card_id: cardId, category: '', description: '', total_amount: '', purchase_date: getLocalDateString(), installments: '1' })

// O "+ Novo": todos os formularios de lancamento num lugar so. Os handlers de
// envio vieram de Transactions.jsx (banco, transferencia) e de Carteira.jsx
// (compra no cartao, via POST /api/cc-expenses/purchases — a regra da fatura
// fica no backend). So a area bancaria: operacao de investimento se registra
// em Investimentos, onde o "+ Novo" abre o InvestmentLaunchModal (Layout.jsx).
//
// `editingItem` e um item da fila de envio (lib/outbox.js) aberto para
// corrigir: o sheet abre preenchido e Salvar regrava o item, sem criar outro.
export default function NewEntrySheet({ open, initialType = 'EXPENSE', editingItem = null, onClose, onSaved }) {
  const [type, setType] = useState(initialType)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  // Contas, cartoes e categorias pelo cache compartilhado (lib/queries.js):
  // qualquer gravacao o invalida, entao o que mudou em Ajustes ja chega aqui.
  // Buscadas com o app aberto, nao so com o sheet: sem servidor o "+ Novo"
  // precisa delas no cache guardado mesmo que nunca tenha sido aberto antes.
  const accountsQuery = useQuery({ queryKey: ['contas', 'ativas'], queryFn: () => accountsApi.list() })
  const categoriesQuery = useQuery({ queryKey: ['categorias', 'ativas'], queryFn: () => categoriesApi.list() })
  const cardsQuery = useQuery({ queryKey: ['cartoes'], queryFn: () => creditCardsApi.list() })
  const accounts = accountsQuery.data || NO_ITEMS
  const categories = categoriesQuery.data || NO_ITEMS
  const cards = cardsQuery.data || NO_ITEMS
  const loading = open && (accountsQuery.isPending || categoriesQuery.isPending || cardsQuery.isPending)
  // Sem servidor, as listas vem do cache guardado no aparelho: a busca falha,
  // mas ha o que mostrar, e o formulario segue valendo.
  const missingLists = !accountsQuery.data || !categoriesQuery.data || !cardsQuery.data
  const loadError = missingLists ? accountsQuery.error || categoriesQuery.error || cardsQuery.error : null

  const [transForm, setTransForm] = useState(() => emptyBankForm('EXPENSE', ''))
  const [transferForm, setTransferForm] = useState(() => emptyTransferForm(''))
  const [expenseForm, setExpenseForm] = useState(() => emptyExpenseForm(''))

  const defaultAccountId = useMemo(() => pickDefaultAccountId(accounts), [accounts])
  const categoryOptions = useMemo(() => buildCategoryOptions(categories), [categories])

  // Ao abrir: tipo pedido e formularios limpos com a data de hoje.
  useEffect(() => {
    if (!open) return
    setError('')
    setTransForm(emptyBankForm(initialType === 'INCOME' ? 'INCOME' : 'EXPENSE', ''))
    setTransferForm(emptyTransferForm(''))
    setExpenseForm(emptyExpenseForm(''))
    if (!editingItem) {
      setType(initialType || 'EXPENSE')
      return
    }
    // Item da fila: o payload guardado tem os mesmos campos do formulario.
    const { kind, payload } = editingItem
    setType(kind)
    if (kind === 'TRANSFER') {
      setTransferForm({ ...emptyTransferForm(''), ...payload, amount: String(payload.amount ?? '') })
    } else if (kind === 'CARD') {
      setExpenseForm({
        ...emptyExpenseForm(''),
        ...payload,
        total_amount: String(payload.total_amount ?? ''),
        installments: String(payload.installments ?? '1'),
      })
    } else {
      setTransForm({ ...emptyBankForm(kind, ''), ...payload, type: kind, amount: String(payload.amount ?? ''), account_id: payload.account_id || '' })
    }
  }, [open, initialType, editingItem])

  // Conta e cartao padrao assim que a lista chega (ou ja estava no cache).
  useEffect(() => {
    if (!open) return
    setTransForm((current) => ({ ...current, account_id: current.account_id || defaultAccountId }))
    setTransferForm((current) => ({ ...current, account_id: current.account_id || defaultAccountId }))
    setExpenseForm((current) => ({ ...current, card_id: current.card_id || cards[0]?.id || '' }))
  }, [open, initialType, defaultAccountId, cards])

  useEffect(() => {
    if (open && loadError) setError(loadError.message || 'Não foi possível carregar contas, cartões e categorias.')
  }, [open, loadError])

  const handleTypeChange = (nextType) => {
    setType(nextType)
    setError('')
    if (nextType === 'EXPENSE' || nextType === 'INCOME') {
      // A categoria depende do tipo (receita x despesa); o resto do que foi digitado fica.
      setTransForm((current) => (current.type === nextType ? current : { ...current, type: nextType, category: '' }))
    }
  }

  // Fora do Extrato nada na tela muda depois de salvar; o toast confirma.
  const finish = async (message, options) => {
    await onSaved?.()
    onClose()
    toast(message, options)
  }

  // Grava no servidor ou, se o pedido nao chegou, na fila de envio. O item
  // aberto para correcao e regravado na fila com o mesmo client_id.
  const submitEntry = async (kind, payload, label) => {
    if (editingItem) {
      await updateItem(editingItem.client_id, { kind, payload })
      flush().catch(() => {})
      await finish(`${label} pendente atualizada.`, { tone: 'info' })
      return
    }
    const result = await createEntry(kind, payload)
    if (result.queued) {
      await finish(`Sem conexão: ${label.charAt(0).toLowerCase()}${label.slice(1)} guardada neste aparelho. Ela é enviada quando o servidor responder.`, { tone: 'info', duration: 6000 })
      return
    }
    await finish(`${label} registrada.`)
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
      await submitEntry(transForm.type, {
        amount,
        date: transForm.date,
        category: transForm.category,
        description: transForm.description,
        type: transForm.type,
        account_id: transForm.account_id || defaultAccountId || undefined,
      }, `${transForm.type === 'INCOME' ? 'Receita' : 'Despesa'} de ${formatCurrency(amount)}`)
    } catch (submitError) {
      setError(submitError.message || 'Não foi possível criar o lançamento.')
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
      await submitEntry('TRANSFER', {
        amount,
        date: transferForm.date,
        account_id: transferForm.account_id,
        transfer_account_id: transferForm.transfer_account_id,
        description: transferForm.description,
      }, `Transferência de ${formatCurrency(amount)}`)
    } catch (submitError) {
      setError(submitError.message || 'Não foi possível registrar a transferência.')
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
      setError('Preencha a compra no cartão com valores válidos.')
      return
    }

    setSaving(true)
    setError('')
    try {
      // O parcelamento e a fatura de cada parcela sao calculados no backend
      // (POST /api/cc-expenses/purchases), junto do cartao que define a regra.
      await submitEntry('CARD', {
        card_id: expenseForm.card_id,
        category: expenseForm.category,
        description: expenseForm.description,
        total_amount: totalAmount,
        purchase_date: expenseForm.purchase_date,
        installments: installmentsCount,
      }, installmentsCount > 1
        ? `Compra no cartão de ${formatCurrency(totalAmount)} em ${installmentsCount}x`
        : `Compra no cartão de ${formatCurrency(totalAmount)}`)
    } catch (submitError) {
      setError(submitError.message || 'Não foi possível criar a compra no cartão.')
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

  // Ordem do formulario = ordem do que se digita: valor, categoria, descricao.
  // Data e conta quase sempre ficam no padrao, entao vao no fim, lado a lado.
  const renderBankForm = () => (
    <div className="grid grid-cols-2 gap-x-3 gap-y-4">
      <Field label="Valor" className="col-span-2">
        <input type="number" inputMode="decimal" step="0.01" placeholder="0,00" value={transForm.amount} onChange={(event) => setTransForm({ ...transForm, amount: event.target.value })} className={AMOUNT_INPUT} required autoFocus />
      </Field>
      <Field label="Categoria" className="col-span-2">
        <select value={transForm.category} onChange={(event) => setTransForm({ ...transForm, category: event.target.value })} className="app-select" required>
          <option value="">Selecione...</option>
          {filterCategoryOptions(categoryOptions, transForm.type).map((category) => (
            <option key={category.id} value={category.name}>{category.label}</option>
          ))}
        </select>
      </Field>
      <Field label="Descrição" className="col-span-2">
        <input type="text" placeholder={transForm.type === 'INCOME' ? 'Ex: Salário' : 'Ex: Mercado'} value={transForm.description} onChange={(event) => setTransForm({ ...transForm, description: event.target.value })} className="app-input" required />
      </Field>
      <Field label="Data" className="min-w-0">
        <input type="date" value={transForm.date} onChange={(event) => setTransForm({ ...transForm, date: event.target.value })} className="app-input" required />
      </Field>
      <Field label="Conta" className="min-w-0">
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
    <div className="grid grid-cols-2 gap-x-3 gap-y-4">
      <Field label="Valor" className="col-span-2">
        <input type="number" inputMode="decimal" step="0.01" placeholder="0,00" value={transferForm.amount} onChange={(event) => setTransferForm({ ...transferForm, amount: event.target.value })} className={AMOUNT_INPUT} required autoFocus />
      </Field>
      <Field label="De" className="min-w-0">
        <select value={transferForm.account_id} onChange={(event) => setTransferForm({ ...transferForm, account_id: event.target.value })} className="app-select" required>
          <option value="">Selecione...</option>
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>{account.name}</option>
          ))}
        </select>
      </Field>
      <Field label="Para" className="min-w-0">
        <select value={transferForm.transfer_account_id} onChange={(event) => setTransferForm({ ...transferForm, transfer_account_id: event.target.value })} className="app-select" required>
          <option value="">Selecione...</option>
          {accounts.filter((account) => account.id !== transferForm.account_id).map((account) => (
            <option key={account.id} value={account.id}>{account.name}</option>
          ))}
        </select>
      </Field>
      <Field label="Data" className="col-span-2">
        <input type="date" value={transferForm.date} onChange={(event) => setTransferForm({ ...transferForm, date: event.target.value })} className="app-input" required />
      </Field>
      <Field label="Descrição" hint="Opcional" className="col-span-2">
        <input type="text" placeholder="Ex: Reserva do mês" value={transferForm.description} onChange={(event) => setTransferForm({ ...transferForm, description: event.target.value })} className="app-input" />
      </Field>
      {!loading && accounts.length < 2 ? (
        <p className="col-span-2 text-sm text-zinc-600">
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
      <div className="grid grid-cols-[minmax(0,1fr)_6rem] gap-x-3 gap-y-4">
        <Field label="Valor total" className="min-w-0">
          <input type="number" inputMode="decimal" step="0.01" placeholder="0,00" value={expenseForm.total_amount} onChange={(event) => setExpenseForm({ ...expenseForm, total_amount: event.target.value })} className={AMOUNT_INPUT} required autoFocus />
        </Field>
        <Field label="Parcelas">
          <input type="number" inputMode="numeric" min="1" max="48" value={expenseForm.installments} onChange={(event) => setExpenseForm({ ...expenseForm, installments: event.target.value })} className={cx(AMOUNT_INPUT, 'text-center')} required />
        </Field>
        <Field label="Categoria" className="col-span-2">
          <select value={expenseForm.category} onChange={(event) => setExpenseForm({ ...expenseForm, category: event.target.value })} className="app-select" required>
            <option value="">Selecione...</option>
            {filterCategoryOptions(categoryOptions, 'EXPENSE').map((category) => (
              <option key={category.id} value={category.name}>{category.label}</option>
            ))}
          </select>
        </Field>
        <Field label="Descrição" className="col-span-2">
          <input type="text" placeholder="O que você comprou?" value={expenseForm.description} onChange={(event) => setExpenseForm({ ...expenseForm, description: event.target.value })} className="app-input" required />
        </Field>
        <Field label="Cartão" className="col-span-2">
          <select value={expenseForm.card_id} onChange={(event) => setExpenseForm({ ...expenseForm, card_id: event.target.value })} className="app-select" required>
            <option value="">Selecione...</option>
            {cards.map((card) => <option key={card.id} value={card.id}>{card.name} (vence dia {card.due_day})</option>)}
          </select>
        </Field>
        <Field label="Data da compra" className="col-span-2">
          <input type="date" value={expenseForm.purchase_date} onChange={(event) => setExpenseForm({ ...expenseForm, purchase_date: event.target.value })} className="app-input" required />
        </Field>
      </div>
    )
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={editingItem ? 'Corrigir lançamento pendente' : 'Novo lançamento'}
      footer={(
        <div className="flex gap-2 sm:justify-end">
          <Button type="button" variant="secondary" size="lg" onClick={onClose} className="flex-1 sm:flex-none">Cancelar</Button>
          <Button type="submit" form={FORM_ID} size="lg" loading={saving} disabled={cannotSave} className="flex-1 sm:flex-none">Salvar</Button>
        </div>
      )}
    >
      <form id={FORM_ID} onSubmit={onSubmit} className="space-y-4">
        <EntryTypePicker value={type} onChange={handleTypeChange} />
        <AlertMessage tone="danger" message={error} onDismiss={() => setError('')} />
        {type === 'TRANSFER' ? renderTransferForm() : type === 'CARD' ? renderCardForm() : renderBankForm()}
      </form>
    </Sheet>
  )
}
