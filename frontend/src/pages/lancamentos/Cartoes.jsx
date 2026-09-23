import { useMemo, useState } from 'react'
import { CheckCircle, ChevronDown, CreditCard, Plus, Receipt, Trash2, Wallet } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ccExpensesApi } from '../../lib/dataApi'
import { useNewEntry } from '../../lib/newEntry'
import {
  AlertMessage,
  Badge,
  Button,
  EmptyState,
  Expand,
  FitValue,
  IconButton,
  PageHeader,
  Panel,
  cx,
} from '../../components/ui'
import { formatCurrency } from '../../lib/format'
import { usePrivateFormatter } from '../../lib/privacy'
import {
  formatDateBR,
  formatInvoiceLabel,
  getNow,
  getPurchaseGroupKey,
  parseInstallmentInfo,
} from './helpers'
import ProjectionHeader from './ProjectionHeader'
import PayInvoiceSheet from '../../components/PayInvoiceSheet'
import useLancamentos from './useLancamentos'

function invoiceDueDate(invoice, dueDay) {
  return new Date(invoice.invoiceYear, invoice.invoiceMonth - 1, dueDay || 1)
}

function SummaryStat({ icon: Icon, label, value, hint, tone = 'neutral' }) {
  const toneClasses = {
    neutral: 'bg-zinc-100 text-zinc-700',
    success: 'bg-emerald-100 text-emerald-700',
    info: 'bg-sky-100 text-sky-700',
    danger: 'bg-rose-100 text-rose-700',
  }

  return (
    <div className="flex items-center gap-3 rounded-lg border border-zinc-200 bg-white px-4 py-3 shadow-card">
      <div className={cx('hidden h-10 w-10 shrink-0 items-center justify-center rounded-lg sm:flex', toneClasses[tone] || toneClasses.neutral)}>
        <Icon className="h-5 w-5" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-semibold uppercase leading-4 tracking-wide text-zinc-500">{label}</p>
        <FitValue measure={value} baseSize={18} minSize={13} className="mt-0.5 font-bold text-zinc-950">{value}</FitValue>
        {hint ? <p className="truncate text-xs text-zinc-600">{hint}</p> : null}
      </div>
    </div>
  )
}

