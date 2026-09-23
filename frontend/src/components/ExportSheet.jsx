import { useEffect, useState } from 'react'
import { Download } from 'lucide-react'
import { exportsApi } from '../lib/dataApi'
import { toast } from '../lib/toast'
import { AlertMessage, Button, Field, SegmentedControl, Sheet, Skeleton } from './ui'

const FORMAT_ITEMS = [
  { value: 'xlsx', label: 'Excel (.xlsx)' },
  { value: 'csv', label: 'CSV' },
]

const STORAGE_PREFIX = 'financeMVP:export:'

// O catalogo de colunas nao muda durante a sessao: uma busca so, dividida
// entre as telas.
let catalogPromise = null
function loadCatalog() {
  if (!catalogPromise) {
    catalogPromise = exportsApi.columns().catch((error) => {
      catalogPromise = null
      throw error
    })
  }
  return catalogPromise
}

function readSaved(name) {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_PREFIX + name) || 'null')
  } catch {
    return null
  }
}

function writeSaved(name, value) {
  try {
    localStorage.setItem(STORAGE_PREFIX + name, JSON.stringify(value))
  } catch {
    // Sem localStorage: a escolha so nao fica lembrada.
  }
}

// Exportar: formato e colunas, lembrados por tela neste navegador.
// `exportName` e a chave do catalogo (transactions, portfolio, movements,
// proceeds); `onExport({ format, columns })` baixa o arquivo — a tela junta
// os filtros dela.
export default function ExportSheet({ open, onClose, exportName, title, description, onExport }) {
  const [columns, setColumns] = useState([])
  const [selected, setSelected] = useState([])
  const [format, setFormat] = useState('xlsx')
  const [loading, setLoading] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return undefined
    let cancelled = false
    setError('')
    setLoading(true)
    loadCatalog()
      .then((catalog) => {
        if (cancelled) return
        const available = catalog?.[exportName] || []
        const saved = readSaved(exportName)
        const known = new Set(available.map((column) => column.key))
        const savedColumns = (saved?.columns || []).filter((key) => known.has(key))
        setColumns(available)
        setSelected(savedColumns.length ? savedColumns : available.map((column) => column.key))
        setFormat(saved?.format === 'csv' ? 'csv' : 'xlsx')
      })
      .catch((loadError) => {
        if (!cancelled) setError(loadError.message || 'Não foi possível carregar as colunas.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, exportName])

  const toggle = (key) => {
    setSelected((current) => (current.includes(key) ? current.filter((item) => item !== key) : [...current, key]))
  }

  const allSelected = columns.length > 0 && selected.length === columns.length

  const handleDownload = async () => {
    // A ordem do arquivo e a do catalogo, nao a ordem em que os itens foram marcados.
    const ordered = columns.map((column) => column.key).filter((key) => selected.includes(key))
    setDownloading(true)
    setError('')
    try {
      const filename = await onExport({
        format,
        columns: allSelected ? undefined : ordered.join(','),
      })
      writeSaved(exportName, { format, columns: ordered })
      onClose()
      toast(filename ? `${filename} baixado.` : 'Arquivo baixado.')
    } catch (downloadError) {
      setError(downloadError.message || 'Não foi possível exportar.')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={title}
      description={description}
      footer={(
        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <Button type="button" variant="secondary" size="lg" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            type="button"
            size="lg"
            icon={Download}
            loading={downloading}
            disabled={loading || selected.length === 0}
            onClick={handleDownload}
          >
            Baixar
          </Button>
        </div>
      )}
    >
      <div className="space-y-5">
        <AlertMessage message={error} onDismiss={() => setError('')} />
        <Field label="Formato" hint={format === 'xlsx' ? 'Abre direto no Excel, com números e datas prontos para somar e filtrar.' : 'Separado por ponto e vírgula, vírgula decimal: abre no Excel em português.'}>
          <SegmentedControl items={FORMAT_ITEMS} value={format} onChange={setFormat} />
        </Field>
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm font-medium text-zinc-700">Colunas</span>
            {columns.length ? (
              <button
                type="button"
                className="text-sm font-semibold text-emerald-700 hover:underline"
                onClick={() => setSelected(allSelected ? [] : columns.map((column) => column.key))}
              >
                {allSelected ? 'Desmarcar todas' : 'Marcar todas'}
              </button>
            ) : null}
          </div>
          {loading ? (
            <Skeleton className="h-40 w-full" />
          ) : (
            <ul className="grid grid-cols-1 gap-1 sm:grid-cols-2">
              {columns.map((column) => (
                <li key={column.key}>
                  <label className="flex min-h-10 cursor-pointer items-center gap-3 rounded-xl px-2 text-sm text-zinc-800 hover:bg-zinc-50">
                    <input
                      type="checkbox"
                      className="h-4 w-4 rounded border-zinc-300 text-emerald-600"
                      checked={selected.includes(column.key)}
                      onChange={() => toggle(column.key)}
                    />
                    {column.label}
                  </label>
                </li>
              ))}
            </ul>
          )}
          {!loading && columns.length > 0 && selected.length === 0 ? (
            <p className="text-xs text-rose-600">Escolha ao menos uma coluna.</p>
          ) : null}
        </div>
      </div>
    </Sheet>
  )
}
