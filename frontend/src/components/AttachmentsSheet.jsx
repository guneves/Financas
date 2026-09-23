import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, Download, ExternalLink, FileText, Image as ImageIcon, Paperclip, Trash2 } from 'lucide-react'
import { attachmentsApi, ccExpenseAttachmentsApi } from '../lib/dataApi'
import { saveBlob } from '../lib/api'
import { formatCurrency, formatDateBR, formatSignedCurrency, getLocalDateString } from '../lib/format'
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
// Miniatura na lista: so imagem que o navegador desenha. Sem Pillow no
// backend, a miniatura e o proprio arquivo reduzido pelo navegador — um
// comprovante tem ate 10 MB e um lancamento tem poucos.
const THUMBNAIL_TYPES = new Set(['image/jpeg', 'image/png', 'image/gif', 'image/webp'])

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} kB`
  return `${(bytes / (1024 * 1024)).toFixed(1).replace('.', ',')} MB`
}

function signOf(transaction) {
  if (transaction.type === 'TRANSFER') return 0
  return transaction.type === 'INCOME' ? 1 : -1
}

// Comprovantes de um lancamento (`transaction`) ou de uma compra no cartao
// (`purchase`, da tela Cartoes): lista, anexar (varios de uma vez), ver, abrir,
// baixar e excluir. `onChanged` roda ao fechar se algo mudou, para a tela
// recontar o clipe da linha.
export default function AttachmentsSheet({ transaction, purchase, onClose, onChanged }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [busyId, setBusyId] = useState('')
  const [error, setError] = useState('')
  const changedRef = useRef(false)
  const inputRef = useRef(null)
  const api = purchase ? ccExpenseAttachmentsApi : attachmentsApi
  const owner = purchase || transaction
  const transactionId = owner?.id
  // URLs de blob ja baixados (miniatura e visualizacao dividem o mesmo).
  const [urls, setUrls] = useState({})
  const urlsRef = useRef({})
  const [previewing, setPreviewing] = useState(null)

  const blobUrl = async (item) => {
    if (urlsRef.current[item.id]) return urlsRef.current[item.id]
    const blob = await api.file(transactionId, item.id)
    const url = URL.createObjectURL(blob)
    urlsRef.current = { ...urlsRef.current, [item.id]: url }
    setUrls(urlsRef.current)
    return url
  }

  // Miniaturas: baixa as imagens da lista em segundo plano.
  useEffect(() => {
    if (!transactionId) return
    items
      .filter((item) => THUMBNAIL_TYPES.has(item.content_type) && !urlsRef.current[item.id])
      .forEach((item) => { blobUrl(item).catch(() => {}) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, transactionId])

  // Ao trocar de lancamento ou fechar, solta os blobs.
  useEffect(() => () => {
    Object.values(urlsRef.current).forEach((url) => URL.revokeObjectURL(url))
    urlsRef.current = {}
    setUrls({})
    setPreviewing(null)
  }, [transactionId])

  useEffect(() => {
    if (!transactionId) return undefined
    let cancelled = false
    changedRef.current = false
    setItems([])
    setError('')
    setLoading(true)
    api.list(transactionId)
      .then((list) => { if (!cancelled) setItems(list) })
      .catch((err) => { if (!cancelled) setError(err.message || 'Não foi possível carregar os comprovantes.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [transactionId])

  const handlePreview = async (item) => {
    if (!OPENABLE.has(item.content_type)) {
      handleDownload(item)
      return
    }
    setBusyId(item.id)
    setError('')
    try {
      await blobUrl(item)
      setPreviewing(item)
    } catch (err) {
      setError(err.message || 'Não foi possível abrir o comprovante.')
    } finally {
      setBusyId('')
    }
  }

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
        const created = await api.upload(transactionId, file)
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
      const blob = await api.file(transactionId, item.id)
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
      const blob = await api.file(transactionId, item.id)
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
      await api.remove(transactionId, item.id)
      setItems((current) => current.filter((entry) => entry.id !== item.id))
      if (previewing?.id === item.id) setPreviewing(null)
      changedRef.current = true
    } catch (err) {
      setError(err.message || 'Não foi possível excluir o comprovante.')
    } finally {
      setBusyId('')
    }
  }

  const description = purchase
    ? [
        purchase.description,
        formatDateBR(purchase.purchase_date),
        purchase.installmentTotal > 1
          ? `${purchase.installmentTotal}x de ${formatCurrency(purchase.amount)}`
          : formatCurrency(purchase.amount),
      ].join(' · ')
    : transaction
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
      open={Boolean(owner)}
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
        {previewing ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <Button type="button" variant="subtle" size="sm" icon={ArrowLeft} onClick={() => setPreviewing(null)}>
                Voltar à lista
              </Button>
              <div className="flex shrink-0 gap-1.5">
                <IconButton label="Abrir em nova aba" icon={ExternalLink} size="sm" onClick={() => handleOpen(previewing)} />
                <IconButton label="Baixar" icon={Download} size="sm" onClick={() => handleDownload(previewing)} />
              </div>
            </div>
            <p className="truncate text-sm font-medium text-zinc-900" title={previewing.original_name}>{previewing.original_name}</p>
            {previewing.content_type === 'application/pdf' ? (
              <iframe
                src={urls[previewing.id]}
                title={previewing.original_name}
                className="h-[60vh] w-full rounded-lg border border-zinc-200 bg-white"
              />
            ) : (
              <img
                src={urls[previewing.id]}
                alt={previewing.original_name}
                className="mx-auto max-h-[60vh] w-auto rounded-lg border border-zinc-200 object-contain"
              />
            )}
          </div>
        ) : loading ? (
          <p className="text-sm text-zinc-500">Carregando comprovantes...</p>
        ) : items.length ? (
          <ul className="divide-y divide-zinc-100 rounded-lg border border-zinc-200">
            {items.map((item) => {
              const Icon = item.content_type === 'application/pdf' ? FileText : ImageIcon
              const busy = busyId === item.id
              return (
                <li key={item.id} className="flex items-center gap-3 px-3 py-2.5">
                  <button
                    type="button"
                    onClick={() => handlePreview(item)}
                    aria-label={`Ver ${item.original_name}`}
                    className="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-zinc-200 bg-zinc-50"
                  >
                    {urls[item.id] && THUMBNAIL_TYPES.has(item.content_type) ? (
                      <img src={urls[item.id]} alt="" className="h-full w-full object-cover" />
                    ) : (
                      <Icon className="h-5 w-5 text-zinc-400" aria-hidden="true" />
                    )}
                  </button>
                  <div className="min-w-0 flex-1">
                    <button
                      type="button"
                      onClick={() => handlePreview(item)}
                      className="block max-w-full truncate text-left text-sm font-medium text-zinc-900 hover:underline"
                      title={item.original_name}
                    >
                      {item.original_name}
                    </button>
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
