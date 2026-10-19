import { useState } from 'react'
import { createPortal } from 'react-dom'
import { Download, Pencil, Plus, Receipt, Trash2 } from 'lucide-react'
import InvestmentLaunchModal from '../../components/InvestmentLaunchModal'
import FixedIncomeFields from '../../components/FixedIncomeFields'
import CashLinkField, { cashLinkFromMetadata, cashLinkMetadata } from '../../components/CashLinkField'
import {
  AlertMessage,
  Badge,
  Button,
  EmptyState,
  ListSkeleton,
  Field,
  Menu,
  PageHeader,
  Panel,
  PanelHeader,
  Sheet,
  SummaryPanel,
  cx,
} from '../../components/ui'
import { investmentsApi } from '../../lib/dataApi'
import { parseTreasuryUnits } from '../../lib/treasury'
import { formatCurrency, formatSignedCurrency } from '../../lib/format'
import {
  FIXED_INCOME_METADATA_KEYS,
  fixedIncomeFormFromMetadata,
  fixedIncomeMetadataFromForm,
} from '../../lib/fixedIncome'
import {
  formatPercent,
  getClassLabel,
  hasRealizedResult,
  movementDateValue,
  movementFees,
  movementTotalValue,
  movementUnitPrice,
  parseNumberInput,
} from './helpers'
import useInvestments from './useInvestments'
import { toast } from '../../lib/toast'
import { confirmAction } from '../../lib/confirm'
import ExportSheet from '../../components/ExportSheet'
import CorporateActionsPanel from './CorporateActionsPanel'
import AportesChart from './AportesChart'

const EDIT_FORM_ID = 'investment-movement-edit'

// Leitura de uma linha do historico, usada pela tabela e pelos cartoes.
function describeMovement(mov) {
  const isFixed = mov.asset_class === 'FIXED_INCOME'
  const isSale = mov.quantity < 0
  const isRedemption = !!mov.metadata?.is_redemption
  const unitPrice = movementUnitPrice(mov)
  const totalValue = movementTotalValue(mov)
  const fees = movementFees(mov)
  const hasResult = hasRealizedResult(mov)
  const netProceeds = hasResult
    ? Number(mov.realized_net_proceeds || 0)
    : Math.max(totalValue - fees, 0)
  const realizedProfit = Number(mov.realized_profit || 0)
  const realizedTax = Number(mov.realized_tax_amount || 0)
  const afterTax = Number(mov.realized_net_profit_after_tax || 0)
  const realizedMetadata = mov.realized_metadata || {}
  const allocationCount = Array.isArray(realizedMetadata.allocations)
    ? realizedMetadata.allocations.length
    : 0

  const dateValue = movementDateValue(mov)
  const hasCustomDate = dateValue && dateValue !== mov.created_at
  const dateObj = hasCustomDate
    ? new Date(`${String(dateValue).slice(0, 10)}T00:00:00`)
    : new Date(mov.created_at)
  const dateLabel = `${dateObj.toLocaleDateString('pt-BR')}${!hasCustomDate ? ` às ${dateObj.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}` : ''}`
  // Evento corporativo (017): a bonificacao e uma operacao propria; as
  // operacoes anteriores a um desdobramento aparecem na base nova, marcadas.
  const isBonus = Boolean(mov.metadata?.corporate_action_id)
  const adjusted = (mov.metadata?.corporate_adjustments || []).length > 0
  const kind = isBonus ? 'Bonificação' : isFixed ? (isSale ? 'Resgate' : 'Aporte') : (isSale ? 'Venda' : 'Compra')
  const quantityText = Math.abs(Number(mov.quantity)).toLocaleString('pt-BR', { maximumFractionDigits: 6 })
  const kindDetail = isRedemption
    ? formatCurrency(totalValue)
    : isFixed ? '' : `${quantityText} un.${adjusted ? ' · ajustada por evento' : ''}`
  // A operacao tem lancamento no Extrato quando saiu de uma conta (CashLinkField).
  const inStatement = cashLinkFromMetadata(mov.metadata).enabled
  const kindDetailWithCash = inStatement
    ? [kindDetail, 'no extrato'].filter(Boolean).join(' · ')
    : kindDetail
  const kindLabel = `${kind} de ${isRedemption ? formatCurrency(totalValue) : quantityText}`

  return {
    isSale,
    isBonus,
    dateText: dateObj.toLocaleDateString('pt-BR'),
    timeText: hasCustomDate ? '' : dateObj.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }),
    kind,
    kindDetail: kindDetailWithCash,
    inStatement,
    unitPrice,
    totalValue,
    fees,
    hasResult,
    netProceeds,
    realizedProfit,
    realizedTax,
    afterTax,
    realizedMetadata,
    allocationCount,
    dateLabel,
    kindLabel,
  }
}