export default function Cartoes() {
  // Saldos da conta somem no modo privado; totais de cartao ficam.
  const privateMoney = usePrivateFormatter(formatCurrency)
  const { openNewEntry } = useNewEntry()
  const {
    dataError,
    setDataError,
    fetchData,
    balance,
    cards,
    accounts,
    ccExpenses,
    projectedBalanceGlobal,
    projectedBalanceNextMonth,
    accountName,
  } = useLancamentos()

  const [saving, setSaving] = useState(false)
  // Fatura aguardando confirmacao no sheet de pagamento: { invoice, cardGroup }.
  const [paying, setPaying] = useState(null)
  const [payError, setPayError] = useState('')
  const [payNotice, setPayNotice] = useState('')
  // Sobrescritas do usuario; sem entrada, so a fatura mais proxima fica aberta.
  const [toggledInvoices, setToggledInvoices] = useState({})

  // Portado de Carteira.jsx (walletSummary). O saldo e o mesmo do cabecalho
  // (lista completa, TRANSFER fora). ccExpenses ja vem so com status OPEN.
  const walletSummary = useMemo(() => {
    const today = getNow()
    const currentMonth = today.getMonth() + 1
    const currentYear = today.getFullYear()

    const openCreditTotal = ccExpenses.reduce((acc, expense) => acc + Number(expense.amount || 0), 0)
    const currentInvoiceTotal = ccExpenses
      .filter((expense) => expense.invoice_month === currentMonth && expense.invoice_year === currentYear)
      .reduce((acc, expense) => acc + Number(expense.amount || 0), 0)

    return {
      openCreditTotal,
      currentInvoiceTotal,
      projectedBalance: balance - openCreditTotal,
      availableAfterCurrentInvoice: balance - currentInvoiceTotal,
    }
  }, [balance, ccExpenses])

  const openInvoicesByCard = useMemo(() => {
    const groupedByCard = ccExpenses.reduce((acc, expense) => {
      const cardKey = expense.card_id || 'sem-cartao'
      const invoiceKey = `${expense.invoice_year}-${String(expense.invoice_month).padStart(2, '0')}`
      const card = cards.find((item) => item.id === expense.card_id)

      if (!acc[cardKey]) {
        acc[cardKey] = {
          cardId: expense.card_id,
          cardName: expense.credit_cards?.name || card?.name || 'Cartão',
          dueDay: expense.credit_cards?.due_day || card?.due_day,
          closingDay: expense.credit_cards?.closing_day || card?.closing_day,
          autopayAccountId: card?.autopay_account_id || null,
          invoices: {},
        }
      }

      if (!acc[cardKey].invoices[invoiceKey]) {
        acc[cardKey].invoices[invoiceKey] = {
          invoiceKey,
          invoiceMonth: expense.invoice_month,
          invoiceYear: expense.invoice_year,
          // Vem do servidor, que e onde mora a regra do fechamento.
          closed: expense.invoice_closed === true,
          closingDate: expense.invoice_closing_date,
          dueDate: expense.invoice_due_date,
          total: 0,
          purchases: {},
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
          installmentTotal: installment.total,
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
          purchases: Object.values(invoice.purchases).sort((a, b) => a.description.localeCompare(b.description)),
        })),
      }))
      .sort((a, b) => a.cardName.localeCompare(b.cardName))
  }, [ccExpenses, cards])

  // A fatura em aberto com o vencimento mais proximo (atrasadas primeiro).
  const nearestInvoice = useMemo(() => {
    let nearest = null
    openInvoicesByCard.forEach((cardGroup) => {
      cardGroup.invoices.forEach((invoice) => {
        const due = invoiceDueDate(invoice, cardGroup.dueDay)
        if (!nearest || due < nearest.due) {
          nearest = { due, invoice, cardGroup, key: `${cardGroup.cardId}|${invoice.invoiceKey}` }
        }
      })
    })
    return nearest
  }, [openInvoicesByCard])

  const isInvoiceExpanded = (key) => (
    key in toggledInvoices ? toggledInvoices[key] : key === nearestInvoice?.key
  )

  const toggleInvoice = (key) => {
    setToggledInvoices((prev) => ({ ...prev, [key]: !isInvoiceExpanded(key) }))
  }

  const handlePayInvoice = (invoice, cardGroup) => {
    if (!invoice.closed) return
    setPayError('')
    setPaying({ invoice, cardGroup })
  }

  // Conta sugerida: a do debito automatico do cartao, senao a padrao — a
  // mesma que o servidor usa quando account_id nao vem.
  const suggestedPayAccountId = useMemo(() => {
    const active = accounts.filter((account) => !account.archived_at)
    const autopayId = paying?.cardGroup.autopayAccountId
    if (autopayId && active.some((account) => account.id === autopayId)) return autopayId
    return (active.find((account) => account.is_default) || active[0])?.id || ''
  }, [accounts, paying])

  const confirmPayInvoice = async (accountId) => {
    if (!paying) return
    const { invoice, cardGroup } = paying
    setSaving(true)
    setPayError('')
    setPayNotice('')
    try {
      // Um unico pedido: o servidor lanca a despesa e baixa a fatura juntos.
      await ccExpensesApi.payInvoice({
        card_id: cardGroup.cardId,
        invoice_month: invoice.invoiceMonth,
        invoice_year: invoice.invoiceYear,
        account_id: accountId || undefined,
      })
      setPaying(null)
      const payer = accountId ? ` saiu de ${accountName(accountId)}` : ' foi debitado'
      setPayNotice(`Fatura ${cardGroup.cardName} ${formatInvoiceLabel(invoice.invoiceMonth, invoice.invoiceYear)} paga — ${formatCurrency(invoice.total)}${payer}.`)
      await fetchData()
    } catch (error) {
      setPayError(error.message || 'Não foi possível pagar a fatura.')
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteCCPurchase = async (purchase) => {
    if (!window.confirm(`Deseja excluir a compra "${purchase.description}" e eliminar todas as faturas vinculadas a ela?`)) return

    let candidates = []
    try {
      candidates = await ccExpensesApi.candidates({
        card_id: purchase.card_id,
        description: purchase.description,
        purchase_date: purchase.purchase_date,
        category: purchase.category,
      })
    } catch (error) {
      setDataError(error.message || 'Não foi possível localizar as faturas da compra.')
      return
    }

    // POST /api/cc-expenses/purchases distribui o resto dos centavos nas
    // primeiras parcelas (100/3 = 33,34 + 33,33 + 33,33), entao as parcelas de
    // uma mesma compra podem diferir em 1 centavo. A comparacao aceita essa
    // diferenca; antes ela exigia valor identico e deixava parcelas para tras.
    const purchaseCents = Math.round(parseFloat(purchase.amount) * 100)
    const idsToDelete = (candidates || [])
      .filter((item) => {
        const installment = parseInstallmentInfo(item.installment_info)
        return Math.abs(Math.round(parseFloat(item.amount) * 100) - purchaseCents) <= 1
          && installment.total === purchase.installmentTotal
      })
      .map((item) => item.id)

    if (idsToDelete.length === 0) {
      alert('Nenhuma fatura vinculada foi encontrada para essa compra.')
      return
    }

    try {
      await ccExpensesApi.removeMany(idsToDelete)
      await fetchData()
    } catch (error) {
      setDataError(error.message || 'Não foi possível excluir a compra.')
    }
  }

  const getInvoiceStatus = (invoice, dueDay) => {
    const today = getNow()
    const dueDate = new Date(invoice.invoiceYear, invoice.invoiceMonth - 1, dueDay)
    if (today > dueDate) return <Badge tone="danger">Em atraso</Badge>
    if (invoice.closed) return <Badge tone="warning">Fechada</Badge>
    return <Badge>Aberta</Badge>
  }

  // Por que o botao Pagar esta (ou nao) liberado, numa linha.
  const paymentHint = (invoice, cardGroup) => {
    if (!invoice.closed) {
      return invoice.closingDate ? `Fecha em ${formatDateBR(invoice.closingDate)} · pagamento liberado depois` : 'Pagamento liberado após o fechamento'
    }
    if (cardGroup.autopayAccountId && invoice.dueDate) {
      return `Débito automático em ${formatDateBR(invoice.dueDate)}`
    }
    return null
  }

  const headerActions = nearestInvoice ? (
    <>
      <Button type="button" variant="secondary" icon={Plus} onClick={() => openNewEntry('CARD')}>Nova compra</Button>
      <Button
        type="button"
        icon={CheckCircle}
        loading={saving}
        disabled={!nearestInvoice.invoice.closed}
        title={nearestInvoice.invoice.closed ? undefined : paymentHint(nearestInvoice.invoice, nearestInvoice.cardGroup)}
        onClick={() => handlePayInvoice(nearestInvoice.invoice, nearestInvoice.cardGroup)}
      >
        Pagar fatura
      </Button>
    </>
  ) : (
    <Button type="button" variant="secondary" icon={Plus} onClick={() => openNewEntry('CARD')}>Nova compra</Button>
  )

  return (
    <div className="space-y-6">
      <PageHeader
        title="Cartões"
        description={nearestInvoice
          ? `Próxima fatura: ${nearestInvoice.cardGroup.cardName} ${formatInvoiceLabel(nearestInvoice.invoice.invoiceMonth, nearestInvoice.invoice.invoiceYear)} · ${formatCurrency(nearestInvoice.invoice.total)}`
          : 'Faturas em aberto por cartão.'}
        actions={headerActions}
      />

      <AlertMessage tone="warning" message={dataError} onDismiss={() => setDataError('')} />
      <AlertMessage tone="success" message={payNotice} onDismiss={() => setPayNotice('')} />

      <PayInvoiceSheet
        open={Boolean(paying)}
        onClose={() => setPaying(null)}
        title="Pagar fatura"
        description={paying
          ? `${paying.cardGroup.cardName} · ${formatInvoiceLabel(paying.invoice.invoiceMonth, paying.invoice.invoiceYear)}`
          : undefined}
        total={paying?.invoice.total || 0}
        accounts={accounts}
        defaultAccountId={suggestedPayAccountId}
        saving={saving}
        error={payError}
        onConfirm={confirmPayInvoice}
      />

      <ProjectionHeader
        balance={balance}
        projectedBalanceNextMonth={projectedBalanceNextMonth}
        projectedBalanceGlobal={projectedBalanceGlobal}
      />

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <SummaryStat icon={CreditCard} label="Total aberto" value={formatCurrency(walletSummary.openCreditTotal)} />
        <SummaryStat icon={Receipt} label="Fatura do mês" value={formatCurrency(walletSummary.currentInvoiceTotal)} />
        <SummaryStat icon={Wallet} label="Saldo após a fatura atual" value={privateMoney(walletSummary.availableAfterCurrentInvoice)} tone={walletSummary.availableAfterCurrentInvoice >= 0 ? 'neutral' : 'danger'} />
        <SummaryStat icon={Wallet} label="Saldo projetado" value={privateMoney(walletSummary.projectedBalance)} hint="Conta menos cartões abertos" tone={walletSummary.projectedBalance >= 0 ? 'neutral' : 'danger'} />
      </div>

      {cards.length === 0 ? (
        <Panel className="p-5">
          <EmptyState
            icon={CreditCard}
            title="Nenhum cartão cadastrado"
            message="Os cartões ficam em Ajustes. Depois disso, registre compras pelo botão Novo."
            action={<Link to="/ajustes#cartoes" className="text-sm font-semibold text-emerald-700 underline-offset-2 hover:underline">Cadastrar cartão em Ajustes</Link>}
          />
        </Panel>
      ) : openInvoicesByCard.length > 0 ? (
        <div className="space-y-4">
          {openInvoicesByCard.map((cardGroup) => {
            const cardTotal = cardGroup.invoices.reduce((acc, invoice) => acc + invoice.total, 0)

            return (
              <Panel key={cardGroup.cardId} className="overflow-hidden">
                <div className="flex flex-col gap-1 border-b border-zinc-100 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-lg font-bold text-zinc-950">{cardGroup.cardName}</h3>
                      <Badge>{cardGroup.invoices.length} fatura(s)</Badge>
                      {cardGroup.autopayAccountId ? (
                        <Badge>Débito automático · {accountName(cardGroup.autopayAccountId)}</Badge>
                      ) : null}
                    </div>
                    <p className="mt-1 text-sm text-zinc-600">Vence dia {cardGroup.dueDay} • Fecha dia {cardGroup.closingDay}</p>
                  </div>
                  <p className="whitespace-nowrap text-sm text-zinc-600">Em aberto: <span className="font-semibold text-zinc-950">{formatCurrency(cardTotal)}</span></p>
                </div>

                <div className="divide-y divide-zinc-100">
                  {cardGroup.invoices.map((invoice) => {
                    const key = `${cardGroup.cardId}|${invoice.invoiceKey}`
                    const expanded = isInvoiceExpanded(key)
                    const isNearest = key === nearestInvoice?.key
                    const hint = paymentHint(invoice, cardGroup)

                    return (
                      <div key={invoice.invoiceKey}>
                        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-5 py-3">
                          <button
                            type="button"
                            onClick={() => toggleInvoice(key)}
                            aria-expanded={expanded}
                            className="flex min-h-[44px] min-w-[14rem] flex-1 items-center gap-3 text-left"
                          >
                            <ChevronDown className={cx('h-5 w-5 shrink-0 text-zinc-500 transition-transform', expanded && 'rotate-180')} />
                            <div className="min-w-0">
                              <div className="flex flex-wrap items-center gap-2">
                                <p className="font-semibold text-zinc-950">Fatura {formatInvoiceLabel(invoice.invoiceMonth, invoice.invoiceYear)}</p>
                                {getInvoiceStatus(invoice, cardGroup.dueDay)}
                                {isNearest ? <Badge>Próxima</Badge> : null}
                              </div>
                              {hint ? <p className="mt-0.5 text-xs text-zinc-500">{hint}</p> : null}
                            </div>
                          </button>
                          <div className="ml-auto flex items-center gap-3">
                            <p className="whitespace-nowrap text-base font-semibold text-zinc-950">{formatCurrency(invoice.total)}</p>
                            <Button type="button" variant={isNearest && invoice.closed ? 'primary' : 'secondary'} icon={CheckCircle} loading={saving} disabled={!invoice.closed} title={invoice.closed ? undefined : hint} onClick={() => handlePayInvoice(invoice, cardGroup)} className="h-11 lg:h-9">
                              Pagar
                            </Button>
                          </div>
                        </div>

                        <Expand open={expanded} innerClassName="px-5 pb-4">
                          <ul className="divide-y divide-zinc-100 rounded-lg border border-zinc-200">
                            {invoice.purchases.map((purchase) => (
                              <li key={purchase.purchaseKey} className="flex items-center gap-3 py-1.5 pl-4 pr-2">
                                <div className="min-w-0 flex-1">
                                  <p className="truncate font-medium text-zinc-900" title={purchase.description}>{purchase.description}</p>
                                  <p className="truncate text-xs text-zinc-500">
                                    {purchase.category} · {formatDateBR(purchase.purchase_date)}
                                    {purchase.installmentTotal > 1 ? ` · parcela ${purchase.installmentCurrent}/${purchase.installmentTotal}` : ''}
                                  </p>
                                </div>
                                <p className="whitespace-nowrap font-semibold text-zinc-950">{formatCurrency(purchase.amount)}</p>
                                <IconButton label="Excluir compra parcelada" icon={Trash2} size="sm" variant="danger" onClick={() => handleDeleteCCPurchase(purchase)} />
                              </li>
                            ))}
                          </ul>
                        </Expand>
                      </div>
                    )
                  })}
                </div>
              </Panel>
            )
          })}
        </div>
      ) : (
        <Panel className="p-5">
          <EmptyState icon={CreditCard} title="Nenhuma fatura aberta" message="As compras no crédito aparecerão agrupadas por cartão." />
        </Panel>
      )}
    </div>
  )
}
