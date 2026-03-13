import { useState, useEffect } from 'react'
import { supabase } from '../lib/supabaseClient'
import { Wallet, ArrowDownCircle, ArrowUpCircle, Trash2, CreditCard, Calendar, CheckCircle } from 'lucide-react'

export default function Transactions() {
  const [activeTab, setActiveTab] = useState('CONTA') // 'CONTA' ou 'CARTOES'
  
  // Estados da Conta Corrente
  const [transactions, setTransactions] = useState([])
  const [balance, setBalance] = useState(0)
  const [transForm, setTransForm] = useState({ amount: '', date: '', category: '', description: '', type: 'EXPENSE' })
  
  // Estados do Cartão de Crédito
  const [cards, setCards] = useState([])
  const [ccExpenses, setCcExpenses] = useState([])
  const [cardForm, setCardForm] = useState({ name: '', due_day: '' })
  const [expenseForm, setExpenseForm] = useState({ card_id: '', description: '', total_amount: '', purchase_date: '', installments: '1' })
  const [projectedBalanceGlobal, setProjectedBalanceGlobal] = useState(0)
  const [projectedBalanceNextMonth, setProjectedBalanceNextMonth] = useState(0)

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return

    // 1. Busca Transações Bancárias
    const { data: tData } = await supabase.from('transactions').select('*').order('date', { ascending: false })
    let currentBalance = 0
    if (tData) {
      setTransactions(tData)
      currentBalance = tData.reduce((acc, curr) => curr.type === 'INCOME' ? acc + parseFloat(curr.amount) : acc - parseFloat(curr.amount), 0)
      setBalance(currentBalance)
    }

    // 2. Busca Cartões
    const { data: cData } = await supabase.from('credit_cards').select('*')
    if (cData) setCards(cData)

    // 3. Busca Despesas de Cartão e Calcula Projeções
    const { data: ccData } = await supabase.from('cc_expenses').select(`*, credit_cards(name, due_day)`).eq('status', 'OPEN').order('invoice_year', { ascending: true }).order('invoice_month', { ascending: true })
    
    if (ccData) {
      setCcExpenses(ccData)

      // Descobre as datas dinamicamente
      const today = new Date()
      const currentMonth = today.getMonth() + 1
      const currentYear = today.getFullYear()

      let nextMonth = currentMonth + 1
      let nextYear = currentYear
      if (nextMonth > 12) { nextMonth = 1; nextYear++ }

      // Projeção Global (Desconta TODAS as faturas)
      const totalOpenCredit = ccData.reduce((acc, curr) => acc + parseFloat(curr.amount), 0)
      setProjectedBalanceGlobal(currentBalance - totalOpenCredit)

      // Projeção Próximo Mês (Desconta faturas atrasadas, deste mês e do próximo)
      const creditUpToNextMonth = ccData.reduce((acc, curr) => {
        const isPastOrCurrent = curr.invoice_year < currentYear || (curr.invoice_year === currentYear && curr.invoice_month <= currentMonth)
        const isNextMonth = curr.invoice_year === nextYear && curr.invoice_month === nextMonth

        if (isPastOrCurrent || isNextMonth) {
          return acc + parseFloat(curr.amount)
        }
        return acc
      }, 0)

      setProjectedBalanceNextMonth(currentBalance - creditUpToNextMonth)
    }
  }

  // ---- LÓGICA CONTA CORRENTE ----
  const handleBankSubmit = async (e) => {
    e.preventDefault()
    const { data: { user } } = await supabase.auth.getUser()
    await supabase.from('transactions').insert([{ 
      user_id: user.id, amount: parseFloat(transForm.amount), date: transForm.date, category: transForm.category, description: transForm.description, type: transForm.type 
    }])
    setTransForm({ amount: '', date: '', category: '', description: '', type: 'EXPENSE' })
    fetchData()
  }

  // ---- LÓGICA CARTÕES DE CRÉDITO ----
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
    
    // Calcula o mês da primeira fatura baseado na data da compra
    const purchaseDate = new Date(expenseForm.purchase_date + 'T00:00:00') // Força o fuso horário local
    let currentMonth = purchaseDate.getMonth() + 1
    let currentYear = purchaseDate.getFullYear()

    const inserts = []
    for (let i = 1; i <= installmentsCount; i++) {
      inserts.push({
        user_id: user.id,
        card_id: expenseForm.card_id,
        description: expenseForm.description,
        amount: amountPerInstallment.toFixed(2),
        purchase_date: expenseForm.purchase_date,
        invoice_month: currentMonth,
        invoice_year: currentYear,
        installment_info: `${i}/${installmentsCount}`,
        status: 'OPEN'
      })
      // Avança o mês da fatura para as próximas parcelas
      currentMonth++
      if (currentMonth > 12) { currentMonth = 1; currentYear++ }
    }

    await supabase.from('cc_expenses').insert(inserts)
    setExpenseForm({ card_id: cards[0]?.id || '', description: '', total_amount: '', purchase_date: '', installments: '1' })
    fetchData()
  }

  const handlePayInvoice = async (expense) => {
    if(!window.confirm(`Deseja pagar e descontar R$ ${expense.amount} do saldo da conta corrente?`)) return
    const { data: { user } } = await supabase.auth.getUser()
    
    // 1. Desconta o dinheiro da conta bancária real
    await supabase.from('transactions').insert([{
      user_id: user.id, type: 'EXPENSE', amount: expense.amount, date: new Date().toISOString().split('T')[0], category: `Pagamento Fatura ${expense.credit_cards.name}`, description: expense.description
    }])
    
    // 2. Muda o status da despesa do cartão para PAGA
    await supabase.from('cc_expenses').update({ status: 'PAID' }).eq('id', expense.id)
    fetchData()
  }

  const handleDeleteTransaction = async (id) => {
    if(!window.confirm("Deseja realmente eliminar esta transação? O saldo será recalculado.")) return
    const { error } = await supabase.from('transactions').delete().eq('id', id)
    if (!error) fetchData()
  }

  const handleDeleteCCExpense = async (id) => {
    if(!window.confirm("Deseja eliminar este lançamento do cartão de crédito?")) return
    const { error } = await supabase.from('cc_expenses').delete().eq('id', id)
    if (!error) fetchData()
  }

  const handleDeleteCard = async (id, name) => {
    if(!window.confirm(`ATENÇÃO: Deseja realmente excluir o cartão "${name}"?\nIsso apagará TODAS as faturas (abertas e pagas) vinculadas a ele. Esta ação não pode ser desfeita.`)) return
    
    await supabase.from('cc_expenses').delete().eq('card_id', id)
    
    const { error } = await supabase.from('credit_cards').delete().eq('id', id)
    
    if (error) {
      alert("Erro ao excluir cartão: " + error.message)
    } else {
      fetchData()
    }
  }

  // Helpers Visuais
  const getInvoiceStatus = (year, month, dueDay) => {
    const today = new Date()
    const dueDate = new Date(year, month - 1, dueDay)
    if (today > dueDate) return <span className="text-red-600 font-bold text-xs bg-red-100 px-2 py-1 rounded-md">Em Atraso</span>
    return <span className="text-yellow-600 font-bold text-xs bg-yellow-100 px-2 py-1 rounded-md">Aberta</span>
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      
      {/* Cabeçalho e Painéis de Saldo */}
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

      {/* =========================================
          ABA: CONTA CORRENTE (Débito/Dinheiro)
          ========================================= */}
      {activeTab === 'CONTA' && (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
          <form onSubmit={handleBankSubmit} className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 grid grid-cols-1 md:grid-cols-6 gap-4">
            <select value={transForm.type} onChange={e => setTransForm({...transForm, type: e.target.value})} className="p-2 border rounded-lg bg-white">
              <option value="EXPENSE">Saída Bancária (-)</option><option value="INCOME">Entrada Bancária (+)</option>
            </select>
            <input type="number" step="0.01" placeholder="Valor (R$)" value={transForm.amount} onChange={e => setTransForm({...transForm, amount: e.target.value})} className="p-2 border rounded-lg" required />
            <input type="date" value={transForm.date} onChange={e => setTransForm({...transForm, date: e.target.value})} className="p-2 border rounded-lg" required />
            <input type="text" placeholder="Categoria / Descrição" value={transForm.category} onChange={e => setTransForm({...transForm, category: e.target.value})} className="col-span-2 p-2 border rounded-lg" required />
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
                  <th className="p-4 text-right">Ação</th> {/* Nova Coluna */}
                </tr>
              </thead>
              <tbody>
                {transactions.map(t => (
                  <tr key={t.id} className="border-b border-slate-50 hover:bg-slate-50">
                    <td className="p-4 text-slate-600">{new Date(t.date).toLocaleDateString('pt-BR')}</td>
                    <td className="p-4 font-medium">{t.category}</td>
                    <td className="p-4">{t.type === 'INCOME' ? <span className="text-green-600">Entrada</span> : <span className="text-red-600">Saída</span>}</td>
                    <td className={`p-4 font-bold ${t.type === 'INCOME' ? 'text-green-600' : 'text-slate-800'}`}>{t.type === 'INCOME' ? '+' : '-'} R$ {parseFloat(t.amount).toFixed(2)}</td>
                    {/* Eliminar */}
                    <td className="p-4 text-right">
                      <button onClick={() => handleDeleteTransaction(t.id)} className="text-slate-400 hover:text-red-500 transition">
                        <Trash2 size={18}/>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* =========================================
          ABA: CARTÕES DE CRÉDITO
          ========================================= */}
      {activeTab === 'CARTOES' && (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Cadastro e Lista de Cartões */}
            <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 col-span-1 h-fit">
              <h3 className="font-bold text-slate-800 mb-4 flex items-center gap-2"><CreditCard size={20}/> Gerenciar Cartões</h3>
              
              <form onSubmit={handleCreateCard} className="space-y-4 mb-6">
                <input type="text" placeholder="Nome do Cartão (ex: Nubank)" value={cardForm.name} onChange={e => setCardForm({...cardForm, name: e.target.value})} className="w-full p-2 border rounded-lg" required />
                <input type="number" min="1" max="31" placeholder="Dia do Vencimento" value={cardForm.due_day} onChange={e => setCardForm({...cardForm, due_day: e.target.value})} className="w-full p-2 border rounded-lg" required />
                <button type="submit" className="w-full bg-slate-800 text-white rounded-lg py-2 hover:bg-slate-900 transition">Salvar Cartão</button>
              </form>

              {/* Lista de Cartões Cadastrados */}
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
                          <Trash2 size={18}/>
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Lançamento de Compra no Crédito */}
            <div className="bg-white p-6 rounded-2xl shadow-sm border border-blue-200 col-span-2">
              <h3 className="font-bold text-blue-800 mb-4 flex items-center gap-2"><Wallet size={20}/> Lançar Compra no Crédito</h3>
              {cards.length === 0 ? (
                <div className="text-slate-500 bg-slate-50 p-4 rounded-lg">Cadastre um cartão primeiro para lançar compras.</div>
              ) : (
                <form onSubmit={handleCCExpenseSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <select value={expenseForm.card_id} onChange={e => setExpenseForm({...expenseForm, card_id: e.target.value})} className="p-2 border rounded-lg" required>
                    <option value="">Selecione o Cartão...</option>
                    {cards.map(c => <option key={c.id} value={c.id}>{c.name} (Vence dia {c.due_day})</option>)}
                  </select>
                  <input type="text" placeholder="O que você comprou?" value={expenseForm.description} onChange={e => setExpenseForm({...expenseForm, description: e.target.value})} className="p-2 border rounded-lg" required />
                  <input type="number" step="0.01" placeholder="Valor TOTAL da Compra" value={expenseForm.total_amount} onChange={e => setExpenseForm({...expenseForm, total_amount: e.target.value})} className="p-2 border rounded-lg" required />
                  <div className="flex gap-2">
                    <input type="date" title="Data da Compra" value={expenseForm.purchase_date} onChange={e => setExpenseForm({...expenseForm, purchase_date: e.target.value})} className="flex-1 p-2 border rounded-lg" required />
                    <input type="number" min="1" max="48" title="Qtd de Parcelas" placeholder="Parcelas" value={expenseForm.installments} onChange={e => setExpenseForm({...expenseForm, installments: e.target.value})} className="w-24 p-2 border rounded-lg" required />
                  </div>
                  <button type="submit" className="col-span-1 md:col-span-2 bg-blue-600 text-white rounded-lg py-2 hover:bg-blue-700">Registrar Compra Parcelada</button>
                </form>
              )}
            </div>
          </div>

          {/* Faturas em Aberto */}
          <h3 className="text-xl font-bold text-slate-800 mt-8 mb-4">Faturas em Aberto</h3>
          <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-slate-50 border-b text-slate-600 text-sm">
                  <th className="p-4">Cartão / Vencimento</th><th className="p-4">Descrição</th><th className="p-4">Parcela</th><th className="p-4">Valor</th><th className="p-4">Status</th><th className="p-4 text-right">Ação</th>
                </tr>
              </thead>
              <tbody>
                {ccExpenses.length === 0 && <tr><td colSpan="6" className="p-8 text-center text-slate-500">Você não tem nenhuma fatura em aberto. Que paz!</td></tr>}
                {ccExpenses.map(exp => (
                  <tr key={exp.id} className="border-b border-slate-50 hover:bg-slate-50">
                    <td className="p-4">
                      <p className="font-bold text-slate-800">{exp.credit_cards.name}</p>
                      <p className="text-xs text-slate-500"><Calendar className="inline w-3 h-3 mr-1"/>{exp.credit_cards.due_day}/{exp.invoice_month}/{exp.invoice_year}</p>
                    </td>
                    <td className="p-4 font-medium text-slate-700">{exp.description}</td>
                    <td className="p-4 text-slate-600">{exp.installment_info}</td>
                    <td className="p-4 font-bold text-red-500">R$ {parseFloat(exp.amount).toFixed(2)}</td>
                    <td className="p-4">{getInvoiceStatus(exp.invoice_year, exp.invoice_month, exp.credit_cards.due_day)}</td>
                    <td className="p-4 text-right flex justify-end items-center gap-3">
                      <button onClick={() => handlePayInvoice(exp)} className="text-white bg-green-500 hover:bg-green-600 px-3 py-1.5 rounded-lg text-sm font-medium transition flex items-center gap-1">
                        <CheckCircle size={16}/> Pagar e Baixar
                      </button>
                      {/* Novo Botão de Eliminar Fatura */}
                      <button onClick={() => handleDeleteCCExpense(exp.id)} className="text-slate-400 hover:text-red-500 transition" title="Eliminar lançamento">
                        <Trash2 size={20}/>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}