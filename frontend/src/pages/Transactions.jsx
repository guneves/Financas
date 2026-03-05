import { useState, useEffect } from 'react'
import { supabase } from '../lib/supabaseClient'

export default function Transactions() {
  const [transactions, setTransactions] = useState([])
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

    if (error) console.error("Erro ao buscar:", error)
    else setTransactions(data)
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
      fetchTransactions()
    }
    setLoading(false)
  }

  const handleDelete = async (id) => {
    const { error } = await supabase.from('transactions').delete().eq('id', id)
    if (!error) fetchTransactions()
  }

  return (
    <div className="max-w-4xl mx-auto p-8">
      <h1 className="text-3xl font-bold mb-8 text-slate-800">Transações Diárias</h1>

      <form onSubmit={handleSubmit} className="bg-white p-6 rounded-xl shadow-sm border border-slate-200 mb-8 grid grid-cols-1 md:grid-cols-5 gap-4">
        <select value={form.type} onChange={e => setForm({...form, type: e.target.value})} className="p-2 border rounded-md" required>
          <option value="EXPENSE">Despesa</option>
          <option value="INCOME">Receita</option>
        </select>
        <input type="number" step="0.01" placeholder="Valor" value={form.amount} onChange={e => setForm({...form, amount: e.target.value})} className="p-2 border rounded-md" required />
        <input type="date" value={form.date} onChange={e => setForm({...form, date: e.target.value})} className="p-2 border rounded-md" required />
        <input type="text" placeholder="Categoria" value={form.category} onChange={e => setForm({...form, category: e.target.value})} className="p-2 border rounded-md" required />
        <button type="submit" disabled={loading} className="bg-blue-600 text-white rounded-md py-2 hover:bg-blue-700">Adicionar</button>
      </form>

      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-slate-50 border-b text-slate-600">
              <th className="p-4">Data</th><th className="p-4">Categoria</th><th className="p-4">Tipo</th><th className="p-4">Valor</th><th className="p-4">Ação</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map(t => (
              <tr key={t.id} className="border-b hover:bg-slate-50">
                <td className="p-4">{t.date}</td><td className="p-4">{t.category}</td>
                <td className="p-4">{t.type === 'INCOME' ? 'Entrada' : 'Saída'}</td>
                <td className="p-4">R$ {t.amount}</td>
                <td className="p-4"><button onClick={() => handleDelete(t.id)} className="text-red-500 hover:underline">Excluir</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}