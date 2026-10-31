import { useState } from 'react'
import { Check, CheckCheck, CreditCard } from 'lucide-react'
import { Badge, Button, Panel, PanelHeader, cx } from '../../components/ui'
import { reviewApi } from '../../lib/dataApi'
import { formatSignedCurrency } from '../../lib/format'
import {
  reviewCanBeRepasse,
  reviewCategoryType,
  reviewHasCategory,
  reviewKey,
  reviewNoticeText,
  reviewPayload,
  reviewPlace,
  reviewSign,
} from '../../lib/review'
import { toast } from '../../lib/toast'
import { formatDateBR } from './helpers'

// Quantos de uma vez na tela: o resto vem com "Mostrar todos".
const FIRST = 5

// Revisar (045): o que a notificacao e a Pluggy gravaram sozinhas. O trabalho
// do dono e so este: a categoria (ja vem sugerida) e um toque em "É meu"; numa
// receita, "É receita" ou "É repasse" (dinheiro de outra pessoa).
// "Confirmar todos" leva as categorias como estao na tela.
export default function ReviewPanel({ items, categoryOptionsFor, onError }) {
  const [chosen, setChosen] = useState({})
  const [busy, setBusy] = useState('')
  const [showAll, setShowAll] = useState(false)

  if (!items.length) return null
  const visible = showAll ? items : items.slice(0, FIRST)

  const confirm = async (list, key) => {
    setBusy(key)
    onError('')
    try {
      const body = await reviewApi.confirm(reviewPayload(list, chosen))
      toast(body.reviewed === 1 ? 'Confirmado.' : `${body.reviewed} lançamentos confirmados.`)
    } catch (error) {
      onError(error.message || 'Não foi possível confirmar.')
    } finally {
      setBusy('')
    }
  }

  const categorySelect = (item) => {
    const key = reviewKey(item)
    const options = categoryOptionsFor(reviewCategoryType(item))
    const value = chosen[key] ?? item.category_id ?? ''
    return (
      <select
        value={value}
        onChange={(event) => setChosen({ ...chosen, [key]: event.target.value })}
        aria-label={`Categoria de ${item.description || 'lançamento'}`}
        className="app-select"
      >
        {/* A categoria sugerida, quando ela nao esta na lista (texto livre). */}
        {!options.some((option) => option.id === value) ? <option value={value}>{item.category || 'Sem categoria'}</option> : null}
        {options.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
      </select>
    )
  }

  return (
    <Panel className="overflow-clip">
      <PanelHeader
        title="Revisar"
        description={reviewNoticeText(items.length)}
        actions={items.length > 1 ? (
          <Button type="button" variant="secondary" icon={CheckCheck} disabled={Boolean(busy)} onClick={() => confirm(items, 'all')}>
            Confirmar todos ({items.length})
          </Button>
        ) : null}
      />
      <ul className="divide-y divide-zinc-100">
        {visible.map((item) => {
          const key = reviewKey(item)
          return (
            <li key={key} className="grid gap-3 px-4 py-3 sm:px-5 md:grid-cols-[minmax(0,1fr)_minmax(0,14rem)_auto] md:items-center">
              <div className="flex min-w-0 items-center gap-3">
                <div className="min-w-0 flex-1">
                  <p className="flex min-w-0 items-center gap-2">
                    <span className="truncate font-medium text-zinc-900" title={item.description}>{item.description || item.category}</span>
                    {item.table === 'cc_expenses' ? (
                      <Badge><CreditCard className="mr-1 h-3 w-3" aria-hidden="true" />Cartão</Badge>
                    ) : null}
                  </p>
                  <p className="truncate text-xs text-zinc-500">{formatDateBR(item.date)} · {reviewPlace(item)}</p>
                </div>
                <p className={cx('num shrink-0 font-semibold', reviewSign(item) > 0 ? 'text-emerald-700' : reviewSign(item) < 0 ? 'text-zinc-950' : 'text-zinc-500')}>
                  {formatSignedCurrency(item.amount, reviewSign(item))}
                </p>
              </div>
              {reviewHasCategory(item) ? categorySelect(item) : <span className="text-sm text-zinc-500">Transferência</span>}
              <div className="flex gap-2">
                <Button type="button" icon={Check} disabled={Boolean(busy)} onClick={() => confirm([item], key)} className="flex-1 md:flex-none">
                  {reviewCanBeRepasse(item) ? 'É receita' : 'É meu'}
                </Button>
                {reviewCanBeRepasse(item) ? (
                  <Button type="button" variant="secondary" disabled={Boolean(busy)} onClick={() => confirm([{ ...item, repasse: true }], key)} className="flex-1 md:flex-none">
                    É repasse
                  </Button>
                ) : null}
              </div>
            </li>
          )
        })}
      </ul>
      {items.length > FIRST ? (
        <div className="border-t border-zinc-100 px-5 py-3 text-center">
          <Button type="button" variant="secondary" onClick={() => setShowAll((open) => !open)}>
            {showAll ? 'Mostrar menos' : `Mostrar todos (${items.length})`}
          </Button>
        </div>
      ) : null}
    </Panel>
  )
}
