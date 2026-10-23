import { useMemo, useState } from 'react'
import { CheckCircle, ChevronDown, CreditCard, Paperclip, Plus, Trash2, Undo2, Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ccExpensesApi, ccInvoicesApi } from '../../lib/dataApi'
import { useNewEntry } from '../../lib/newEntry'
import {
  AlertMessage,
  Badge,
  Button,
  EmptyState,
  ListSkeleton,
  Expand,
  Menu,
  PageHeader,
  Panel,
  cx,
} from '../../components/ui'
import { formatCurrency, formatSignedCurrency } from '../../lib/format'
import { formatDateBR, formatInvoiceLabel } from './helpers'
import ProjectionHeader from './ProjectionHeader'
import PayInvoiceSheet from '../../components/PayInvoiceSheet'
import AttachmentsSheet from '../../components/AttachmentsSheet'
import CardShareSheet from './CardShareSheet'
import CardRefundSheet from './CardRefundSheet'
import { shareSummary } from '../../lib/sharing'
import useLancamentos from './useLancamentos'
import { confirmAction } from '../../lib/confirm'
import { useQuery } from '../../lib/queries'
import { toast } from '../../lib/toast'

// Uma compra de GET /api/cc-invoices como a tela e os sheets a leem.
function purchaseRow(purchase, cardId) {
  return {
    purchaseKey: purchase.id,
    id: purchase.id,
    client_id: purchase.client_id || null,
    attachmentCount: Number(purchase.attachment_count || 0),
    card_id: cardId,
    description: purchase.description,
    category: purchase.category || 'Outros',
    category_raw: purchase.category,
    purchase_date: purchase.purchase_date,
    amount: purchase.amount,
    refund: purchase.kind === 'REFUND',
    installmentCurrent: purchase.installment_current,
    installmentTotal: purchase.installment_total,
    installmentsOpen: purchase.installments_open,
    installmentsPaid: purchase.installments_paid,
    // A parcela desta fatura: "Dividida com Ana · sua parte" e da parcela.
    shareText: shareSummary(purchase),
  }
}

// As faturas de um cartao, com as flags do servidor (services/card_invoices.py).
function cardGroupOf(card) {
  return {
    cardId: card.card_id,
    cardName: card.card_name,
    dueDay: card.due_day,
    closingDay: card.closing_day,
    autopayAccountId: card.autopay_account_id || null,
    total: card.total,
    invoices: card.invoices.map((invoice) => ({
      invoiceKey: invoice.key,
      invoiceMonth: invoice.invoice_month,
      invoiceYear: invoice.invoice_year,
      closed: invoice.closed,
      closingDate: invoice.closing_date,
      dueDate: invoice.due_date,
      pastDue: invoice.past_due,
      payable: invoice.payable,
      nearest: invoice.nearest,
      future: invoice.future,
      total: invoice.total,
      purchases: invoice.purchases.map((purchase) => purchaseRow(purchase, card.card_id)),
    })),
  }
}

const NO_CARDS = []

