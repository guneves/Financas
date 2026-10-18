import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { ArrowDownRight, ArrowUpRight, CalendarDays } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { investmentsApi, marketApi } from '../lib/dataApi'
import { AlertMessage, Button, Field, SegmentedControl, Sheet } from './ui'
import { formatCurrency, getLocalDateString } from '../lib/format'
import { usePrivateFormatter } from '../lib/privacy'
import { toast } from '../lib/toast'
import TickerAutocomplete from './TickerAutocomplete'
import FixedIncomeFields from './FixedIncomeFields'
import CashLinkField, { cashLinkMetadata, emptyCashLink } from './CashLinkField'
import { SaleExemptionNotice } from './ExemptionMeter'
import { emptyFixedIncomeForm, fixedIncomeMetadataFromForm } from '../lib/fixedIncome'

// Classes com cotacao na B3: o ativo tem de vir do catalogo, nao de texto livre.
const CATALOG_ASSET_CLASSES = ['STOCKS', 'REIT']

const ASSET_TYPES = [
  { value: 'STOCKS', label: 'Ações' },
  { value: 'REIT', label: 'Fundos Imobiliários' },
  { value: 'FIXED_INCOME', label: 'Renda Fixa' },
  { value: 'BITCOIN', label: 'Bitcoin' },
  { value: 'OTHER', label: 'Outros' },
]

// Bitcoin e um tipo so na tela: na API e a classe "Outros" com o ticker BTC,
// cotado em reais (BTC-BRL) e com o IR de criptoativo.
const BITCOIN = 'BITCOIN'
const BITCOIN_TICKER = 'BTC'

function movementAssetClass(assetType) {
  return assetType === BITCOIN ? 'OTHER' : assetType
}

function assetTypeOf(asset) {
  if (!asset) return 'STOCKS'
  return asset.market_kind === 'CRIPTO' ? BITCOIN : asset.class
}

const FORM_ID = 'investment-launch-form'

const MODE_ITEMS = [
  { value: 'BUY', label: 'Compra', icon: ArrowUpRight },
  { value: 'SELL', label: 'Venda', icon: ArrowDownRight },
]

const initialForm = () => ({
  asset_class: 'STOCKS',
  ticker_or_name: '',
  asset_id: '',
  ticker_confirmed: false,
  transaction_date: getLocalDateString(),
  quantity: '1',
  price: '',
  other_costs: '',
  fixed_income: emptyFixedIncomeForm(),
  // Sai da conta da carteira, a nao ser que o dono marque a caixa (CashLinkField).
  cash_link: emptyCashLink(),
})

// Preco sugerido na venda: a cotacao da carteira. O app e so em reais.
function saleUnitPrice(asset) {
  if (!asset) return ''
  return asset.current_price ? String(asset.current_price) : ''
}

function parseAmount(value) {
  const rawValue = String(value || '').trim()
  const normalized = rawValue.includes(',')
    ? rawValue.replace(/\./g, '').replace(',', '.')
    : rawValue
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : 0
}

function normalizeAssetName(value) {
  return String(value || '').trim().toUpperCase()
}

