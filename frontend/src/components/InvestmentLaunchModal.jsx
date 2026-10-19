import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { ArrowDownRight, ArrowUpRight, CalendarDays } from 'lucide-react'
import { investmentsApi, marketApi, refreshQuotes } from '../lib/dataApi'
import { AlertMessage, Button, Field, SegmentedControl, Sheet } from './ui'
import { formatCurrency, formatQuantity, getLocalDateString } from '../lib/format'
import { usePrivateFormatter } from '../lib/privacy'
import { toast } from '../lib/toast'
import TickerAutocomplete from './TickerAutocomplete'
import AssetPicker from './AssetPicker'
import FixedIncomeFields from './FixedIncomeFields'
import { parseTreasuryUnits } from '../lib/treasury'
import CashLinkField, { cashLinkMetadata, emptyCashLink } from './CashLinkField'
import { SaleExemptionNotice } from './ExemptionMeter'
import {
  FIXED_INCOME_TYPES,
  TREASURY_TITLES,
  TREASURY_TYPE,
  emptyFixedIncomeForm,
  fixedIncomeMetadataFromForm,
  rateFieldsForMode,
  rateModeOf,
  treasuryRateMode,
} from '../lib/fixedIncome'

// Classes com cotacao na B3: o ativo tem de vir do catalogo, nao de texto livre.
const CATALOG_ASSET_TYPES = ['STOCKS', 'ETF', 'REIT']

const ASSET_TYPES = [
  { value: 'STOCKS', label: 'Ações' },
  { value: 'ETF', label: 'ETFs' },
  { value: 'REIT', label: 'Fundos Imobiliários' },
  { value: 'FIXED_INCOME', label: 'Renda Fixa' },
  { value: 'TESOURO', label: 'Tesouro Direto' },
  { value: 'BITCOIN', label: 'Bitcoin' },
  { value: 'OTHER', label: 'Outros' },
]

// Tipos so da tela (services/asset_categories.py): ETF e a classe "Acoes" com
// um ticker que a B3 diz ETF; Tesouro Direto e "Renda Fixa" com o tipo de
// titulo TESOURO; Bitcoin e "Outros" com o ticker BTC, cotado em reais
// (BTC-BRL) e com o IR de criptoativo.
const BITCOIN = 'BITCOIN'
const BITCOIN_TICKER = 'BTC'
const ETF = 'ETF'
const TREASURY = 'TESOURO'

const MOVEMENT_CLASS = { [BITCOIN]: 'OTHER', [ETF]: 'STOCKS', [TREASURY]: 'FIXED_INCOME' }

function movementAssetClass(assetType) {
  return MOVEMENT_CLASS[assetType] || assetType
}

function assetTypeOf(asset) {
  if (!asset) return 'STOCKS'
  if (asset.market_kind === 'CRIPTO') return BITCOIN
  if (asset.category === 'ETF') return ETF
  if (asset.category === 'TESOURO') return TREASURY
  return asset.class
}

// A compra de renda fixa nao oferece o Tesouro: ele tem o tipo de ativo dele.
const PRIVATE_FIXED_INCOME_TYPES = FIXED_INCOME_TYPES.filter((type) => type.value !== TREASURY_TYPE)
const NO_TYPES = []

const fixedIncomeFormFor = (assetType) => (
  assetType === TREASURY ? { ...emptyFixedIncomeForm(), fixed_income_type: TREASURY_TYPE } : emptyFixedIncomeForm()
)

const FORM_ID = 'investment-launch-form'

const MODE_ITEMS = [
  { value: 'BUY', label: 'Compra', icon: ArrowUpRight },
  { value: 'SELL', label: 'Venda', icon: ArrowDownRight },
]

// "0,85" -> {treasury_units: 0.85}; vazio, nada. Um numero invalido e erro.
function treasuryUnitsMetadata(form) {
  if (form.asset_class !== TREASURY) return {}
  const units = parseTreasuryUnits(form.treasury_units)
  if (units === null) return {}
  if (Number.isNaN(units)) throw new Error('Informe uma quantidade de títulos válida.')
  return { treasury_units: units }
}