export default function Operacoes() {
  const {
    movementsLoading,
    assets,
    movements,
    dataError,
    setDataError,
    refreshAll,
    handleUpdateStockPrices,
  } = useInvestments()

  const [loading, setLoading] = useState(false)
  const [editModal, setEditModal] = useState(null)
  // Erro da edicao dentro do sheet: o aviso da pagina fica atras dele.
  const [editError, setEditError] = useState('')
  const [isLaunchModalOpen, setIsLaunchModalOpen] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)

  const openEditModal = (mov) => {
    const movementDate = movementDateValue(mov)
    const cashLink = cashLinkFromMetadata(mov.metadata)
    setEditError('')
    setEditModal({
      id: mov.id,
      asset_class: mov.asset_class,
      ticker_or_name: mov.ticker_or_name,
      // A quantidade aparece sem sinal: o tipo (compra, venda, resgate) e da
      // operacao gravada, e o "-" da venda e posto de volta ao salvar.
      quantity: Math.abs(Number(mov.quantity)),
      average_price: mov.average_price,
      current_price: mov.current_price,
      metadata: mov.metadata || {},
      is_sale: mov.quantity < 0 && mov.asset_class !== 'FIXED_INCOME',
      is_redemption: !!mov.metadata?.is_redemption,
      sale_price: mov.metadata?.sale_price || '',
      other_costs: mov.metadata?.other_costs ?? mov.fee_amount ?? '',
      fixed_income: fixedIncomeFormFromMetadata(mov.metadata || {}),
      // Compra do Tesouro: a quantidade de titulos do extrato da corretora.
      is_treasury_buy: mov.asset_category === 'TESOURO' && !mov.metadata?.is_redemption && Number(mov.quantity) > 0,
      treasury_units: mov.metadata?.treasury_units ? String(mov.metadata.treasury_units).replace('.', ',') : '',
      movement_date: movementDate ? String(movementDate).slice(0, 10) : '',
      cash_link: cashLink,
      saved_cash_account_id: cashLink.accountId,
    })
  }

  const handleSaveEdit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setDataError('')
    setEditError('')
    let saved = false

    try {
      const averagePrice = Number(editModal.average_price)
      const finalQuantity = editModal.asset_class === 'FIXED_INCOME' ? 1 : parseNumberInput(editModal.quantity)
      const otherCosts = editModal.other_costs === '' ? 0 : parseNumberInput(editModal.other_costs)
      const metadata = { ...(editModal.metadata || {}) }

      if (!Number.isFinite(averagePrice) || averagePrice < 0) {
        throw new Error('Informe um preço/valor válido.')
      }
      if (!Number.isFinite(otherCosts) || otherCosts < 0) {
        throw new Error('Informe custos válidos.')
      }
      if (editModal.is_sale) {
        const salePrice = Number(editModal.sale_price || 0)
        if (!Number.isFinite(salePrice) || salePrice <= 0) {
          throw new Error('Informe um preço de venda válido.')
        }
      }
      if (!editModal.is_redemption && (!Number.isFinite(finalQuantity) || finalQuantity <= 0)) {
        throw new Error('Informe uma quantidade válida.')
      }

      delete metadata.purchase_date
      delete metadata.sale_date
      delete metadata.redemption_date
      metadata.other_costs = otherCosts
      // A conta da carteira, ou `null` quando marcado "Não descontar de nenhuma conta".
      Object.assign(metadata, cashLinkMetadata(editModal.cash_link, { editing: true }))

      if (editModal.is_redemption) {
        metadata.redemption_date = editModal.movement_date
        metadata.is_redemption = true
      } else if (editModal.is_sale) {
        metadata.sale_date = editModal.movement_date
        metadata.sale_price = Number(editModal.sale_price || editModal.current_price || averagePrice)
      } else {
        metadata.purchase_date = editModal.movement_date
      }

      if (editModal.asset_class === 'FIXED_INCOME' && !editModal.is_redemption) {
        FIXED_INCOME_METADATA_KEYS.forEach((key) => delete metadata[key])
        Object.assign(metadata, fixedIncomeMetadataFromForm(editModal.fixed_income))
      }
      if (editModal.is_treasury_buy) {
        const units = parseTreasuryUnits(editModal.treasury_units)
        if (Number.isNaN(units)) throw new Error('Informe uma quantidade de títulos válida.')
        if (units === null) delete metadata.treasury_units
        else metadata.treasury_units = units
      }

      await investmentsApi.update(editModal.id, {
        // Venda e resgate saem com o "-"; o servidor tambem guarda o sinal da
        // operacao gravada, entao a quantidade sem sinal nunca vira uma compra.
        quantity: editModal.is_redemption
          ? -Math.abs(Number(editModal.quantity))
          : editModal.is_sale ? -finalQuantity : finalQuantity,
        average_price: averagePrice,
        metadata: metadata
      })
      saved = true

      setEditModal(null)
      toast('Operação atualizada.')
      // A gravacao ja invalidou o cache (lib/api.js). A cotacao vai por tras:
      // esperar por ela (yfinance) e pela nova busca de toda tela aberta
      // deixava o "Salvar" girando, e o `loading` e o mesmo da proxima edicao.
      handleUpdateStockPrices(true, editModal.id)
    } catch (error) {
      const message = 'Erro ao guardar edição: ' + error.message
      if (saved) setDataError(message)
      else setEditError(message)
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteMovement = async (id) => {
    if (await confirmAction({ title: 'Excluir esta operação?', message: 'Só esta operação sai do histórico; as outras do ativo continuam.', confirmLabel: 'Excluir' })) {
      try {
        await investmentsApi.remove(id)
        toast('Operação excluída.')
        await refreshAll()
      } catch (error) {
        setDataError(error.message || 'Não foi possível excluir a operação.')
      }
    }
  }

  const realizedMovements = movements.filter(hasRealizedResult)
  const realizedSummary = realizedMovements.reduce((acc, movement) => {
    acc.realizedProfit += Number(movement.realized_profit || 0)
    acc.taxAmount += Number(movement.realized_tax_amount || 0)
    acc.netProfitAfterTax += Number(movement.realized_net_profit_after_tax || 0)
    acc.netProceeds += Number(movement.realized_net_proceeds || 0)
    acc.costBasis += Number(movement.realized_cost_basis || 0)
    return acc
  }, {
    realizedProfit: 0,
    taxAmount: 0,
    netProfitAfterTax: 0,
    netProceeds: 0,
    costBasis: 0,
  })

  const setEditField = (field, value) => setEditModal({ ...editModal, [field]: value })

  return (
    <div className="space-y-6">
      <PageHeader
        title="Operações"
        description="Compras, vendas, aportes e resgates, com o resultado realizado e o IR estimado."
        actions={(
          <>
            <Button type="button" variant="secondary" icon={Download} disabled={movements.length === 0} onClick={() => setExportOpen(true)}>
              Exportar
            </Button>
            <Button type="button" icon={Plus} onClick={() => setIsLaunchModalOpen(true)}>
              Registrar operação
            </Button>
          </>
        )}
      />

      <AlertMessage tone="warning" message={dataError} onDismiss={() => setDataError('')} />

      {realizedMovements.length > 0 ? (
        <SummaryPanel
          lead={{
            label: 'Resultado pós-IR',
            value: formatSignedCurrency(realizedSummary.netProfitAfterTax),
            hint: `${realizedMovements.length} venda(s) e resgate(s) com resultado`,
            tone: realizedSummary.netProfitAfterTax >= 0 ? 'gain' : 'loss',
          }}
          figures={[
            {
              label: 'Lucro/prejuízo realizado',
              value: formatSignedCurrency(realizedSummary.realizedProfit),
              hint: 'Antes do IR',
              tone: realizedSummary.realizedProfit >= 0 ? 'gain' : 'loss',
            },
            { label: 'IR estimado', value: formatCurrency(realizedSummary.taxAmount), hint: 'Parte de cada venda no IR do mês, e o retido na renda fixa' },
            { label: 'Base de custo vendida', value: formatCurrency(realizedSummary.costBasis), hint: 'Custo médio e títulos resgatados' },
          ]}
        />
      ) : null}

      <AportesChart />

      <Panel className="overflow-clip">
        <PanelHeader
          title="Operações"
          description="Compras e vendas da sua carteira."
          actions={<Badge>{movements.length} registro(s)</Badge>}
        />
        {movementsLoading ? (
          <ListSkeleton rows={6} />
        ) : movements.length === 0 ? (
          <div className="p-5">
            <EmptyState icon={Receipt} title="Nenhum histórico encontrado." message="As compras, vendas e resgates registrados aparecem aqui." />
          </div>
        ) : (
          <>
            <ul className="divide-y divide-zinc-100 xl:hidden">
              {movements.map((mov) => (
                <MovementCard
                  key={mov.id}
                  mov={mov}
                  info={describeMovement(mov)}
                  onEdit={() => openEditModal(mov)}
                  onDelete={() => handleDeleteMovement(mov.id)}
                />
              ))}
            </ul>

            <div className="hidden xl:block">
              <table className="app-table table-fixed">
                <colgroup>
                  <col className="w-32" />
                  <col />
                  <col className="w-28" />
                  <col className="w-36" />
                  <col className="w-44" />
                  <col className="w-44" />
                  <col className="w-16" />
                </colgroup>
                <thead>
                  <tr>
                    <th>Data</th>
                    <th>Ativo</th>
                    <th className="text-right">Preço</th>
                    <th className="text-right">Total</th>
                    <th className="text-right">Resultado</th>
                    <th className="text-right">IR estimado</th>
                    <th><span className="sr-only">Ações</span></th>
                  </tr>
                </thead>
                <tbody>
                  {movements.map((mov) => (
                    <MovementRow
                      key={mov.id}
                      mov={mov}
                      info={describeMovement(mov)}
                      onEdit={() => openEditModal(mov)}
                      onDelete={() => handleDeleteMovement(mov.id)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Panel>

      <CorporateActionsPanel assets={assets} />

      <ExportSheet
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        exportName="movements"
        title="Exportar operações"
        description="Todas as operações, da mais recente para a mais antiga, com o resultado realizado de cada venda."
        onExport={(options) => investmentsApi.exportMovements(options)}
      />

      <InvestmentLaunchModal
        open={isLaunchModalOpen}
        onClose={() => setIsLaunchModalOpen(false)}
        assets={assets}
        onSaved={refreshAll}
      />

      {createPortal((
      <Sheet
        open={Boolean(editModal)}
        onClose={() => setEditModal(null)}
        title="Editar operação"
        description={editModal ? `Ativo: ${editModal.ticker_or_name}` : undefined}
        footer={(
          <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <Button type="button" variant="secondary" size="lg" onClick={() => setEditModal(null)}>
              Cancelar
            </Button>
            <Button type="submit" form={EDIT_FORM_ID} size="lg" loading={loading}>
              Salvar
            </Button>
          </div>
        )}
      >
        {editModal ? (
          <form id={EDIT_FORM_ID} onSubmit={handleSaveEdit} className="space-y-4">
            <AlertMessage tone="danger" message={editError} onDismiss={() => setEditError('')} />

            {editModal.asset_class !== 'FIXED_INCOME' && (
              <Field label="Quantidade">
                <input type="number" min="0" step="any" inputMode="decimal" value={editModal.quantity} onChange={(e) => setEditField('quantity', e.target.value)} className="app-input" required />
              </Field>
            )}

            {/* Na venda o custo e o preco medio da posicao na data, calculado pelo
                servidor (custo medio ponderado): nao ha o que editar. */}
            {!editModal.is_sale && (
              <Field label={editModal.is_redemption ? 'Base de custo resgatada (R$)' : editModal.asset_class === 'FIXED_INCOME' ? 'Valor aplicado (R$)' : 'Preço médio/base de custo (R$)'}>
                <input type="number" step="0.01" value={editModal.average_price} onChange={(e) => setEditField('average_price', e.target.value)} className="app-input" required />
              </Field>
            )}

            {editModal.is_sale && (
              <Field label="Preço de venda (R$)" hint="O custo da venda é o preço médio da posição na data, calculado pelo app.">
                <input type="number" step="0.01" value={editModal.sale_price} onChange={(e) => setEditField('sale_price', e.target.value)} className="app-input" required />
              </Field>
            )}

            <Field label="Outros custos (R$)">
              <input type="number" min="0" step="0.01" value={editModal.other_costs} onChange={(e) => setEditField('other_costs', e.target.value)} className="app-input" />
            </Field>

            <Field label="Data da operação">
              <input type="date" value={editModal.movement_date} onChange={(e) => setEditField('movement_date', e.target.value)} className="app-input" required />
            </Field>

            <CashLinkField
              value={editModal.cash_link}
              onChange={(next) => setEditField('cash_link', next)}
              movementType={editModal.is_redemption ? 'REDEMPTION' : editModal.is_sale ? 'SELL' : 'BUY'}
              savedAccountId={editModal.saved_cash_account_id}
              selectClassName="app-select"
            />

            {editModal.is_treasury_buy && (
              <Field label="Quantidade de títulos (opcional)" hint="Como no extrato da corretora: o valor de mercado é essa quantidade × o preço do Tesouro. Vazio, o app calcula pelo preço do dia da compra.">
                <input type="text" inputMode="decimal" value={editModal.treasury_units} onChange={(e) => setEditField('treasury_units', e.target.value)} placeholder="Ex: 0,85" className="app-input" />
              </Field>
            )}

            {editModal.asset_class === 'FIXED_INCOME' && !editModal.is_redemption && (
              <FixedIncomeFields
                value={editModal.fixed_income}
                onChange={(next) => setEditField('fixed_income', next)}
                inputClassName="app-input"
                selectClassName="app-select"
              />
            )}
          </form>
        ) : null}
      </Sheet>
      ), document.body)}
    </div>
  )
}

function movementMenuItems(onEdit, onDelete) {
  return [
    { label: 'Editar operação', icon: Pencil, onSelect: onEdit },
    { label: 'Excluir só esta operação', icon: Trash2, tone: 'danger', onSelect: onDelete },
  ]
}

function profitClass(value) {
  return value > 0 ? 'text-emerald-700' : value < 0 ? 'text-rose-600' : 'text-zinc-500'
}

const COST_METHOD_LABELS = {
  AVERAGE: 'custo médio',
  FIFO: 'FIFO',
  LOT_REDEMPTION: 'resgate do título',
}

// "−11,90% · custo médio"
function realizedDetail(mov, info) {
  const costMethod = info.realizedMetadata.cost_method
  const method = COST_METHOD_LABELS[costMethod] || costMethod || 'custo médio'
  // Lotes so existiam no FIFO (resultado gravado antes do custo medio).
  const lots = costMethod === 'FIFO' && info.allocationCount ? `, ${info.allocationCount} lote${info.allocationCount > 1 ? 's' : ''}` : ''
  return `${formatPercent(mov.realized_profitability_percent, 2, { signed: true })} · ${method}${lots}`
}

// Duas linhas no maximo: o valor e um detalhe. O resto (base de custo,
// aliquota) fica no title da celula.
function MovementRow({ mov, info, onEdit, onDelete }) {
  return (
    <tr>
      <td className="text-zinc-600">
        <p className="whitespace-nowrap">{info.dateText}</p>
        {info.timeText ? <p className="text-xs text-zinc-500">{info.timeText}</p> : null}
      </td>
      <td>
        <p className="truncate font-semibold text-zinc-950" title={`${mov.ticker_or_name} · ${mov.asset_category_label || getClassLabel(mov.asset_class)}`}>{mov.ticker_or_name}</p>
        <p className="truncate text-xs text-zinc-500">
          <span className="font-medium text-zinc-700">{info.kind}</span>{info.kindDetail ? ` · ${info.kindDetail}` : ''}
        </p>
      </td>
      <td className="num text-zinc-700">{formatCurrency(info.unitPrice)}</td>
      <td className="num">
        <p className="font-semibold text-zinc-950">{formatCurrency(info.totalValue)}</p>
        {info.fees > 0 ? <p className="text-xs text-zinc-500">custos {formatCurrency(info.fees)}</p> : null}
      </td>
      <td className="num" title={info.hasResult ? `Base de custo: ${formatCurrency(mov.realized_cost_basis)} · Líquido da venda: ${formatCurrency(info.netProceeds)}` : undefined}>
        {info.hasResult ? (
          <>
            <p className={cx('font-semibold', profitClass(info.realizedProfit))}>{formatSignedCurrency(info.realizedProfit)}</p>
            <p className="truncate text-xs text-zinc-500" title={realizedDetail(mov, info)}>{realizedDetail(mov, info)}</p>
          </>
        ) : (
          <span className="text-zinc-400">—</span>
        )}
      </td>
      <td className="num" title={info.hasResult ? `Alíquota: ${formatPercent(Number(mov.realized_tax_rate || 0) * 100)}` : undefined}>
        {info.hasResult ? (
          <>
            <p className="font-medium text-zinc-900">{formatCurrency(info.realizedTax)}</p>
            <p className={cx('truncate text-xs', profitClass(info.afterTax))}>pós-IR {formatSignedCurrency(info.afterTax)}</p>
          </>
        ) : (
          <span className="text-zinc-400">—</span>
        )}
      </td>
      <td className="py-1.5 text-right">
        {info.isBonus ? null : <Menu label={`Ações da operação de ${mov.ticker_or_name}`} items={movementMenuItems(onEdit, onDelete)} />}
      </td>
    </tr>
  )
}

function MovementCard({ mov, info, onEdit, onDelete }) {
  return (
    <li className="space-y-2 px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-semibold text-zinc-950">{mov.ticker_or_name}</p>
          <p className="text-xs text-zinc-500">{(mov.asset_category_label || getClassLabel(mov.asset_class))} · {info.dateLabel}</p>
        </div>
        <p className="shrink-0 font-semibold text-zinc-950">{formatCurrency(info.totalValue)}</p>
      </div>
      {/* Acoes na mesma linha da operacao: uma fileira so para dois botoes
          dobrava a altura do cartao. */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-zinc-600">
          <span className="font-medium text-zinc-800">{info.kindLabel}</span>
          <span>a {formatCurrency(info.unitPrice)}</span>
          {info.fees > 0 ? <span>· Custos {formatCurrency(info.fees)}</span> : null}
          {info.isSale ? <span>· Líquido {formatCurrency(info.netProceeds)}</span> : null}
          {info.inStatement ? <span>· No extrato</span> : null}
        </div>
        {info.isBonus ? null : <Menu label={`Ações da operação de ${mov.ticker_or_name}`} size="md" items={movementMenuItems(onEdit, onDelete)} />}
      </div>
      {info.hasResult ? (
        <div className="grid grid-cols-2 gap-3 rounded-lg bg-zinc-50 px-3 py-2 text-sm tabular">
          <div>
            <p className="text-xs text-zinc-600">Resultado</p>
            <p className={cx('font-semibold', profitClass(info.realizedProfit))}>{formatSignedCurrency(info.realizedProfit)}</p>
            <p className="text-xs text-zinc-600">Base: {formatCurrency(mov.realized_cost_basis)}</p>
            <p className="text-xs text-zinc-600">{realizedDetail(mov, info)}</p>
          </div>
          <div>
            <p className="text-xs text-zinc-600">IR estimado</p>
            <p className="font-medium text-zinc-900">{formatCurrency(info.realizedTax)}</p>
            <p className={cx('text-xs font-medium', profitClass(info.afterTax))}>Pós-IR: {formatSignedCurrency(info.afterTax)}</p>
            <p className="text-xs text-zinc-600">Alíq.: {formatPercent(Number(mov.realized_tax_rate || 0) * 100)}</p>
          </div>
        </div>
      ) : null}
    </li>
  )
}
