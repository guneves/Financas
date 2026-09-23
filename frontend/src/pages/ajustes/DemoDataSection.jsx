import { useState } from 'react'
import { Sparkles } from 'lucide-react'
import { ccExpensesApi, creditCardsApi, transactionsApi } from '../../lib/dataApi'
import { AlertMessage, Button, Panel, PanelHeader } from '../../components/ui'
import { confirmAction } from '../../lib/confirm'
import { toast } from '../../lib/toast'

// Dados de exemplo. O handler e os dados vieram de Carteira.jsx sem mudanca de
// payload; o que muda e a confirmacao (D2 em docs/ux-reorganization.md):
// isto grava linhas de verdade no banco do usuario.

function getNow() {
  return new Date()
}

function getLocalDateString(date = getNow()) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function dateAtDay(day, monthOffset = 0) {
  const today = getNow()
  const base = new Date(today.getFullYear(), today.getMonth() + monthOffset, 1)
  const lastDay = new Date(base.getFullYear(), base.getMonth() + 1, 0).getDate()
  base.setDate(Math.min(Math.max(day, 1), lastDay))
  return getLocalDateString(base)
}

function isSameTransaction(existing, candidate) {
  return existing.type === candidate.type
    && existing.date === candidate.date
    && existing.description === candidate.description
    && Number(existing.amount || 0).toFixed(2) === Number(candidate.amount || 0).toFixed(2)
}

function isSamePurchase(existing, candidate) {
  return existing.card_id === candidate.card_id
    && existing.description === candidate.description
    && existing.purchase_date === candidate.purchase_date
    && existing.category === candidate.category
}

function buildMockTransactions() {
  return [
    {
      type: 'INCOME',
      amount: 8500,
      date: dateAtDay(1),
      category: 'Salário',
      description: 'Demo - salário mensal',
    },
    {
      type: 'INCOME',
      amount: 1250,
      date: dateAtDay(2),
      category: 'Freelance',
      description: 'Demo - projeto extra',
    },
    {
      type: 'EXPENSE',
      amount: 2250,
      date: dateAtDay(3),
      category: 'Moradia',
      description: 'Demo - aluguel',
    },
    {
      type: 'EXPENSE',
      amount: 486.7,
      date: dateAtDay(4),
      category: 'Mercado',
      description: 'Demo - mercado da semana',
    },
    {
      type: 'EXPENSE',
      amount: 178.9,
      date: dateAtDay(5),
      category: 'Transporte',
      description: 'Demo - combustível',
    },
    {
      type: 'INCOME',
      amount: 8400,
      date: dateAtDay(1, -1),
      category: 'Salário',
      description: 'Demo - salário mês anterior',
    },
    {
      type: 'EXPENSE',
      amount: 2130,
      date: dateAtDay(3, -1),
      category: 'Moradia',
      description: 'Demo - aluguel mês anterior',
    },
  ]
}

const MOCK_CARDS = [
  { name: 'Nubank Demo', due_day: 10, closing_day: 3 },
  { name: 'Inter Demo', due_day: 20, closing_day: 13 },
]

// Em Carteira.jsx era uma constante de modulo; aqui e uma funcao para as datas
// acompanharem o dia em que o botao e apertado. Mesmos campos, mesmos valores.
function buildMockPurchases() {
  return [
    {
      cardName: 'Nubank Demo',
      category: 'Alimentação',
      description: 'Demo - supermercado no crédito',
      total_amount: 392.45,
      purchase_date: dateAtDay(2),
      installments: 1,
    },
    {
      cardName: 'Nubank Demo',
      category: 'Serviços',
      description: 'Demo - notebook parcelado',
      total_amount: 3600,
      purchase_date: dateAtDay(6),
      installments: 6,
    },
    {
      cardName: 'Inter Demo',
      category: 'Saúde',
      description: 'Demo - academia',
      total_amount: 129.9,
      purchase_date: dateAtDay(8),
      installments: 1,
    },
    {
      cardName: 'Inter Demo',
      category: 'Educação',
      description: 'Demo - curso online',
      total_amount: 900,
      purchase_date: dateAtDay(12),
      installments: 3,
    },
  ]
}

