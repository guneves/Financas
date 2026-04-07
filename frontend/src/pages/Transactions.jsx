import { useMemo, useState, useEffect } from 'react'
import { supabase } from '../lib/supabaseClient'
import { Wallet, Trash2, CreditCard, Calendar, CheckCircle } from 'lucide-react'

const CATEGORY_OPTIONS = ['Receita', 'Investimento', 'Alimentação', 'Moradia', 'Transporte', 'Saúde', 'Educação', 'Lazer', 'Serviços', 'Outros']

function getNow() {
  return new Date()
}

function getLocalDateString(date = getNow()) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function formatDateBR(dateString) {
  if (!dateString) return ''
  const [year, month, day] = dateString.split('-')
  return `${day}/${month}/${year}`
}

function parseLocalDate(dateString) {
  if (!dateString) return null
  const [year, month, day] = dateString.split('-').map(Number)
  return new Date(year, month - 1, day)
}

function parseInstallmentInfo(value) {
  if (!value || typeof value !== 'string' || !value.includes('/')) {
    return { current: 1, total: 1 }
  }

  const [current, total] = value.split('/').map(Number)

  return {
    current: Number.isFinite(current) ? current : 1,
    total: Number.isFinite(total) ? total : 1
  }
}

function getPurchaseGroupKey(expense) {
  const installment = parseInstallmentInfo(expense.installment_info)
  return [
    expense.card_id || 'sem-cartao',
    expense.description || 'sem-descricao',
    expense.purchase_date || 'sem-data',
    expense.category || 'sem-categoria',
    Number(parseFloat(expense.amount || 0).toFixed(2)),
    installment.total
  ].join('|')
}

function formatInvoiceLabel(month, year) {
  return `${String(month).padStart(2, '0')}/${year}`
}

function formatCurrency(value) {
  return `R$ ${Number(value || 0).toFixed(2)}`
}