export default function InvestmentLaunchModal({
  open,
  onClose,
  assets = [],
  onSaved,
  initialMode = 'BUY',
  initialAssetId = '',
}) {
  // Venda: o valor de cada posicao some no modo privado.
  const privateMoney = usePrivateFormatter(formatCurrency)
  const [mode, setMode] = useState('BUY')
  const [form, setForm] = useState(() => initialForm())
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (open) {
      const nextMode = initialMode === 'SELL' ? 'SELL' : 'BUY'
      const selectedAsset = assets.find((asset) => String(asset.id) === String(initialAssetId))
      setMode(nextMode)
      setForm({
        ...initialForm(),
        asset_id: nextMode === 'SELL' && selectedAsset ? String(selectedAsset.id) : '',
        asset_class: nextMode === 'SELL' ? assetTypeOf(selectedAsset) : 'STOCKS',
        ticker_or_name: nextMode === 'SELL' && selectedAsset ? selectedAsset.ticker || selectedAsset.name || '' : '',
        price: nextMode === 'SELL' ? saleUnitPrice(selectedAsset) : '',
      })
      setError('')
    }
  }, [open, initialMode, initialAssetId, assets])

  const saleAssets = useMemo(() => {
    return assets
      .filter((asset) => asset.class !== 'FIXED_INCOME' && Number(asset.quantity || 0) > 0)
      .sort((a, b) => String(a.name).localeCompare(String(b.name)))
  }, [assets])

  const selectedSaleAsset = useMemo(() => {
    return saleAssets.find((asset) => String(asset.id) === String(form.asset_id))
  }, [form.asset_id, saleAssets])

  const quantity = mode === 'BUY' && form.asset_class === 'FIXED_INCOME' ? 1 : parseAmount(form.quantity)
  const unitPrice = parseAmount(form.price)
  const otherCosts = parseAmount(form.other_costs)
  const totalValue = mode === 'SELL'
    ? Math.max((quantity * unitPrice) - otherCosts, 0)
    : form.asset_class === 'FIXED_INCOME'
      ? unitPrice + otherCosts
      : (quantity * unitPrice) + otherCosts

  const usesCatalog = mode === 'BUY' && CATALOG_ASSET_CLASSES.includes(form.asset_class)

  const updateForm = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }))
  }

  const handleTickerChange = (ticker, option) => {
    setForm((current) => ({
      ...current,
      ticker_or_name: ticker,
      // Guardado para nao repetir a consulta ao catalogo no submit.
      ticker_confirmed: Boolean(option),
    }))
  }

  const handleAssetClassChange = (nextClass) => {
    setForm((current) => ({
      ...current,
      asset_class: nextClass,
      ticker_or_name: nextClass === BITCOIN ? BITCOIN_TICKER : '',
      ticker_confirmed: false,
    }))
  }

  const handleModeChange = (nextMode) => {
    setMode(nextMode)
    setError('')
    setForm((current) => ({
      ...current,
      asset_id: '',
      ticker_or_name: '',
      quantity: '1',
      price: '',
      other_costs: '',
      asset_class: nextMode === 'SELL' ? 'STOCKS' : current.asset_class,
    }))
  }

  const handleSaleAssetChange = (assetId) => {
    const asset = saleAssets.find((item) => String(item.id) === String(assetId))
    setForm((current) => ({
      ...current,
      asset_id: assetId,
      asset_class: asset ? assetTypeOf(asset) : current.asset_class,
      ticker_or_name: asset?.ticker || asset?.name || '',
      price: saleUnitPrice(asset) || current.price,
    }))
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setSaving(true)
    setError('')

    try {
      if (mode === 'BUY') {
        await createBuyMovement()
      } else {
        await createSellMovement()
      }

      await onSaved?.()
      onClose()
      const assetName = normalizeAssetName(form.ticker_or_name)
      toast(mode === 'BUY' ? `Compra de ${assetName} registrada.` : `Venda de ${assetName} registrada.`)
    } catch (submitError) {
      setError(submitError.message || 'Não foi possível salvar o lançamento.')
    } finally {
      setSaving(false)
    }
  }

  // O ativo pode ter sido digitado inteiro sem passar pela lista. Antes de
  // lancar, confirma no catalogo -- ou aceita uma posicao que ja esta na
  // carteira, caso de papeis anteriores ao catalogo.
  const ensureKnownTicker = async (ticker) => {
    const inWallet = assets.some((asset) => normalizeAssetName(asset.ticker || asset.name) === ticker)
    if (inWallet) return

    try {
      await marketApi.ticker(ticker)
    } catch {
      throw new Error(`${ticker} não está na lista da B3. Selecione um ativo pela busca.`)
    }
  }

  const createBuyMovement = async () => {
    const tickerName = normalizeAssetName(form.ticker_or_name)
    if (!tickerName) throw new Error('Informe o ativo do lançamento.')
    if (usesCatalog && !form.ticker_confirmed) {
      await ensureKnownTicker(tickerName)
    }
    if (unitPrice <= 0) throw new Error('Informe um preço válido.')
    if (form.asset_class !== 'FIXED_INCOME' && quantity <= 0) throw new Error('Informe uma quantidade válida.')

    const finalQuantity = form.asset_class === 'FIXED_INCOME' ? 1 : quantity
    const grossValue = form.asset_class === 'FIXED_INCOME' ? unitPrice : unitPrice * finalQuantity
    const averagePrice = form.asset_class === 'FIXED_INCOME'
      ? grossValue + otherCosts
      : (grossValue + otherCosts) / finalQuantity

    const existingAsset = assets.find((asset) => {
      const currentTicker = normalizeAssetName(asset.ticker || asset.name)
      return currentTicker === tickerName
    })

    const baseMetadata = form.asset_class === 'FIXED_INCOME'
      ? {
          ...fixedIncomeMetadataFromForm(form.fixed_income),
          purchase_date: form.transaction_date,
          other_costs: otherCosts,
        }
      : {
          purchase_date: form.transaction_date,
          other_costs: otherCosts,
        }
    const metadata = { ...baseMetadata, ...cashLinkMetadata(form.cash_link) }

    const insertedData = await investmentsApi.create([
      {
        asset_class: movementAssetClass(form.asset_class),
        ticker_or_name: tickerName,
        quantity: finalQuantity,
        average_price: Number(averagePrice.toFixed(6)),
        current_price: existingAsset ? existingAsset.current_price : unitPrice,
        metadata,
      },
    ])

    const createdId = insertedData?.[0]?.id
    if (createdId) {
      try {
        await apiFetch('/api/investments/update-prices', {
          method: 'POST',
          body: JSON.stringify({ investment_id: createdId }),
        })
      } catch (priceError) {
        console.warn('Não foi possível atualizar a cotação após o lançamento:', priceError)
      }
    }
  }

  const createSellMovement = async () => {
    if (!selectedSaleAsset) throw new Error('Selecione o ativo para venda.')
    if (quantity <= 0) throw new Error('Informe uma quantidade válida.')
    if (quantity > Number(selectedSaleAsset.quantity || 0)) {
      throw new Error('A quantidade informada é maior do que a posição disponível.')
    }
    if (unitPrice <= 0) throw new Error('Informe o preço da venda.')

    await investmentsApi.create([
      {
        asset_class: selectedSaleAsset.class,
        ticker_or_name: selectedSaleAsset.ticker || selectedSaleAsset.name,
        quantity: -quantity,
        average_price: selectedSaleAsset.average_price,
        current_price: selectedSaleAsset.current_price,
        metadata: {
          sale_date: form.transaction_date,
          sale_price: unitPrice,
          other_costs: otherCosts,
          ...cashLinkMetadata(form.cash_link),
        },
      },
    ])
  }

  // Portal: o wrapper animado do Layout tem transform, o que prenderia o
  // `fixed` do Sheet a caixa da pagina em vez da janela.
  return createPortal((
    <Sheet
      open={open}
      onClose={onClose}
      title="Registrar operação"
      description="Compra ou venda. O resgate de renda fixa fica na linha do ativo, em Posição."
      className="sm:max-w-3xl"
      footer={(
        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Button type="button" variant="secondary" size="lg" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form={FORM_ID} size="lg" loading={saving}>
            {mode === 'BUY' ? 'Salvar compra' : 'Salvar venda'}
          </Button>
        </div>
      )}
    >
      <form id={FORM_ID} onSubmit={handleSubmit} className="space-y-5">
        <SegmentedControl
          items={MODE_ITEMS}
          value={mode}
          onChange={handleModeChange}
          className="grid w-full grid-cols-2 [&>button]:h-11"
        />

        <AlertMessage tone="danger" message={error} />

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Field label="Tipo de ativo">
            <select
              value={form.asset_class}
              onChange={(event) => handleAssetClassChange(event.target.value)}
              disabled={mode === 'SELL'}
              className="app-select h-11"
            >
              {ASSET_TYPES.map((type) => (
                <option key={type.value} value={type.value}>{type.label}</option>
              ))}
            </select>
          </Field>

          <Field label="Ativo">
            {mode === 'BUY' && form.asset_class === BITCOIN ? (
              <div className="app-input flex h-11 items-center text-zinc-700">
                Bitcoin (BTC) · cotação automática em reais
              </div>
            ) : mode === 'BUY' && usesCatalog ? (
              <TickerAutocomplete
                value={form.ticker_or_name}
                onChange={handleTickerChange}
                assetClass={form.asset_class}
                walletAssets={assets}
                required
              />
            ) : mode === 'BUY' ? (
              <>
                <input
                  list="investment-assets"
                  value={form.ticker_or_name}
                  onChange={(event) => updateForm('ticker_or_name', event.target.value)}
                  placeholder={form.asset_class === 'FIXED_INCOME' ? 'Ex: CDB Banco X 2027' : 'Selecionar ou digitar'}
                  className="app-input h-11"
                  required
                />
                <datalist id="investment-assets">
                  {assets.filter((asset) => asset.class === form.asset_class).map((asset) => (
                    <option key={asset.id} value={asset.ticker || asset.name} />
                  ))}
                </datalist>
              </>
            ) : (
              <select
                value={form.asset_id}
                onChange={(event) => handleSaleAssetChange(event.target.value)}
                className="app-select h-11"
                required
              >
                <option value="">Selecionar</option>
                {saleAssets.map((asset) => (
                  <option key={asset.id} value={asset.id}>
                    {asset.name} - {privateMoney(asset.current_value)}
                  </option>
                ))}
              </select>
            )}
          </Field>

          <Field label="Data da operação">
            <div className="relative">
              <CalendarDays className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
              <input
                type="date"
                value={form.transaction_date}
                onChange={(event) => updateForm('transaction_date', event.target.value)}
                className="app-input h-11 pl-10"
                required
              />
            </div>
          </Field>

          {form.asset_class === 'FIXED_INCOME' && mode === 'BUY' ? null : (
            <Field label="Quantidade">
              <input
                type="number"
                min="0"
                step={form.asset_class === BITCOIN ? 'any' : '0.0001'}
                inputMode="decimal"
                value={form.quantity}
                onChange={(event) => updateForm('quantity', event.target.value)}
                className="app-input h-11"
                required
              />
            </Field>
          )}

          <Field label={form.asset_class === 'FIXED_INCOME' && mode === 'BUY' ? 'Valor aplicado em R$' : 'Preço em R$'}>
            <input
              type="number"
              min="0"
              step="0.01"
              inputMode="decimal"
              value={form.price}
              onChange={(event) => updateForm('price', event.target.value)}
              placeholder="0,00"
              className="app-input h-11"
              required
            />
          </Field>

          <Field label="Outros custos (opcional)">
            <input
              type="number"
              min="0"
              step="0.01"
              inputMode="decimal"
              value={form.other_costs}
              onChange={(event) => updateForm('other_costs', event.target.value)}
              placeholder="0,00"
              className="app-input h-11"
            />
          </Field>

          {mode === 'BUY' && form.asset_class === 'FIXED_INCOME' ? (
            <FixedIncomeFields
              value={form.fixed_income}
              onChange={(next) => updateForm('fixed_income', next)}
            />
          ) : null}
        </div>

        {mode === 'SELL' && saleAssets.length === 0 ? (
          <AlertMessage tone="warning">
            Não há ativos de renda variável disponíveis para venda. Resgates de renda fixa continuam na linha do ativo.
          </AlertMessage>
        ) : null}

        {mode === 'SELL' && selectedSaleAsset?.class === 'STOCKS' ? (
          <SaleExemptionNotice
            date={form.transaction_date}
            amount={quantity * unitPrice}
            ticker={selectedSaleAsset.ticker || selectedSaleAsset.name}
          />
        ) : null}

        <CashLinkField
          value={form.cash_link}
          onChange={(next) => updateForm('cash_link', next)}
          movementType={mode}
          enabled={open}
        />

        <div className="flex items-center justify-between rounded-lg bg-zinc-100 px-4 py-3">
          <span className="font-semibold text-zinc-800">Valor total</span>
          <span className="text-lg font-bold tabular text-zinc-950">
            {formatCurrency(totalValue)}
          </span>
        </div>
      </form>
    </Sheet>
  ), document.body)
}
