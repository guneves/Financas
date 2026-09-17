import { useEffect, useMemo, useRef, useState } from 'react'
import { Loader2, Search } from 'lucide-react'
import { marketApi } from '../lib/dataApi'
import { cx } from './ui'

const KIND_TONES = {
  ACAO: 'bg-emerald-50 text-emerald-700',
  ETF: 'bg-sky-50 text-sky-700',
  FII: 'bg-amber-50 text-amber-700',
  BDR: 'bg-violet-50 text-violet-700',
  CARTEIRA: 'bg-zinc-100 text-zinc-600',
}

const normalize = (value) => String(value || '').trim().toUpperCase()

/**
 * Campo de ativo com busca no catalogo da B3.
 *
 * O backend e quem decide o que e um papel valido (`/api/market/tickers`); aqui
 * so mostramos o que ele devolve e obrigamos a escolha de uma das opcoes. Os
 * ativos que o usuario ja tem na carteira entram como opcao extra para que uma
 * posicao antiga, fora do catalogo, continue lancavel.
 */
export default function TickerAutocomplete({
  value,
  onChange,
  assetClass,
  walletAssets = [],
  placeholder = 'Digite o ticker (ex: PETR4)',
  required = false,
  disabled = false,
  id = 'ticker-autocomplete',
}) {
  const [query, setQuery] = useState(value || '')
  const [options, setOptions] = useState([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [highlight, setHighlight] = useState(0)
  const containerRef = useRef(null)
  const skipNextSearch = useRef(false)

  useEffect(() => {
    setQuery(value || '')
  }, [value])

  const walletOptions = useMemo(() => {
    return walletAssets
      .filter((asset) => !assetClass || asset.class === assetClass)
      .map((asset) => ({
        ticker: normalize(asset.ticker || asset.name),
        name: asset.name || asset.ticker,
        kind: 'CARTEIRA',
        kind_label: 'Na carteira',
      }))
      .filter((asset) => asset.ticker)
  }, [walletAssets, assetClass])

  useEffect(() => {
    if (skipNextSearch.current) {
      skipNextSearch.current = false
      return
    }
    if (!open) return

    let active = true
    setLoading(true)
    const timer = setTimeout(async () => {
      try {
        const results = await marketApi.searchTickers({
          q: query,
          asset_class: assetClass,
          limit: 20,
        })
        if (!active) return
        const catalogTickers = new Set(results.map((item) => item.ticker))
        const needle = normalize(query)
        const extras = walletOptions.filter((asset) => (
          !catalogTickers.has(asset.ticker) && (!needle || asset.ticker.includes(needle))
        ))
        setOptions([...results, ...extras])
        setHighlight(0)
      } catch {
        if (active) setOptions([])
      } finally {
        if (active) setLoading(false)
      }
    }, 180)

    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [query, assetClass, open, walletOptions])

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const selectOption = (option) => {
    skipNextSearch.current = true
    setQuery(option.ticker)
    setOpen(false)
    onChange(option.ticker, option)
  }

  const handleChange = (event) => {
    const nextValue = normalize(event.target.value)
    setQuery(nextValue)
    setOpen(true)
    // Enquanto nao houver escolha na lista, o formulario nao tem ativo valido.
    onChange(nextValue, null)
  }

  const handleKeyDown = (event) => {
    if (!open && ['ArrowDown', 'ArrowUp'].includes(event.key)) {
      setOpen(true)
      return
    }
    if (!open) return

    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setHighlight((current) => Math.min(current + 1, Math.max(options.length - 1, 0)))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlight((current) => Math.max(current - 1, 0))
    } else if (event.key === 'Enter') {
      if (options[highlight]) {
        event.preventDefault()
        selectOption(options[highlight])
      }
    } else if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
        <input
          id={id}
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-autocomplete="list"
          autoComplete="off"
          value={query}
          onChange={handleChange}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          required={required}
          disabled={disabled}
          className="app-input h-12 pl-10"
        />
        {loading ? (
          <Loader2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-zinc-400" />
        ) : null}
      </div>

      {open ? (
        <ul
          role="listbox"
          className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-lg border border-zinc-200 bg-white py-1 shadow-xl"
        >
          {options.length === 0 && !loading ? (
            <li className="px-3 py-3 text-sm text-zinc-500">
              Nenhum ativo encontrado para "{query}".
            </li>
          ) : null}

          {options.map((option, index) => (
            <li key={`${option.kind}-${option.ticker}`} role="option" aria-selected={index === highlight}>
              <button
                type="button"
                onMouseEnter={() => setHighlight(index)}
                onClick={() => selectOption(option)}
                className={cx(
                  'flex w-full items-center justify-between gap-3 px-3 py-2 text-left transition',
                  index === highlight ? 'bg-zinc-100' : 'hover:bg-zinc-50'
                )}
              >
                <span className="min-w-0">
                  <span className="block text-sm font-semibold text-zinc-800">{option.ticker}</span>
                  <span className="block truncate text-xs text-zinc-500">{option.name}</span>
                </span>
                <span
                  className={cx(
                    'shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold',
                    KIND_TONES[option.kind] || KIND_TONES.CARTEIRA
                  )}
                >
                  {option.kind_label}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
