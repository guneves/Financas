import { useState, useEffect } from 'react'
import { supabase } from '../lib/supabaseClient'
import { Wallet, ArrowDownCircle, ArrowUpCircle, Trash2 } from 'lucide-react'

export default function Transactions() {
  const [transactions, setTransactions] = useState([])
  const [balance, setBalance] = useState(0)
  const [form, setForm] = useState({ amount: '', date: '', category: '', description: '', type: 'EXPENSE' })
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetchTransactions()
  }, [])

  const fetchTransactions = async () => {
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return

    const { data, error } = await supabase
      .from('transactions')
      .select('*')
      .order('date', { ascending: false })

    if (!error && data) {
      setTransactions(data)
      
      // Lógica da Conta Bancária: Soma receitas e subtrai despesas
      const currentBalance = data.reduce((acc, curr) => {
        return curr.type === 'INCOME' ? acc + parseFloat(curr.amount) : acc - parseFloat(curr.amount)
      }, 0)
      setBalance(currentBalance)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    const { data: { user } } = await supabase.auth.getUser()

    const { error } = await supabase.from('transactions').insert([
      { 
        user_id: user.id, 
        amount: parseFloat(form.amount), 
        date: form.date, 
        category: form.category, 
        description: form.description, 
        type: form.type 
      }
    ])

    if (!error) {
      setForm({ amount: '', date: '', category: '', description: '', type: 'EXPENSE' })
      fetchTransactions() // Recarrega o extrato e o saldo
    }
    setLoading(false)
  }

  const handleDelete = async (id) => {
    if(window.confirm("Deseja excluir esta transação?")) {
      const { error } = await supabase.from('transactions').delete().eq('id', id)
      if (!error) fetchTransactions()
    }
  }

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-800">Conta Corrente</h1>
          <p className="text-slate-500 mt-1">Gerencie suas receitas e despesas diárias.</p>
        </div>
        
        {/* Cartão de Saldo Bancário */}
        <div className="bg-slate-900 text-white p-6 rounded-2xl shadow-lg flex items-center gap-4 min-w-[250px]">
          <div className="bg-slate-800 p-3 rounded-xl"><Wallet className="text-blue-400" /></div>
          <div>
            <p className="text-sm font-medium text-slate-400">Saldo Disponível</p>
            <p className={`text-2xl font-bold ${balance >= 0 ? 'text-white' : 'text-red-400'}`}>
              R$ {balance.toFixed(2)}
            </p>
          </div>
        </div>
      </div>

      {/* Formulário de Lançamento */}
      <form onSubmit={handleSubmit} className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 grid grid-cols-1 md:grid-cols-6 gap-4 items-end">
        <div className="flex flex-col space-y-1 md:col-span-1">
          <label className="text-sm text-slate-500 font-medium">Tipo</label>
          <select value={form.type} onChange={e => setForm({...form, type: e.target.value})} className="p-2 border border-slate-300 rounded-lg bg-white">
            <option value="EXPENSE">Saída (-)</option>
            <option value="INCOME">Entrada (+)</option>
          </select>
        </div>
        <div className="flex flex-col space-y-1 md:col-span-1">
          <label className="text-sm text-slate-500 font-medium">Valor (R$)</label>
          <input type="number" step="0.01" min="0.01" value={form.amount} onChange={e => setForm({...form, amount: e.target.value})} className="p-2 border border-slate-300 rounded-lg" required />
        </div>
        <div className="flex flex-col space-y-1 md:col-span-1">
          <label className="text-sm text-slate-500 font-medium">Data</label>
          <input type="date" value={form.date} onChange={e => setForm({...form, date: e.target.value})} className="p-2 border border-slate-300 rounded-lg" required />
        </div>
        <div className="flex flex-col space-y-1 md:col-span-2">
          <label className="text-sm text-slate-500 font-medium">Categoria / Descrição</label>
          <input type="text" placeholder="Ex: Salário, Supermercado..." value={form.category} onChange={e => setForm({...form, category: e.target.value})} className="p-2 border border-slate-300 rounded-lg" required />
        </div>
        <button type="submit" disabled={loading} className="md:col-span-1 bg-blue-600 text-white rounded-lg py-2.5 font-medium hover:bg-blue-700 transition">
          Lançar
        </button>
      </form>

      {/* Extrato Bancário */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100 text-slate-600 text-sm">
              <th className="p-4 font-medium">Data</th>
              <th className="p-4 font-medium">Descrição</th>
              <th className="p-4 font-medium">Movimentação</th>
              <th className="p-4 font-medium">Valor</th>
              <th className="p-4 font-medium text-right"></th>
            </tr>
          </thead>
          <tbody>
            {transactions.map(t => (
              <tr key={t.id} className="border-b border-slate-50 hover:bg-slate-50 transition">
                <td className="p-4 text-slate-600">{new Date(t.date).toLocaleDateString('pt-BR')}</td>
                <td className="p-4 font-medium text-slate-800">{t.category}</td>
                <td className="p-4">
                  {t.type === 'INCOME' ? (
                    <span className="flex items-center gap-1 text-green-600 text-sm font-medium bg-green-50 w-fit px-2 py-1 rounded-md"><ArrowUpCircle size={16}/> Entrada</span>
                  ) : (
                    <span className="flex items-center gap-1 text-red-600 text-sm font-medium bg-red-50 w-fit px-2 py-1 rounded-md"><ArrowDownCircle size={16}/> Saída</span>
                  )}
                </td>
                <td className={`p-4 font-bold ${t.type === 'INCOME' ? 'text-green-600' : 'text-slate-800'}`}>
                  {t.type === 'INCOME' ? '+' : '-'} R$ {parseFloat(t.amount).toFixed(2)}
                </td>
                <td className="p-4 text-right">
                  <button onClick={() => handleDelete(t.id)} className="text-slate-400 hover:text-red-500 transition"><Trash2 size={18}/></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}