const initialForm = () => ({
  asset_class: 'STOCKS',
  ticker_or_name: '',
  asset_id: '',
  ticker_confirmed: false,
  transaction_date: getLocalDateString(),
  quantity: '1',
  price: '',
  other_costs: '',
  // Tesouro: quantos titulos o extrato da corretora mostra (opcional; sem ele,
  // o servidor divide o valor pelo PU do Tesouro na data).
  treasury_units: '',
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

  const isFixedIncome = movementAssetClass(form.asset_class) === 'FIXED_INCOME'
  const quantity = mode === 'BUY' && isFixedIncome ? 1 : parseAmount(form.quantity)
  const unitPrice = parseAmount(form.price)
  const otherCosts = parseAmount(form.other_costs)
  const totalValue = mode === 'SELL'
    ? Math.max((quantity * unitPrice) - otherCosts, 0)
    : isFixedIncome
      ? unitPrice + otherCosts
      : (quantity * unitPrice) + otherCosts

  const usesCatalog = mode === 'BUY' && CATALOG_ASSET_TYPES.includes(form.asset_class)

  // Venda: busca entre as posicoes, pelo ticker ou pelo nome.
  const saleOptions = useMemo(() => saleAssets.map((asset) => ({
    value: String(asset.id),
    label: asset.ticker || asset.name,
    name: asset.name,
    meta: [
      asset.category_label,
      `${formatQuantity(asset.quantity)} ${Number(asset.quantity) === 1 ? 'cota' : 'cotas'}`,
      asset.name && asset.name !== asset.ticker ? asset.name : null,
    ].filter(Boolean).join(' · '),
    aside: privateMoney(asset.current_value),
  })), [saleAssets, privateMoney])

  // Nome sugerido na renda fixa: os titulos da carteira daquele tipo (e, no
  // Tesouro, os titulos que o Tesouro vende).
  const fixedIncomeNames = useMemo(() => {
    const own = assets
      .filter((asset) => asset.class === 'FIXED_INCOME' && (asset.category === 'TESOURO') === (form.asset_class === TREASURY))
      .map((asset) => asset.ticker || asset.name)
    const names = form.asset_class === TREASURY ? [...own, ...TREASURY_TITLES] : own
    return [...new Set(names)]
  }, [assets, form.asset_class])

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
      fixed_income: fixedIncomeFormFor(nextClass),
      treasury_units: '',
    }))
  }

  // No Tesouro, o nome do titulo ja diz a rentabilidade (Selic, Prefixado, IPCA+).
  const handleFixedIncomeNameChange = (name) => {
    setForm((current) => {
      const mode = current.asset_class === TREASURY ? treasuryRateMode(name) : null
      const fixedIncome = mode && mode !== rateModeOf(current.fixed_income)
        ? { ...current.fixed_income, ...rateFieldsForMode(mode), rate: '' }
        : current.fixed_income
      return { ...current, ticker_or_name: name, fixed_income: fixedIncome }
    })
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
      // Compra: a cotacao do ativo depois de fechar. A venda nao busca cotacao.
      let createdId = null
      if (mode === 'BUY') {
        createdId = await createBuyMovement()
      } else {
        await createSellMovement()
      }

      // A gravacao ja invalidou o cache (lib/api.js): fecha agora, sem esperar
      // a nova busca de cada tela nem a cotacao (yfinance, BCB, Tesouro), que
      // vai por tras e so refaz as telas se mudou alguma (refreshQuotes).
      onSaved?.()
      onClose()
      if (createdId) {
        refreshQuotes({ investment_id: createdId }).catch((priceError) => {
          console.warn('Não foi possível atualizar a cotação após o lançamento:', priceError)
        })
      }
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
    if (!isFixedIncome && quantity <= 0) throw new Error('Informe uma quantidade válida.')

    const finalQuantity = isFixedIncome ? 1 : quantity
    const grossValue = isFixedIncome ? unitPrice : unitPrice * finalQuantity
    const averagePrice = isFixedIncome
      ? grossValue + otherCosts
      : (grossValue + otherCosts) / finalQuantity

    const existingAsset = assets.find((asset) => {
      const currentTicker = normalizeAssetName(asset.ticker || asset.name)
      return currentTicker === tickerName
    })

    const baseMetadata = isFixedIncome
      ? {
          ...fixedIncomeMetadataFromForm(
            form.asset_class === TREASURY ? { ...form.fixed_income, fixed_income_type: TREASURY_TYPE } : form.fixed_income,
          ),
          purchase_date: form.transaction_date,
          other_costs: otherCosts,
          ...treasuryUnitsMetadata(form),
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

    return insertedData?.[0]?.id
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
                assetClass={movementAssetClass(form.asset_class)}
                kind={form.asset_class === ETF ? ETF : undefined}
                excludeKind={form.asset_class === 'STOCKS' ? ETF : undefined}
                walletAssets={assets}
                placeholder={form.asset_class === ETF ? 'Digite o ticker (ex: BOVA11)' : undefined}
                required
              />
            ) : mode === 'BUY' && isFixedIncome ? (
              <>
                <input
                  list="investment-fixed-income-names"
                  value={form.ticker_or_name}
                  onChange={(event) => handleFixedIncomeNameChange(event.target.value)}
                  placeholder={form.asset_class === TREASURY ? 'Ex: Tesouro IPCA+ 2035' : 'Ex: CDB Banco X 2027'}
                  className="app-input h-11"
                  required
                />
                <datalist id="investment-fixed-income-names">
                  {fixedIncomeNames.map((name) => (
                    <option key={name} value={name} />
                  ))}
                </datalist>
              </>
            ) : mode === 'BUY' ? (
              <>
                <input
                  list="investment-assets"
                  value={form.ticker_or_name}
                  onChange={(event) => updateForm('ticker_or_name', event.target.value)}
                  placeholder="Selecionar ou digitar"
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
              <AssetPicker
                id="sale-asset"
                value={form.asset_id}
                onChange={handleSaleAssetChange}
                options={saleOptions}
                placeholder="Digite o ticker ou o nome"
                emptyMessage="Nenhuma posição para vender."
                required
              />
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

          {isFixedIncome && mode === 'BUY' ? null : (
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

          <Field label={isFixedIncome && mode === 'BUY' ? 'Valor aplicado em R$' : 'Preço em R$'}>
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

          {mode === 'BUY' && form.asset_class === TREASURY ? (
            <Field label="Quantidade de títulos (opcional)" hint="Como no extrato da corretora. Sem ela, o app usa o preço do Tesouro na data da compra.">
              <input
                type="text"
                inputMode="decimal"
                value={form.treasury_units}
                onChange={(event) => updateForm('treasury_units', event.target.value)}
                placeholder="Ex: 0,85"
                className="app-input h-11"
              />
            </Field>
          ) : null}

          {mode === 'BUY' && isFixedIncome ? (
            <FixedIncomeFields
              value={form.fixed_income}
              onChange={(next) => updateForm('fixed_income', next)}
              types={form.asset_class === TREASURY ? NO_TYPES : PRIVATE_FIXED_INCOME_TYPES}
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