export default function Transactions() {
  const [activeTab, setActiveTab] = useState('CONTA')

  const [transactions, setTransactions] = useState(() => {
    const saved = localStorage.getItem('@financeMVP:transactions')
    return saved ? JSON.parse(saved) : []
  })
  const [balance, setBalance] = useState(() => {
    const saved = localStorage.getItem('@financeMVP:balance')
    return saved ? parseFloat(saved) : 0
  })

  const [cards, setCards] = useState(() => {
    const saved = localStorage.getItem('@financeMVP:cards')
    return saved ? JSON.parse(saved) : []
  })
  const [ccExpenses, setCcExpenses] = useState(() => {
    const saved = localStorage.getItem('@financeMVP:ccExpenses')
    return saved ? JSON.parse(saved) : []
  })
  const [projectedBalanceGlobal, setProjectedBalanceGlobal] = useState(() => {
    const saved = localStorage.getItem('@financeMVP:projectedBalanceGlobal')
    return saved ? parseFloat(saved) : 0
  })
  const [projectedBalanceNextMonth, setProjectedBalanceNextMonth] = useState(() => {
    const saved = localStorage.getItem('@financeMVP:projectedBalanceNextMonth')
    return saved ? parseFloat(saved) : 0
  })

  const [transForm, setTransForm] = useState({ amount: '', date: '', category: '', description: '', type: 'EXPENSE' })
  const [cardForm, setCardForm] = useState({ name: '', due_day: '' })
  const [expenseForm, setExpenseForm] = useState({ card_id: '', category: '', description: '', total_amount: '', purchase_date: '', installments: '1' })

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return

    const { data: tData } = await supabase.from('transactions').select('*').order('date', { ascending: false })
    let currentBalance = 0
    if (tData) {
      setTransactions(tData)
      localStorage.setItem('@financeMVP:transactions', JSON.stringify(tData))

      currentBalance = tData.reduce((acc, curr) => curr.type === 'INCOME' ? acc + parseFloat(curr.amount) : acc - parseFloat(curr.amount), 0)
      setBalance(currentBalance)
      localStorage.setItem('@financeMVP:balance', currentBalance.toString())
    }

    const { data: cData } = await supabase.from('credit_cards').select('*')
    if (cData) {
      setCards(cData)
      localStorage.setItem('@financeMVP:cards', JSON.stringify(cData))
    }

    const { data: ccData } = await supabase
      .from('cc_expenses')
      .select(`*, credit_cards(name, due_day)`)
      .eq('status', 'OPEN')
      .order('invoice_year', { ascending: true })
      .order('invoice_month', { ascending: true })

    if (ccData) {
      setCcExpenses(ccData)
      localStorage.setItem('@financeMVP:ccExpenses', JSON.stringify(ccData))

      const today = getNow()
      const currentMonth = today.getMonth() + 1
      const currentYear = today.getFullYear()

      let nextMonth = currentMonth + 1
      let nextYear = currentYear
      if (nextMonth > 12) {
        nextMonth = 1
        nextYear++
      }

      const totalOpenCredit = ccData.reduce((acc, curr) => acc + parseFloat(curr.amount), 0)
      const projGlobal = currentBalance - totalOpenCredit
      setProjectedBalanceGlobal(projGlobal)
      localStorage.setItem('@financeMVP:projectedBalanceGlobal', projGlobal.toString())

      const creditUpToNextMonth = ccData.reduce((acc, curr) => {
        const isPastOrCurrent = curr.invoice_year < currentYear || (curr.invoice_year === currentYear && curr.invoice_month <= currentMonth)
        const isNextMonth = curr.invoice_year === nextYear && curr.invoice_month === nextMonth

        if (isPastOrCurrent || isNextMonth) {
          return acc + parseFloat(curr.amount)
        }
        return acc
      }, 0)

      const projNextMonth = currentBalance - creditUpToNextMonth
      setProjectedBalanceNextMonth(projNextMonth)
      localStorage.setItem('@financeMVP:projectedBalanceNextMonth', projNextMonth.toString())
    }
  }

  const openInvoicesByCard = useMemo(() => {
    const groupedByCard = ccExpenses.reduce((acc, expense) => {
      const cardKey = expense.card_id || 'sem-cartao'
      const invoiceKey = `${expense.invoice_year}-${String(expense.invoice_month).padStart(2, '0')}`

      if (!acc[cardKey]) {
        acc[cardKey] = {
          cardId: expense.card_id,
          cardName: expense.credit_cards?.name || 'Cartão',
          dueDay: expense.credit_cards?.due_day,
          invoices: {}
        }
      }

      if (!acc[cardKey].invoices[invoiceKey]) {
        acc[cardKey].invoices[invoiceKey] = {
          invoiceKey,
          invoiceMonth: expense.invoice_month,
          invoiceYear: expense.invoice_year,
          total: 0,
          purchases: {}
        }
      }

      acc[cardKey].invoices[invoiceKey].total += parseFloat(expense.amount)

      const purchaseKey = getPurchaseGroupKey(expense)
      const installment = parseInstallmentInfo(expense.installment_info)

      if (!acc[cardKey].invoices[invoiceKey].purchases[purchaseKey]) {
        acc[cardKey].invoices[invoiceKey].purchases[purchaseKey] = {
          purchaseKey,
          card_id: expense.card_id,
          description: expense.description,
          category: expense.category || 'Outros',
          purchase_date: expense.purchase_date,
          amount: parseFloat(expense.amount),
          installmentCurrent: installment.current,
          installmentTotal: installment.total
        }
      }
    return acc
    }, {})

    return Object.values(groupedByCard)
      .map((cardGroup) => ({
        ...cardGroup,
        invoices: Object.values(cardGroup.invoices).sort((a, b) => {
          if (a.invoiceYear !== b.invoiceYear) return a.invoiceYear - b.invoiceYear
          return a.invoiceMonth - b.invoiceMonth
        }).map((invoice) => ({
          ...invoice,
          purchases: Object.values(invoice.purchases).sort((a, b) => a.description.localeCompare(b.description))
        }))
      }))
      .sort((a, b) => a.cardName.localeCompare(b.cardName))
  }, [ccExpenses])

  const handleBankSubmit = async (e) => {
    e.preventDefault()
    const { data: { user } } = await supabase.auth.getUser()
    await supabase.from('transactions').insert([{
      user_id: user.id,
      amount: parseFloat(transForm.amount),
      date: transForm.date,
      category: transForm.category,
      description: transForm.description,
      type: transForm.type
    }])
    setTransForm({ amount: '', date: '', category: '', description: '', type: 'EXPENSE' })
    fetchData()
  }

  const handleCreateCard = async (e) => {
    e.preventDefault()
    const { data: { user } } = await supabase.auth.getUser()
    await supabase.from('credit_cards').insert([{ user_id: user.id, name: cardForm.name, due_day: parseInt(cardForm.due_day) }])
    setCardForm({ name: '', due_day: '' })
    fetchData()
  }

  const handleCCExpenseSubmit = async (e) => {
    e.preventDefault()
    const { data: { user } } = await supabase.auth.getUser()
    const totalAmount = parseFloat(expenseForm.total_amount)
    const installmentsCount = parseInt(expenseForm.installments)
    const amountPerInstallment = totalAmount / installmentsCount

    const purchaseDate = parseLocalDate(expenseForm.purchase_date)
    let currentMonth = purchaseDate.getMonth() + 2
    let currentYear = purchaseDate.getFullYear()

    const inserts = []
    for (let i = 1; i <= installmentsCount; i++) {
      inserts.push({
        user_id: user.id,
        card_id: expenseForm.card_id,
        category: expenseForm.category,
        description: expenseForm.description,
        amount: amountPerInstallment.toFixed(2),
        purchase_date: expenseForm.purchase_date,
        invoice_month: currentMonth,
        invoice_year: currentYear,
        installment_info: `${i}/${installmentsCount}`,
        status: 'OPEN'
      })
      currentMonth++
      if (currentMonth > 12) {
        currentMonth = 1
        currentYear++
      }
    }

    await supabase.from('cc_expenses').insert(inserts)
    setExpenseForm({ card_id: cards[0]?.id || '', category: '', description: '', total_amount: '', purchase_date: '', installments: '1' })
    fetchData()
  }

  const handlePayInvoice = async (invoice, cardGroup) => {
    if (!window.confirm(`Deseja pagar a fatura ${formatInvoiceLabel(invoice.invoiceMonth, invoice.invoiceYear)} do cartão ${cardGroup.cardName} no valor de ${formatCurrency(invoice.total)}?`)) return
    const { data: { user } } = await supabase.auth.getUser()

    await supabase.from('transactions').insert([{
      user_id: user.id,
      type: 'EXPENSE',
      amount: Number(invoice.total.toFixed(2)),
      date: getLocalDateString(),
      category: `Pagamento Fatura ${cardGroup.cardName}`,
      description: `Fatura ${formatInvoiceLabel(invoice.invoiceMonth, invoice.invoiceYear)}`
    }])

    await supabase
      .from('cc_expenses')
      .update({ status: 'PAID' })
      .eq('card_id', cardGroup.cardId)
      .eq('invoice_month', invoice.invoiceMonth)
      .eq('invoice_year', invoice.invoiceYear)
      .eq('status', 'OPEN')

    fetchData()
  }

  const handleDeleteTransaction = async (id) => {
    if (!window.confirm('Deseja realmente eliminar esta transação? O saldo será recalculado.')) return
    const { error } = await supabase.from('transactions').delete().eq('id', id)
    if (!error) fetchData()
  }

  const handleDeleteCCPurchase = async (purchase) => {
    if (!window.confirm(`Deseja excluir a compra "${purchase.description}" e eliminar todas as faturas vinculadas a ela?`)) return

    const { data: candidates, error: selectError } = await supabase
      .from('cc_expenses')
      .select('id, amount, installment_info')
      .eq('card_id', purchase.card_id)
      .eq('description', purchase.description)
      .eq('purchase_date', purchase.purchase_date)
      .eq('category', purchase.category)

    if (selectError) {
      alert('Erro ao localizar a compra: ' + selectError.message)
      return
    }

    const idsToDelete = (candidates || [])
      .filter((item) => {
        const installment = parseInstallmentInfo(item.installment_info)
        return Number(parseFloat(item.amount).toFixed(2)) === Number(parseFloat(purchase.amount).toFixed(2))
          && installment.total === purchase.installmentTotal
      })
      .map((item) => item.id)

    if (idsToDelete.length === 0) {
      alert('Nenhuma fatura vinculada foi encontrada para essa compra.')
      return
    }

    const { error: deleteError } = await supabase
      .from('cc_expenses')
      .delete()
      .in('id', idsToDelete)

    if (deleteError) {
      alert('Erro ao excluir a compra parcelada: ' + deleteError.message)
      return
    }

    fetchData()
  }

  const handleDeleteCard = async (id, name) => {
    if (!window.confirm(`ATENÇÃO: Deseja realmente excluir o cartão "${name}"?\nIsso apagará TODAS as faturas (abertas e pagas) vinculadas a ele. Esta ação não pode ser desfeita.`)) return

    await supabase.from('cc_expenses').delete().eq('card_id', id)
    const { error } = await supabase.from('credit_cards').delete().eq('id', id)

    if (error) {
      alert('Erro ao excluir cartão: ' + error.message)
    } else {
      fetchData()
    }
  }

  const getInvoiceStatus = (year, month, dueDay) => {
    const today = getNow()
    const dueDate = new Date(year, month - 1, dueDay)
    if (today > dueDate) return <span className="text-red-600 font-bold text-xs bg-red-100 px-2 py-1 rounded-md">Em Atraso</span>
    return <span className="text-yellow-600 font-bold text-xs bg-yellow-100 px-2 py-1 rounded-md">Aberta</span>
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex flex-col md:flex-row gap-6">
        <div className="flex-1 space-y-4">
          <h1 className="text-3xl font-bold text-slate-800">Movimentações</h1>
          <div className="flex bg-slate-200 p-1 rounded-lg w-fit">
            <button onClick={() => setActiveTab('CONTA')} className={`px-4 py-2 rounded-md font-medium transition ${activeTab === 'CONTA' ? 'bg-white shadow-sm text-blue-600' : 'text-slate-600 hover:bg-slate-300'}`}>Conta Corrente</button>
            <button onClick={() => setActiveTab('CARTOES')} className={`px-4 py-2 rounded-md font-medium transition ${activeTab === 'CARTOES' ? 'bg-white shadow-sm text-blue-600' : 'text-slate-600 hover:bg-slate-300'}`}>Cartões de Crédito</button>
          </div>
        </div>

        <div className="flex gap-4 overflow-x-auto pb-4">
          <div className="bg-slate-900 text-white p-5 rounded-2xl shadow-lg min-w-[200px]">
            <p className="text-sm font-medium text-slate-400">Saldo Atual (Real)</p>
            <p className={`text-2xl font-bold ${balance >= 0 ? 'text-white' : 'text-red-400'}`}>R$ {balance.toFixed(2)}</p>
          </div>

          <div className="bg-white border border-blue-200 p-5 rounded-2xl shadow-sm min-w-[220px]">
            <p className="text-sm font-medium text-blue-600">Proj. (Até Próx. Mês)</p>
            <p className={`text-2xl font-bold ${projectedBalanceNextMonth >= 0 ? 'text-blue-600' : 'text-red-500'}`} title="Desconta faturas deste mês e do próximo.">
              R$ {projectedBalanceNextMonth.toFixed(2)}
            </p>
          </div>

          <div className="bg-slate-50 border border-slate-200 p-5 rounded-2xl shadow-sm min-w-[220px]">
            <p className="text-sm font-medium text-slate-500">Proj. (Global)</p>
            <p className={`text-2xl font-bold ${projectedBalanceGlobal >= 0 ? 'text-slate-800' : 'text-red-500'}`} title="Desconta todas as faturas futuras (incluindo parcelas longas).">
              R$ {projectedBalanceGlobal.toFixed(2)}
            </p>
          </div>
        </div>
      </div>

      {activeTab === 'CONTA' && (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
          <form onSubmit={handleBankSubmit} className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 grid grid-cols-1 md:grid-cols-6 gap-4">
            <select value={transForm.type} onChange={e => setTransForm({ ...transForm, type: e.target.value })} className="p-2 border rounded-lg bg-white">
              <option value="EXPENSE">Saída Bancária (-)</option>
              <option value="INCOME">Entrada Bancária (+)</option>
            </select>
            <input type="number" step="0.01" placeholder="Valor (R$)" value={transForm.amount} onChange={e => setTransForm({ ...transForm, amount: e.target.value })} className="p-2 border rounded-lg" required />
            <input type="date" value={transForm.date} onChange={e => setTransForm({ ...transForm, date: e.target.value })} className="p-2 border rounded-lg" required />

            <select value={transForm.category} onChange={e => setTransForm({ ...transForm, category: e.target.value })} className="p-2 border rounded-lg bg-white" required>
              <option value="">Selecione a Categoria...</option>
              {CATEGORY_OPTIONS.map((category) => (
                <option key={category} value={category}>{category}</option>
              ))}
            </select>

            <input type="text" placeholder="Descrição (Ex: Mercado)" value={transForm.description} onChange={e => setTransForm({ ...transForm, description: e.target.value })} className="p-2 border rounded-lg" required />
            <button type="submit" className="bg-blue-600 text-white rounded-lg py-2 hover:bg-blue-700">Lançar</button>
          </form>

          <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-slate-50 border-b text-slate-600 text-sm">
                  <th className="p-4">Data</th>
                  <th className="p-4">Descrição</th>
                  <th className="p-4">Movimentação</th>
                  <th className="p-4">Valor</th>
                  <th className="p-4 text-right">Ação</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map(t => (
                  <tr key={t.id} className="border-b border-slate-50 hover:bg-slate-50">
                    <td className="p-4 text-slate-600">{formatDateBR(t.date)}</td>
                    <td className="p-4 font-medium">{t.category}</td>
                    <td className="p-4">{t.type === 'INCOME' ? <span className="text-green-600">Entrada</span> : <span className="text-red-600">Saída</span>}</td>
                    <td className={`p-4 font-bold ${t.type === 'INCOME' ? 'text-green-600' : 'text-slate-800'}`}>{t.type === 'INCOME' ? '+' : '-'} R$ {parseFloat(t.amount).toFixed(2)}</td>
                    <td className="p-4 text-right">
                      <button onClick={() => handleDeleteTransaction(t.id)} className="text-slate-400 hover:text-red-500 transition">
                        <Trash2 size={18} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === 'CARTOES' && (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 col-span-1 h-fit">
              <h3 className="font-bold text-slate-800 mb-4 flex items-center gap-2"><CreditCard size={20} /> Gerenciar Cartões</h3>

              <form onSubmit={handleCreateCard} className="space-y-4 mb-6">
                <input type="text" placeholder="Nome do Cartão (ex: Nubank)" value={cardForm.name} onChange={e => setCardForm({ ...cardForm, name: e.target.value })} className="w-full p-2 border rounded-lg" required />
                <input type="number" min="1" max="31" placeholder="Dia do Vencimento" value={cardForm.due_day} onChange={e => setCardForm({ ...cardForm, due_day: e.target.value })} className="w-full p-2 border rounded-lg" required />
                <button type="submit" className="w-full bg-slate-800 text-white rounded-lg py-2 hover:bg-slate-900 transition">Salvar Cartão</button>
              </form>

              {cards.length > 0 && (
                <div className="pt-4 border-t border-slate-100 space-y-3">
                  <h4 className="text-sm font-semibold text-slate-500">Meus Cartões</h4>
                  <div className="max-h-48 overflow-y-auto space-y-2 pr-1">
                    {cards.map(c => (
                      <div key={c.id} className="flex justify-between items-center bg-slate-50 p-3 rounded-lg border border-slate-100 hover:border-slate-200 transition">
                        <div>
                          <p className="text-sm font-bold text-slate-700">{c.name}</p>
                          <p className="text-xs text-slate-500">Vence dia {c.due_day}</p>
                        </div>
                        <button onClick={() => handleDeleteCard(c.id, c.name)} className="text-slate-400 hover:text-red-500 p-1 transition" title="Excluir Cartão">
                          <Trash2 size={18} />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="bg-white p-6 rounded-2xl shadow-sm border border-blue-200 col-span-2">
              <h3 className="font-bold text-blue-800 mb-4 flex items-center gap-2"><Wallet size={20} /> Lançar Compra no Crédito</h3>
              {cards.length === 0 ? (
                <div className="text-slate-500 bg-slate-50 p-4 rounded-lg">Cadastre um cartão primeiro para lançar compras.</div>
              ) : (
                <form onSubmit={handleCCExpenseSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <select value={expenseForm.card_id} onChange={e => setExpenseForm({ ...expenseForm, card_id: e.target.value })} className="p-2 border rounded-lg" required>
                    <option value="">Selecione o Cartão...</option>
                    {cards.map(c => <option key={c.id} value={c.id}>{c.name} (Vence dia {c.due_day})</option>)}
                  </select>
                  <select value={expenseForm.category} onChange={e => setExpenseForm({ ...expenseForm, category: e.target.value })} className="p-2 border rounded-lg bg-white" required>
                    <option value="">Selecione a Categoria...</option>
                    {CATEGORY_OPTIONS.filter(category => category !== 'Receita').map((category) => (
                      <option key={category} value={category}>{category}</option>
                    ))}
                  </select>
                  <input type="text" placeholder="O que você comprou?" value={expenseForm.description} onChange={e => setExpenseForm({ ...expenseForm, description: e.target.value })} className="p-2 border rounded-lg" required />
                  <input type="number" step="0.01" placeholder="Valor TOTAL da Compra" value={expenseForm.total_amount} onChange={e => setExpenseForm({ ...expenseForm, total_amount: e.target.value })} className="p-2 border rounded-lg" required />
                  <div className="flex gap-2">
                    <input type="date" title="Data da Compra" value={expenseForm.purchase_date} onChange={e => setExpenseForm({ ...expenseForm, purchase_date: e.target.value })} className="flex-1 p-2 border rounded-lg" required />
                    <input type="number" min="1" max="48" title="Qtd de Parcelas" placeholder="Parcelas" value={expenseForm.installments} onChange={e => setExpenseForm({ ...expenseForm, installments: e.target.value })} className="w-24 p-2 border rounded-lg" required />
                  </div>
                  <button type="submit" className="col-span-1 md:col-span-2 bg-blue-600 text-white rounded-lg py-2 hover:bg-blue-700">Registrar Compra Parcelada</button>
                </form>
              )}
            </div>
          </div>

          <h3 className="text-xl font-bold text-slate-800 mt-8 mb-4">Faturas em Aberto</h3>
          <div className="space-y-6">
            {openInvoicesByCard.length === 0 && (
              <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-8 text-center text-slate-500">
                Você não tem nenhuma fatura em aberto. Que paz!
              </div>
            )}

            {openInvoicesByCard.map((cardGroup) => (
              <div key={cardGroup.cardId} className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
                <div className="px-6 py-4 border-b border-slate-100 bg-slate-50 flex items-center justify-between">
                  <div>
                    <h4 className="font-bold text-slate-800">{cardGroup.cardName}</h4>
                    <p className="text-sm text-slate-500">Vence dia {cardGroup.dueDay}</p>
                  </div>
                  <span className="inline-flex items-center rounded-full bg-blue-100 px-3 py-1 text-xs font-medium text-blue-700">
                    {cardGroup.invoices.length} fatura(s) aberta(s)
                  </span>
                </div>

                <div className="divide-y divide-slate-100">
                  {cardGroup.invoices.map((invoice) => (
                    <div key={invoice.invoiceKey} className="p-6 space-y-4">
                      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                        <div>
                          <p className="text-lg font-bold text-slate-800">Fatura {formatInvoiceLabel(invoice.invoiceMonth, invoice.invoiceYear)}</p>
                          <div className="mt-2">
                            {getInvoiceStatus(invoice.invoiceYear, invoice.invoiceMonth, cardGroup.dueDay)}
                          </div>
                        </div>

                        <div className="flex items-center gap-4">
                          <div className="text-right">
                            <p className="text-sm text-slate-500">Total da fatura</p>
                            <p className="text-xl font-bold text-red-500">{formatCurrency(invoice.total)}</p>
                          </div>
                          <button
                            onClick={() => handlePayInvoice(invoice, cardGroup)}
                            className="text-white bg-green-500 hover:bg-green-600 px-4 py-2 rounded-lg text-sm font-medium transition flex items-center gap-2"
                          >
                            <CheckCircle size={16} /> Pagar fatura
                          </button>
                        </div>
                      </div>

                      <div className="space-y-3">
                        {invoice.purchases.map((purchase) => (
                          <div key={purchase.purchaseKey} className="rounded-xl border border-slate-200 p-4">
                            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                              <div>
                                <p className="font-semibold text-slate-800">{purchase.description}</p>
                                <div className="flex flex-wrap gap-2 mt-2">
                                  <span className="inline-flex rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
                                    {purchase.category}
                                  </span>
                                  <span className="inline-flex rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700">
                                    Compra em {formatDateBR(purchase.purchase_date)}
                                  </span>
                                  <span className="inline-flex rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-700">
                                    Parcela {purchase.installmentCurrent}/{purchase.installmentTotal}
                                  </span>
                                </div>
                              </div>

                              <div className="flex items-center gap-4">
                                <p className="text-base font-bold text-slate-900 whitespace-nowrap">{formatCurrency(purchase.amount)}</p>
                                <button
                                  onClick={() => handleDeleteCCPurchase(purchase)}
                                  className="text-slate-400 hover:text-red-500 transition"
                                  title="Excluir compra parcelada inteira"
                                >
                                  <Trash2 size={20} />
                                </button>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
