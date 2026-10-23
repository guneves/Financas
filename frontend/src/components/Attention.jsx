import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Bell, ChevronRight, CreditCard, Repeat, Target, Wallet } from 'lucide-react'
import { useAttentionItems } from '../lib/attention'
import { attentionLink, attentionText, bellBadge, bellLabel } from '../lib/attentionRules'
import { formatCurrency } from '../lib/format'
import { useLayer } from '../lib/layers'
import { usePrivateFormatter } from '../lib/privacy'
import { cx } from './ui'

// Os avisos de "Precisa de atencao" (GET /api/attention) desenhados: os
// cartoes do Inicio e a lista do sino do cabecalho usam o mesmo texto. O
// servidor manda so os numeros; o texto e daqui.

const attentionTones = {
  danger: 'bg-rose-100 text-rose-700',
  warning: 'bg-amber-100 text-amber-800',
  info: 'bg-sky-100 text-sky-700',
}

const ICONS = {
  INVOICE_OVERDUE: CreditCard,
  INVOICE_PAYABLE: CreditCard,
  AUTOPAY_SHORTFALL: Wallet,
  RECURRING: Repeat,
  OVER_BUDGET: Target,
}

// Titulo e detalhe de um aviso (lib/attentionRules.js). O saldo da conta (e o
// que falta, que o revela) somem no modo privado.
function useAttentionText() {
  const privateMoney = usePrivateFormatter(formatCurrency)
  return (item) => attentionText(item, privateMoney)
}

export function AttentionLink({ to, children, onClick }) {
  return (
    <Link to={to} onClick={onClick} className="inline-flex min-h-11 items-center gap-1 text-sm font-bold text-emerald-700 lg:min-h-9 underline-offset-2 hover:underline">
      {children}
      <ChevronRight className="h-4 w-4" aria-hidden="true" />
    </Link>
  )
}

function AttentionIcon({ item }) {
  const Icon = ICONS[item.kind] || Bell
  return (
    <span className={cx('flex h-9 w-9 shrink-0 items-center justify-center rounded-xl', attentionTones[item.tone])}>
      <Icon className="h-4 w-4" />
    </span>
  )
}

// Os cartoes do Inicio. `actions` troca o link de um tipo por uma acao da tela
// (pagar a fatura, lancar as recorrencias); a recorrencia mantem o link no
// detalhe.
export function AttentionCards({ items, actions = {} }) {
  const text = useAttentionText()
  return (
    <ul className="stagger grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => {
        const { title, detail } = text(item)
        const link = attentionLink(item.kind)
        const action = actions[item.kind]
        const linkElement = link ? <AttentionLink to={link.to}>{link.label}</AttentionLink> : null
        return (
          <li key={item.key} className="flex min-w-0 flex-col gap-3 rounded-[1.25rem] border border-zinc-200/60 bg-white p-4">
            <AttentionIcon item={item} />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-bold text-zinc-950">{title}</p>
              <div className="mt-1 text-sm text-zinc-600">{detail || (action ? linkElement : null)}</div>
            </div>
            <div>{action || linkElement}</div>
          </li>
        )
      })}
    </ul>
  )
}

// Sino do cabecalho: todos os avisos de agora, os dispensados no Inicio
// inclusive. Fecha com Esc, clique fora ou ao navegar.
export function AttentionBell() {
  const items = useAttentionItems()
  const text = useAttentionText()
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)
  const buttonRef = useRef(null)
  const location = useLocation()
  const count = items.length

  useEffect(() => { setOpen(false) }, [location.pathname])

  useEffect(() => {
    if (!open) return undefined
    const onPointer = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpen(false)
    }
    document.addEventListener('pointerdown', onPointer)
    return () => document.removeEventListener('pointerdown', onPointer)
  }, [open])

  useLayer(open, () => {
    setOpen(false)
    buttonRef.current?.focus()
  })

  const label = bellLabel(count)

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={label}
        title={label}
        className={cx(
          'relative inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border transition',
          open ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-100 hover:text-zinc-950'
        )}
      >
        <Bell className="h-5 w-5" />
        {count ? (
          <span aria-hidden="true" className="absolute -right-0.5 -top-0.5 flex h-5 min-w-5 items-center justify-center rounded-full border border-white bg-amber-100 px-1 text-[11px] font-bold leading-none text-amber-800">
            {bellBadge(count)}
          </span>
        ) : null}
      </button>
      {open ? (
        <div
          role="dialog"
          aria-label="Precisa de atenção"
          className="fixed inset-x-4 top-[4.5rem] z-40 max-h-[70dvh] animate-slide-down overflow-y-auto rounded-2xl border border-zinc-200 bg-white p-1.5 shadow-lift sm:absolute sm:inset-x-auto sm:right-0 sm:top-full sm:mt-2 sm:w-96"
        >
          <p className="px-3 py-2 text-sm font-semibold text-zinc-950">Precisa de atenção</p>
          {count === 0 ? (
            <p className="px-3 pb-3 text-sm text-zinc-600">Nada pendente agora.</p>
          ) : (
            <ul className="space-y-1">
              {items.map((item) => {
                const { title, detail } = text(item)
                const link = attentionLink(item.kind)
                return (
                  <li key={item.key}>
                    <Link
                      to={link?.to || '/inicio'}
                      onClick={() => setOpen(false)}
                      className="flex items-start gap-3 rounded-xl px-3 py-2.5 transition hover:bg-zinc-100"
                    >
                      <AttentionIcon item={item} />
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-bold text-zinc-950">{title}</span>
                        {detail ? <span className="mt-0.5 block text-sm text-zinc-600">{detail}</span> : null}
                        {link ? <span className="mt-0.5 block text-sm font-bold text-emerald-700">{link.label}</span> : null}
                      </span>
                    </Link>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  )
}
