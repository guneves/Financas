import { useEffect, useMemo, useState } from 'react'
import { CalendarDays, Plus, X } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { investmentsApi } from '../lib/dataApi'
import { Button, cx } from './ui'

const ASSET_TYPES = [
  { value: 'STOCKS', label: 'Ações' },
  { value: 'REIT', label: 'Fundos Imobiliários' },
  { value: 'CATTLE', label: 'Gado' },
  { value: 'FIXED_INCOME', label: 'Renda Fixa' },
  { value: 'OTHER', label: 'Outros' },
]

const initialForm = () => ({
  asset_class: 'STOCKS',
  ticker_or_name: '',
  asset_id: '',
  transaction_date: getLocalDateString(),
  quantity: '1',
  price: '',
  other_costs: '',
  cdi_percentage: '',
  is_tax_free: false,
})

function getLocalDateString(date = new Date()) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function parseAmount(value) {
  const rawValue = String(value || '').trim()
  const normalized = rawValue.includes(',')
    ? rawValue.replace(/\./g, '').replace(',', '.')
    : rawValue
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : 0
}

function formatCurrency(value) {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(Number(value || 0))
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
        asset_class: nextMode === 'SELL' ? selectedAsset?.class || 'STOCKS' : 'STOCKS',
        ticker_or_name: nextMode === 'SELL' && selectedAsset ? selectedAsset.ticker || selectedAsset.name || '' : '',
        price: nextMode === 'SELL' && selectedAsset?.current_price ? String(selectedAsset.current_price) : '',
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

  const updateForm = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }))
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
      asset_class: asset?.class || current.asset_class,
      ticker_or_name: asset?.ticker || asset?.name || '',
      price: asset?.current_price ? String(asset.current_price) : current.price,
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
    } catch (submitError) {
      setError(submitError.message || 'Não foi possível salvar o lançamento.')
    } finally {
      setSaving(false)
    }
  }

  const createBuyMovement = async () => {
    const tickerName = normalizeAssetName(form.ticker_or_name)
    if (!tickerName) throw new Error('Informe o ativo do lançamento.')
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

    const metadata = form.asset_class === 'FIXED_INCOME'
      ? {
          cdi_percentage: form.cdi_percentage ? parseAmount(form.cdi_percentage) / 100 : undefined,
          purchase_date: form.transaction_date,
          is_tax_free: form.is_tax_free,
          other_costs: otherCosts,
        }
      : {
          purchase_date: form.transaction_date,
          other_costs: otherCosts,
        }

    const insertedData = await investmentsApi.create([
      {
        asset_class: form.asset_class,
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
        },
      },
    ])
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/45 p-4">
      <div className="w-full max-w-3xl overflow-hidden rounded-lg bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-zinc-200 px-6 py-5">
          <h2 className="text-2xl font-semibold text-zinc-900">Adicionar Lançamento</h2>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-900"
            aria-label="Fechar"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6 px-6 py-7">
          <div className="grid grid-cols-2 rounded-lg bg-zinc-100 p-1">
            <button
              type="button"
              onClick={() => handleModeChange('BUY')}
              className={cx(
                'flex h-12 items-center justify-center gap-2 rounded-lg text-sm font-semibold transition',
                mode === 'BUY' ? 'bg-white text-zinc-800 shadow-sm' : 'text-zinc-400'
              )}
            >
              <span className="text-emerald-500">◌</span>
              Compra
            </button>
            <button
              type="button"
              onClick={() => handleModeChange('SELL')}
              className={cx(
                'flex h-12 items-center justify-center gap-2 rounded-lg text-sm font-semibold transition',
                mode === 'SELL' ? 'bg-white text-zinc-800 shadow-sm' : 'text-zinc-400'
              )}
            >
              <span className="text-rose-400">◌</span>
              Venda
            </button>
          </div>

          {error ? (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">
              {error}
            </div>
          ) : null}

          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            <ModalField label="Tipo de ativo">
              <select
                value={form.asset_class}
                onChange={(event) => updateForm('asset_class', event.target.value)}
                disabled={mode === 'SELL'}
                className="app-select h-12"
              >
                {ASSET_TYPES.map((type) => (
                  <option key={type.value} value={type.value}>{type.label}</option>
                ))}
              </select>
            </ModalField>

            <ModalField label="Ativo">
              {mode === 'BUY' ? (
                <>
                  <input
                    list="investment-assets"
                    value={form.ticker_or_name}
                    onChange={(event) => updateForm('ticker_or_name', event.target.value)}
                    placeholder="Selecionar ou digitar"
                    className="app-input h-12"
                    required
                  />
                  <datalist id="investment-assets">
                    {assets.map((asset) => (
                      <option key={asset.id} value={asset.ticker || asset.name} />
                    ))}
                  </datalist>
                </>
              ) : (
                <select
                  value={form.asset_id}
                  onChange={(event) => handleSaleAssetChange(event.target.value)}
                  className="app-select h-12"
                  required
                >
                  <option value="">Selecionar</option>
                  {saleAssets.map((asset) => (
                    <option key={asset.id} value={asset.id}>
                      {asset.name} - {formatCurrency(asset.current_value)}
                    </option>
                  ))}
                </select>
              )}
            </ModalField>

            <ModalField label="Data da transação">
              <div className="relative">
                <CalendarDays className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
                <input
                  type="date"
                  value={form.transaction_date}
                  onChange={(event) => updateForm('transaction_date', event.target.value)}
                  className="app-input h-12 pl-10"
                  required
                />
              </div>
            </ModalField>

            <ModalField label="Quantidade">
              <input
                type="number"
                min="0"
                step="0.0001"
                value={form.asset_class === 'FIXED_INCOME' && mode === 'BUY' ? '1' : form.quantity}
                onChange={(event) => updateForm('quantity', event.target.value)}
                disabled={form.asset_class === 'FIXED_INCOME' && mode === 'BUY'}
                className="app-input h-12"
                required
              />
            </ModalField>

            <ModalField label={form.asset_class === 'FIXED_INCOME' && mode === 'BUY' ? 'Valor aplicado em R$' : 'Preço em R$'}>
              <input
                type="number"
                min="0"
                step="0.01"
                value={form.price}
                onChange={(event) => updateForm('price', event.target.value)}
                placeholder="0,00"
                className="app-input h-12"
                required
              />
            </ModalField>

            <ModalField
              label="Outros custos"
              action={<span className="text-xs font-medium text-zinc-500">(Opcional)</span>}
            >
              <input
                type="number"
                min="0"
                step="0.01"
                value={form.other_costs}
                onChange={(event) => updateForm('other_costs', event.target.value)}
                placeholder="0,00"
                className="app-input h-12"
              />
            </ModalField>

            {mode === 'BUY' && form.asset_class === 'FIXED_INCOME' ? (
              <>
                <ModalField label="% do CDI">
                  <input
                    type="number"
                    min="0"
                    step="0.1"
                    value={form.cdi_percentage}
                    onChange={(event) => updateForm('cdi_percentage', event.target.value)}
                    placeholder="Ex: 110"
                    className="app-input h-12"
                    required
                  />
                </ModalField>

                <label className="flex h-12 items-center gap-3 self-end rounded-lg border border-zinc-200 px-4 text-sm font-medium text-zinc-700">
                  <input
                    type="checkbox"
                    checked={form.is_tax_free}
                    onChange={(event) => updateForm('is_tax_free', event.target.checked)}
                    className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500"
                  />
                  Isento de IR (LCI/LCA)
                </label>
              </>
            ) : null}
          </div>

          {mode === 'SELL' && saleAssets.length === 0 ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              Não há ativos de renda variável disponíveis para venda. Resgates de renda fixa continuam na linha do ativo.
            </div>
          ) : null}

          <div className="flex items-center justify-between rounded-lg bg-zinc-200 px-4 py-3">
            <span className="font-semibold text-zinc-800">Valor total</span>
            <span className="text-lg font-bold text-zinc-900">{formatCurrency(totalValue)}</span>
          </div>

          <div className="flex flex-col-reverse gap-3 pt-1 sm:flex-row sm:items-center sm:justify-between">
            <Button type="button" variant="secondary" onClick={onClose}>
              Cancelar
            </Button>
            <Button type="submit" variant="dark" icon={Plus} loading={saving}>
              {mode === 'BUY' ? 'Adicionar Lançamento' : 'Registrar Venda'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}

function ModalField({ label, action, children }) {
  return (
    <label className="block space-y-2">
      <span className="flex items-center justify-between text-sm font-medium text-zinc-500">
        <span>{label}</span>
        {action}
      </span>
      {children}
    </label>
  )
}