const CONFIRM_MESSAGE = 'Isto grava no seu banco de dados real 2 cartões, 7 lançamentos bancários e 4 compras parceladas, '
  + 'todos com "Demo" no nome ou na descrição. Eles entram no saldo, no extrato, nas faturas e nos gráficos, '
  + 'e depois precisam ser excluídos um a um.\n\n'
  + 'Rodar de novo não duplica o que já existe.'

export default function DemoDataSection({ onDataChanged }) {
  const [mockLoading, setMockLoading] = useState(false)
  const [dataError, setDataError] = useState('')

  const handleCreateMockData = async () => {
    if (!(await confirmAction({ title: 'Criar dados de exemplo?', message: CONFIRM_MESSAGE, confirmLabel: 'Criar dados', tone: 'neutral' }))) return

    setMockLoading(true)
    setDataError('')

    try {
      let latestCards = await creditCardsApi.list()
      const createdCounts = {
        cards: 0,
        transactions: 0,
        expenses: 0,
      }

      for (const mockCard of MOCK_CARDS) {
        const exists = latestCards.some((card) => card.name === mockCard.name)
        if (!exists) {
          await creditCardsApi.create(mockCard)
          createdCounts.cards += 1
        }
      }

      latestCards = await creditCardsApi.list()
      const latestTransactions = await transactionsApi.list()
      const latestCardExpenses = await ccExpensesApi.list()

      for (const mockTransaction of buildMockTransactions()) {
        if (!latestTransactions.some((transaction) => isSameTransaction(transaction, mockTransaction))) {
          await transactionsApi.create(mockTransaction)
          createdCounts.transactions += 1
        }
      }

      const cardByName = Object.fromEntries(latestCards.map((card) => [card.name, card]))

      for (const mockPurchase of buildMockPurchases()) {
        const card = cardByName[mockPurchase.cardName]
        if (!card) continue

        const alreadySeeded = latestCardExpenses.some((expense) => isSamePurchase(expense, {
          card_id: card.id,
          description: mockPurchase.description,
          purchase_date: mockPurchase.purchase_date,
          category: mockPurchase.category,
        }))
        if (alreadySeeded) continue

        const created = await ccExpensesApi.createPurchase({
          card_id: card.id,
          category: mockPurchase.category,
          description: mockPurchase.description,
          total_amount: mockPurchase.total_amount,
          purchase_date: mockPurchase.purchase_date,
          installments: mockPurchase.installments,
        })
        createdCounts.expenses += created.length
      }

      onDataChanged?.()
      toast(
        `Dados de exemplo aplicados: ${createdCounts.cards} cartão(ões), ${createdCounts.transactions} lançamento(s) bancário(s) e ${createdCounts.expenses} parcela(s) de cartão.`,
        { action: { label: 'Ver faturas', to: '/lancamentos/cartoes' }, duration: 8000 }
      )
    } catch (error) {
      setDataError(error.message || 'Não foi possível criar os dados de exemplo.')
    } finally {
      setMockLoading(false)
    }
  }

  return (
    <Panel id="dados-de-exemplo" className="scroll-mt-20 lg:scroll-mt-8">
      <PanelHeader
        title="Dados de exemplo"
        description="Preenche o app com cartões, lançamentos e compras fictícias para experimentar as telas."
      />
      <div className="space-y-4 p-5">
        <AlertMessage message={dataError} onDismiss={() => setDataError('')} />
        <AlertMessage tone="warning">
          Os dados de exemplo são gravados no seu banco de dados real, junto com os seus lançamentos. Use numa base de teste.
        </AlertMessage>
        <Button type="button" variant="secondary" icon={Sparkles} loading={mockLoading} onClick={handleCreateMockData}>
          Criar dados de exemplo
        </Button>
      </div>
    </Panel>
  )
}
