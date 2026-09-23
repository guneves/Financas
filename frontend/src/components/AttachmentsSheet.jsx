import { useEffect, useRef, useState } from 'react'
import { Download, ExternalLink, FileText, Image as ImageIcon, Paperclip, Trash2 } from 'lucide-react'
import { attachmentsApi } from '../lib/dataApi'
import { saveBlob } from '../lib/api'
import { formatDateBR, formatSignedCurrency, getLocalDateString } from '../lib/format'
import { AlertMessage, Button, EmptyState, IconButton, Sheet } from './ui'
import { confirmAction } from '../lib/confirm'

// Espelha ATTACHMENT_MAX_BYTES do backend (10 MB por padrao). O backend e quem
// decide; o aviso aqui so evita subir um video de 200 MB para ouvir "nao".
const MAX_BYTES = 10 * 1024 * 1024

const TYPE_LABELS = {
  'application/pdf': 'PDF',
  'image/jpeg': 'JPG',
  'image/png': 'PNG',
  'image/gif': 'GIF',
  'image/webp': 'WEBP',
  'image/heic': 'HEIC',
}

// HEIC so abre no Safari; nos outros navegadores "Abrir" vira baixar.
const OPENABLE = new Set(['application/pdf', 'image/jpeg', 'image/png', 'image/gif', 'image/webp'])

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} kB`
  return `${(bytes / (1024 * 1024)).toFixed(1).replace('.', ',')} MB`
}

function signOf(transaction) {
  if (transaction.type === 'TRANSFER') return 0
  return transaction.type === 'INCOME' ? 1 : -1
}

// Comprovantes de um lancamento: lista, anexar (varios de uma vez), abrir,
// baixar e excluir. `onChanged` roda ao fechar se algo mudou, para o extrato
// recontar o clipe da linha.
export default function AttachmentsSheet({ transaction, onClose, onChanged }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [busyId, setBusyId] = useState('')
  const [error, setError] = useState('')
  const changedRef = useRef(false)
  const inputRef = useRef(null)
  const transactionId = transaction?.id

  useEffect(() => {
    if (!transactionId) return undefined
    let cancelled = false
    changedRef.current = false
    setItems([])
    setError('')
    setLoading(true)
    attachmentsApi.list(transactionId)
      .then((list) => { if (!cancelled) setItems(list) })
      .catch((err) => { if (!cancelled) setError(err.message || 'Não foi possível carregar os comprovantes.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [transactionId])

  const close = () => {
    if (changedRef.current) onChanged?.()
    changedRef.current = false
    onClose()
  }

  const handleFiles = async (event) => {
    const files = Array.from(event.target.files || [])
    event.target.value = ''
    if (!files.length) return

    const tooBig = files.filter((file) => file.size > MAX_BYTES)
    const toSend = files.filter((file) => file.size <= MAX_BYTES)
    const problems = tooBig.map((file) => `${file.name}: passa de 10 MB.`)

    setError('')
    setUploading(true)
    for (const file of toSend) {
      try {
        const created = await attachmentsApi.upload(transactionId, file)
        setItems((current) => [...current, created])
        changedRef.current = true
      } catch (err) {
        problems.push(`${file.name}: ${err.message || 'não foi possível anexar.'}`)
      }
    }
    setUploading(false)
    if (problems.length) setError(problems.join(' '))
  }

  const handleOpen = async (item) => {
    if (!OPENABLE.has(item.content_type)) {
      handleDownload(item)
      return
    }
    // A aba abre no clique (senao o bloqueador de pop-up a barra) e recebe o
    // arquivo quando ele chega; o token vai no cabecalho, entao nao ha link direto.
    const tab = window.open('', '_blank')
    setBusyId(item.id)
    setError('')
    try {
      const blob = await attachmentsApi.file(transactionId, item.id)
      const url = URL.createObjectURL(blob)
      if (tab) {
        tab.location.href = url
      } else {
        saveBlob(blob, item.original_name)
      }
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (err) {
      tab?.close()
      setError(err.message || 'Não foi possível abrir o comprovante.')
    } finally {
      setBusyId('')
    }
  }

  const handleDownload = async (item) => {
    setBusyId(item.id)
    setError('')
    try {
      const blob = await attachmentsApi.file(transactionId, item.id)
      saveBlob(blob, item.original_name)
    } catch (err) {
      setError(err.message || 'Não foi possível baixar o comprovante.')
    } finally {
      setBusyId('')
    }
  }

  const handleDelete = async (item) => {
    if (!(await confirmAction({ title: 'Excluir o comprovante?', message: `“${item.original_name}” será apagado.`, confirmLabel: 'Excluir' }))) return
    setBusyId(item.id)
    setError('')
    try {
      await attachmentsApi.remove(transactionId, item.id)
      setItems((current) => current.filter((entry) => entry.id !== item.id))
      changedRef.current = true
    } catch (err) {
      setError(err.message || 'Não foi possível excluir o comprovante.')
    } finally {
      setBusyId('')
    }
  }

  const description = transaction
    ? [
        transaction.description || transaction.category,
        formatDateBR(transaction.date),
        formatSignedCurrency(transaction.amount, signOf(transaction)),
      ].join(' · ')
    : ''

  const uploadButton = (
    <Button type="button" icon={Paperclip} loading={uploading} className="whitespace-nowrap" onClick={() => inputRef.current?.click()}>
      {uploading ? 'Anexando...' : 'Anexar arquivo'}
    </Button>
  )

  return (
    <Sheet
      open={Boolean(transaction)}
      onClose={close}
      title="Comprovantes"
      description={description}
      footer={items.length ? (
        <div className="flex items-center justify-end gap-3 sm:justify-between">
          <p className="hidden text-xs text-zinc-500 sm:block">PDF ou imagem, até 10 MB cada.</p>
          {uploadButton}
        </div>
      ) : null}
    >
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,image/*"
        multiple
        className="hidden"
        onChange={handleFiles}
      />
      <div className="space-y-3">
        <AlertMessage message={error} onDismiss={() => setError('')} />
        {loading ? (
          <p className="text-sm text-zinc-500">Carregando comprovantes...</p>
        ) : items.length ? (
          <ul className="divide-y divide-zinc-100 rounded-lg border border-zinc-200">
            {items.map((item) => {
              const Icon = item.content_type === 'application/pdf' ? FileText : ImageIcon
              const busy = busyId === item.id
              return (
                <li key={item.id} className="flex items-center gap-3 px-3 py-2.5">
                  <Icon className="h-5 w-5 shrink-0 text-zinc-400" aria-hidden="true" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-zinc-900" title={item.original_name}>{item.original_name}</p>
                    <p className="mt-0.5 text-xs text-zinc-500">
                      {TYPE_LABELS[item.content_type] || 'Arquivo'} · {formatSize(item.size_bytes)}
                      <span className="hidden sm:inline"> · anexado em {formatDateBR(item.created_at ? getLocalDateString(new Date(item.created_at)) : '')}</span>
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-1.5">
                    <IconButton label="Abrir" icon={ExternalLink} size="sm" disabled={busy} onClick={() => handleOpen(item)} />
                    <IconButton label="Baixar" icon={Download} size="sm" disabled={busy} onClick={() => handleDownload(item)} />
                    <IconButton label="Excluir comprovante" icon={Trash2} size="sm" variant="danger" disabled={busy} onClick={() => handleDelete(item)} />
                  </div>
                </li>
              )
            })}
          </ul>
        ) : (
          <EmptyState
            icon={Paperclip}
            title="Nenhum comprovante"
            message="Anexe a nota fiscal, o recibo ou a foto do cupom. PDF ou imagem, até 10 MB."
            action={uploadButton}
            className="min-h-40"
          />
        )}
      </div>
    </Sheet>
  )
}