export default function Cartoes() {
  const { openNewEntry } = useNewEntry()
  const {
    loading,
    dataError,
    setDataError,
    fetchData,
    balance,
    cards,
    accounts,
    projectedBalanceGlobal,
    projectedBalanceNextMonth,
    accountName,
  } = useLancamentos()

  const [saving, setSaving] = useState(false)
  // Fatura aguardando confirmacao no sheet de pagamento: { invoice, cardGroup }.
  const [paying, setPaying] = useState(null)
  const [payError, setPayError] = useState('')
  const [attachmentsFor, setAttachmentsFor] = useState(null)
  // Compra com o "De quem é?" aberto (CardShareSheet).
  const [shareFor, setShareFor] = useState(null)
  // Estorno sendo lancado (CardRefundSheet): { purchase } ou {} pelo topo.
  const [refundFor, setRefundFor] = useState(null)
  // Sobrescritas do usuario; sem entrada, so a fatura mais proxima fica aberta.
  const [toggledInvoices, setToggledInvoices] = useState({})
  // Cartoes com as faturas futuras desdobradas, por card_id.
  const [showFuture, setShowFuture] = useState({})

  // As faturas em aberto por cartao, somadas no servidor (GET /api/cc-invoices):
  // a mesma regra da proxima fatura do Inicio e do sino.
  const invoicesQuery = useQuery({ queryKey: ['cartoes', 'faturas'], queryFn: () => ccInvoicesApi.list() })
  const invoiceData = invoicesQuery.data
  const openInvoicesByCard = useMemo(() => (invoiceData?.cards || NO_CARDS).map(cardGroupOf), [invoiceData])

  // A fatura em aberto com o vencimento mais proximo (atrasadas primeiro),
  // marcada pelo servidor: a tela a abre e o "Pagar fatura" do topo a paga.
  const nearestInvoice = useMemo(() => {
    for (const cardGroup of openInvoicesByCard) {
      const invoice = cardGroup.invoices.find((entry) => entry.nearest)
      if (invoice) return { invoice, cardGroup, key: `${cardGroup.cardId}|${invoice.invoiceKey}` }
    }
    return null
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
      toast(`Fatura ${cardGroup.cardName} ${formatInvoiceLabel(invoice.invoiceMonth, invoice.invoiceYear)} paga — ${formatCurrency(invoice.total)}${payer}.`)
      await fetchData()
    } catch (error) {
      setPayError(error.message || 'Não foi possível pagar a fatura.')
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteRefund = async (purchase) => {
    if (!(await confirmAction({ title: `Excluir o estorno "${purchase.description}"?`, message: 'O crédito sai da fatura.', confirmLabel: 'Excluir estorno' }))) return
    try {
      await ccExpensesApi.removePurchase(purchase.id)
      await fetchData()
    } catch (error) {
      setDataError(error.message || 'Não foi possível excluir o estorno.')
    }
  }

  const handleDeleteCCPurchase = async (purchase) => {
    // As parcelas desta compra, pelo id dela (o client_id, 035), contadas no
    // servidor: uma compra igual no mesmo dia (outra corrida de Uber) e outra
    // compra e fica. So as em aberto saem: uma parcela paga foi junto com o
    // pagamento da fatura, e o servidor a mantem.
    const openCount = purchase.installmentsOpen
    const paidCount = purchase.installmentsPaid

    const openText = openCount === 1 ? 'A parcela em aberto sai da fatura.' : `As ${openCount} parcelas em aberto saem das faturas.`
    const paidText = paidCount === 1
      ? 'A parcela já paga fica: saiu com o pagamento da fatura. Para tirá-la também, desfaça esse pagamento no Extrato.'
      : `As ${paidCount} parcelas já pagas ficam: saíram com o pagamento das faturas. Para tirá-las também, desfaça esses pagamentos no Extrato.`
    const message = paidCount > 0 ? `${openText} ${paidText}` : 'Todas as parcelas dela saem das faturas.'
    if (!(await confirmAction({ title: `Excluir a compra "${purchase.description}"?`, message, confirmLabel: 'Excluir compra' }))) return

    try {
      await ccExpensesApi.removePurchase(purchase.id)
      await fetchData()
    } catch (error) {
      setDataError(error.message || 'Não foi possível excluir a compra.')
    }
  }

  // Em atraso so depois do dia do vencimento, como no Inicio e no sino: no
  // proprio dia a fatura ainda se paga em dia (`past_due`, do servidor).
  const getInvoiceStatus = (invoice) => {
    if (invoice.pastDue) return <Badge tone="danger">Em atraso</Badge>
    if (invoice.closed) return <Badge tone="warning">Fechada</Badge>
    return <Badge>Aberta</Badge>
  }

  // Por que o botao Pagar esta (ou nao) ali, numa linha. Numa fatura futura
  // basta a data do fechamento; o "liberado depois" ja esta dito na primeira.
  const paymentHint = (invoice, cardGroup, future = false) => {
    if (invoice.total < 0) return 'O crédito do estorno abate a próxima fatura'
    if (!invoice.closed) {
      if (!invoice.closingDate) return 'Pagamento liberado após o fechamento'
      return future
        ? `Fecha em ${formatDateBR(invoice.closingDate)}`
        : `Fecha em ${formatDateBR(invoice.closingDate)} · pagamento liberado depois`
    }
    if (cardGroup.autopayAccountId && invoice.dueDate) {
      return `Débito automático em ${formatDateBR(invoice.dueDate)}`
    }
    return null
  }

  const openCreditTotal = invoiceData?.open_total || 0

  // "Pagar fatura" no cabecalho so quando a fatura mais proxima pode ser paga;
  // um botao cinza ali so repetia "ainda nao".
  const canPayNearest = Boolean(nearestInvoice?.invoice.closed)
  const headerActions = (
    <>
      <Button type="button" variant="secondary" icon={Plus} onClick={() => openNewEntry('CARD')}>Nova compra</Button>
      {cards.length > 0 ? (
        <Button type="button" variant="secondary" icon={Undo2} onClick={() => setRefundFor({})}>Estorno</Button>
      ) : null}
      {canPayNearest ? (
        <Button
          type="button"
          icon={CheckCircle}
          loading={saving}
          onClick={() => handlePayInvoice(nearestInvoice.invoice, nearestInvoice.cardGroup)}
        >
          Pagar fatura
        </Button>
      ) : null}
    </>
  )

  const renderInvoice = (invoice, cardGroup, { future = false } = {}) => {
    const key = `${cardGroup.cardId}|${invoice.invoiceKey}`
    const expanded = isInvoiceExpanded(key)
    const isNearest = key === nearestInvoice?.key
    const hint = paymentHint(invoice, cardGroup, future)

    return (
      <div key={invoice.invoiceKey}>
        <div className="flex items-center gap-3 px-5 py-2">
          <button
            type="button"
            onClick={() => toggleInvoice(key)}
            aria-expanded={expanded}
            className="flex min-h-[44px] min-w-0 flex-1 items-center gap-3 text-left"
          >
            <ChevronDown className={cx('h-5 w-5 shrink-0 text-zinc-500 transition-transform', expanded && 'rotate-180')} />
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <p className="font-semibold text-zinc-950">{formatInvoiceLabel(invoice.invoiceMonth, invoice.invoiceYear)}</p>
                {invoice.total < 0 ? <Badge tone="success">Crédito</Badge> : future ? null : getInvoiceStatus(invoice)}
                {isNearest ? <Badge>Próxima</Badge> : null}
              </div>
              {/* No celular o valor desce para baixo do rotulo: ao lado, com o
                  Pagar, sobravam ~40px e os selos passavam por cima dele. */}
              <p className="num mt-0.5 whitespace-nowrap font-semibold text-zinc-950 sm:hidden">{formatCurrency(invoice.total)}</p>
              {hint ? <p className="mt-0.5 truncate text-xs text-zinc-500">{hint}</p> : null}
            </div>
          </button>
          <p className="num hidden whitespace-nowrap font-semibold text-zinc-950 sm:block">{formatCurrency(invoice.total)}</p>
          {invoice.payable ? (
            <Button
              type="button"
              size="sm"
              variant={isNearest ? 'primary' : 'secondary'}
              icon={CheckCircle}
              loading={saving}
              onClick={() => handlePayInvoice(invoice, cardGroup)}
            >
              Pagar
            </Button>
          ) : null}
        </div>

        <Expand open={expanded} innerClassName="px-3 pb-4 sm:px-5">
          <ul className="divide-y divide-zinc-100 rounded-2xl border border-zinc-200/70">
            {invoice.purchases.map((purchase) => (
              <li key={purchase.purchaseKey} className="flex items-center gap-3 py-1.5 pl-4 pr-2">
                <div className="min-w-0 flex-1">
                  <p className="flex min-w-0 items-center gap-1.5 font-medium text-zinc-900" title={purchase.description}>
                    <span className="truncate">{purchase.description}</span>
                    {purchase.attachmentCount > 0 ? (
                      <Paperclip className="h-3.5 w-3.5 shrink-0 text-zinc-400" aria-label={`${purchase.attachmentCount} comprovante(s)`} />
                    ) : null}
                  </p>
                  <p className="truncate text-xs text-zinc-500">
                    {purchase.refund ? 'Estorno · ' : ''}{purchase.category} · {formatDateBR(purchase.purchase_date)}
                    {purchase.installmentTotal > 1 ? ` · parcela ${purchase.installmentCurrent}/${purchase.installmentTotal}` : ''}
                  </p>
                  {purchase.shareText ? <p className="truncate text-xs font-medium text-zinc-500">{purchase.shareText}</p> : null}
                </div>
                {purchase.refund ? (
                  <p className="num whitespace-nowrap font-semibold text-emerald-700">{formatSignedCurrency(purchase.amount)}</p>
                ) : (
                  <p className="num whitespace-nowrap font-semibold text-zinc-950">{formatCurrency(purchase.amount)}</p>
                )}
                <Menu
                  label={`Ações de ${purchase.description}`}
                  items={purchase.refund ? [
                    {
                      label: purchase.attachmentCount > 0 ? `Comprovantes (${purchase.attachmentCount})` : 'Comprovantes',
                      icon: Paperclip,
                      onSelect: () => setAttachmentsFor(purchase),
                    },
                    {
                      label: 'Excluir estorno',
                      icon: Trash2,
                      tone: 'danger',
                      onSelect: () => handleDeleteRefund(purchase),
                    },
                  ] : [
                    {
                      label: 'Registrar estorno',
                      icon: Undo2,
                      onSelect: () => setRefundFor({ purchase }),
                    },
                    {
                      label: 'De quem é?',
                      icon: Users,
                      onSelect: () => setShareFor(purchase),
                    },
                    {
                      label: purchase.attachmentCount > 0 ? `Comprovantes (${purchase.attachmentCount})` : 'Comprovantes',
                      icon: Paperclip,
                      onSelect: () => setAttachmentsFor(purchase),
                    },
                    {
                      label: purchase.installmentTotal > 1 ? 'Excluir compra e parcelas' : 'Excluir compra',
                      icon: Trash2,
                      tone: 'danger',
                      onSelect: () => handleDeleteCCPurchase(purchase),
                    },
                  ]}
                />
              </li>
            ))}
          </ul>
        </Expand>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Cartões"
        description={nearestInvoice
          ? `Próxima fatura: ${nearestInvoice.cardGroup.cardName} ${formatInvoiceLabel(nearestInvoice.invoice.invoiceMonth, nearestInvoice.invoice.invoiceYear)} · ${formatCurrency(nearestInvoice.invoice.total)} · ${formatCurrency(openCreditTotal)} em aberto nos cartões`
          : 'Faturas em aberto por cartão.'}
        actions={headerActions}
      />

      <AlertMessage tone="warning" message={dataError} onDismiss={() => setDataError('')} />

      <CardRefundSheet
        target={refundFor}
        cards={cards}
        onClose={() => setRefundFor(null)}
        onSaved={fetchData}
      />
      <CardShareSheet
        purchase={shareFor}
        onClose={() => setShareFor(null)}
        onSaved={fetchData}
      />
      <AttachmentsSheet
        purchase={attachmentsFor}
        onClose={() => setAttachmentsFor(null)}
        onChanged={fetchData}
      />
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

      {loading || invoicesQuery.isPending ? (
        <Panel className="overflow-clip">
          <ListSkeleton rows={4} />
        </Panel>
      ) : cards.length === 0 ? (
        <Panel className="p-5">
          <EmptyState
            icon={CreditCard}
            title="Nenhum cartão cadastrado"
            message="Os cartões ficam em Ajustes. Depois disso, registre compras pelo botão Novo."
            action={<Link to="/ajustes#cartoes" className="text-sm font-semibold text-emerald-700 underline-offset-2 hover:underline">Cadastrar cartão em Ajustes</Link>}
          />
        </Panel>
      ) : openInvoicesByCard.length > 0 ? (
        <div className="grid grid-cols-[minmax(0,1fr)] gap-4 xl:grid-cols-2 xl:items-start">
          {openInvoicesByCard.map((cardGroup) => {
            const cardTotal = cardGroup.total
            // A fatura e a unidade: ficam a mostra as que pedem algo (em atraso
            // ou fechadas) e a que esta correndo; as futuras (`future`, depois
            // da primeira ainda aberta), que so repetem as parcelas, ficam
            // dobradas com o total delas.
            const current = cardGroup.invoices.filter((invoice) => !invoice.future)
            const future = cardGroup.invoices.filter((invoice) => invoice.future)
            const futureTotal = future.reduce((acc, invoice) => acc + invoice.total, 0)
            const futureOpen = Boolean(showFuture[cardGroup.cardId])
            const lastFuture = future[future.length - 1]

            return (
              <Panel key={cardGroup.cardId} className="overflow-clip">
                <div className="flex items-start justify-between gap-4 px-5 pb-3 pt-5">
                  <div className="min-w-0">
                    <h3 className="truncate text-lg font-bold text-zinc-950">{cardGroup.cardName}</h3>
                    <p className="mt-0.5 text-sm text-zinc-500">
                      Fecha dia {cardGroup.closingDay} · vence dia {cardGroup.dueDay}
                      {cardGroup.autopayAccountId ? ` · débito automático em ${accountName(cardGroup.autopayAccountId)}` : ''}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="text-xs font-semibold text-zinc-500">Em aberto</p>
                    <p className="num text-lg font-bold text-zinc-950">{formatCurrency(cardTotal)}</p>
                  </div>
                </div>

                <div className="divide-y divide-zinc-100 border-t border-zinc-100">
                  {current.map((invoice) => renderInvoice(invoice, cardGroup))}
                </div>

                {future.length > 0 ? (
                  <div className="border-t border-zinc-100">
                    <button
                      type="button"
                      onClick={() => setShowFuture((prev) => ({ ...prev, [cardGroup.cardId]: !futureOpen }))}
                      aria-expanded={futureOpen}
                      className="flex min-h-[44px] w-full items-center gap-3 px-5 py-2 text-left text-sm font-semibold text-zinc-600 hover:text-zinc-950"
                    >
                      <ChevronDown className={cx('h-5 w-5 shrink-0 text-zinc-500 transition-transform', futureOpen && 'rotate-180')} />
                      <span className="min-w-0 flex-1">
                        {future.length === 1 ? 'Fatura seguinte' : `Próximas ${future.length} faturas`}
                        <span className="font-normal text-zinc-500"> · até {formatInvoiceLabel(lastFuture.invoiceMonth, lastFuture.invoiceYear)}</span>
                      </span>
                      <span className="num whitespace-nowrap">{formatCurrency(futureTotal)}</span>
                    </button>
                    <Expand open={futureOpen}>
                      <div className="divide-y divide-zinc-100 border-t border-zinc-100 bg-zinc-50/60">
                        {future.map((invoice) => renderInvoice(invoice, cardGroup, { future: true }))}
                      </div>
                    </Expand>
                  </div>
                ) : null}
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
