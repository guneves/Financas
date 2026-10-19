import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown, Search, X } from 'lucide-react'
import { filterAssetOptions } from '../lib/assetSearch'
import { cx } from './ui'

/**
 * Escolha de um ativo da carteira digitando: ticker ou nome, e a lista abaixo
 * sugere enquanto se escreve (lib/assetSearch.js). Para os ativos que o dono
 * ja tem — a venda, o provento; a compra de papel novo e o TickerAutocomplete,
 * que busca no catalogo da B3.
 *
 * `options`: [{ value, label (ticker), name, meta (linha de baixo), aside (a
 * direita) }]. `value` e o `value` escolhido; `onChange(value, option)`.
 * Texto digitado sem escolher da lista nao e um ativo: o campo fica vazio.
 * A lista abre no fluxo (empurra os campos de baixo), nao por cima: dentro de
 * um Sheet no celular, uma lista flutuante era cortada pela rolagem dele.
 */
export default function AssetPicker({
  value,
  onChange,
  options = [],
  placeholder = 'Digite o ticker ou o nome',
  emptyMessage = 'Nenhum ativo encontrado.',
  required = false,
  disabled = false,
  id = 'asset-picker',
}) {
  const selected = useMemo(
    () => options.find((option) => String(option.value) === String(value)) || null,
    [options, value],
  )
  const [query, setQuery] = useState(selected?.label || '')
  const [open, setOpen] = useState(false)
  const [highlight, setHighlight] = useState(0)
  const containerRef = useRef(null)
  const inputRef = useRef(null)

  // Fora da digitacao, o campo mostra o ativo escolhido (ou nada).
  useEffect(() => {
    if (!open) setQuery(selected?.label || '')
  }, [selected, open])

  // Com um ativo escolhido, abrir a lista mostra todos; digitar filtra.
  const typed = !selected || query !== selected.label
  const filtered = useMemo(
    () => filterAssetOptions(options, typed ? query : ''),
    [options, query, typed],
  )

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (containerRef.current && !containerRef.current.contains(event.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const selectOption = (option) => {
    setQuery(option.label)
    setOpen(false)
    onChange(option.value, option)
  }

  const clear = () => {
    setQuery('')
    onChange('', null)
    setOpen(true)
    inputRef.current?.focus()
  }

  const handleChange = (event) => {
    setQuery(event.target.value)
    setOpen(true)
    setHighlight(0)
    if (selected) onChange('', null)
  }

  const handleKeyDown = (event) => {
    if (!open && ['ArrowDown', 'ArrowUp'].includes(event.key)) {
      setOpen(true)
      return
    }
    if (!open) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setHighlight((current) => Math.min(current + 1, Math.max(filtered.length - 1, 0)))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlight((current) => Math.max(current - 1, 0))
    } else if (event.key === 'Enter') {
      if (filtered[highlight]) {
        event.preventDefault()
        selectOption(filtered[highlight])
      }
    } else if (event.key === 'Escape') {
      // So a lista fecha; o sheet em volta fica (lib/layers.js).
      event.preventDefault()
      setOpen(false)
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
        <input
          ref={inputRef}
          id={id}
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-autocomplete="list"
          autoComplete="off"
          value={query}
          onChange={handleChange}
          onFocus={(event) => {
            setOpen(true)
            event.target.select()
          }}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          required={required}
          disabled={disabled}
          className="app-input h-11 pl-10 pr-10"
        />
        {query && !disabled ? (
          <button
            type="button"
            onClick={(event) => {
              event.preventDefault()
              clear()
            }}
            aria-label="Limpar ativo"
            className="absolute right-2 top-1/2 flex size-8 -translate-y-1/2 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-100"
          >
            <X className="h-4 w-4" />
          </button>
        ) : (
          <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
        )}
      </div>

      {open && !disabled ? (
        <ul
          role="listbox"
          className="mt-1 max-h-64 w-full overflow-y-auto rounded-lg border border-zinc-200 bg-white py-1 shadow-sm"
        >
          {filtered.length === 0 ? (
            <li className="px-3 py-3 text-sm text-zinc-500">
              {query && typed ? `Nenhum ativo encontrado para "${query}".` : emptyMessage}
            </li>
          ) : null}
          {filtered.map((option, index) => (
            <li key={option.value} role="option" aria-selected={String(option.value) === String(value)}>
              <button
                type="button"
                onMouseEnter={() => setHighlight(index)}
                // Sem o preventDefault, o <label> do Field em volta devolve o
                // clique ao input, que ganha foco e reabre a lista.
                onClick={(event) => {
                  event.preventDefault()
                  selectOption(option)
                }}
                className={cx(
                  'flex min-h-11 w-full items-center justify-between gap-3 px-3 py-2 text-left transition',
                  index === highlight ? 'bg-zinc-100' : 'hover:bg-zinc-50',
                )}
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold text-zinc-800">{option.label}</span>
                  {option.meta ? <span className="block truncate text-xs text-zinc-500">{option.meta}</span> : null}
                </span>
                {option.aside ? (
                  <span className="shrink-0 text-xs font-medium tabular text-zinc-600">{option.aside}</span>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
