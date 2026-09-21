import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { NavLink } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  ChevronDown,
  Info,
  Loader2,
  X,
} from 'lucide-react'

export function cx(...classes) {
  return classes.filter(Boolean).join(' ')
}

const buttonVariants = {
  primary: 'bg-emerald-600 text-white hover:bg-emerald-700 border-emerald-600 shadow-sm hover:shadow-glow',
  secondary: 'bg-white text-zinc-800 hover:bg-zinc-50 border-zinc-300',
  dark: 'bg-zinc-900 text-white hover:bg-zinc-800 border-zinc-900',
  danger: 'bg-white text-rose-600 hover:bg-rose-50 border-rose-200',
  subtle: 'bg-zinc-100 text-zinc-700 hover:bg-zinc-200 border-zinc-100',
}

const buttonSizes = {
  sm: 'h-9 px-3 text-sm',
  md: 'h-10 px-4 text-sm',
  lg: 'h-11 px-5 text-sm',
}

export function Button({
  children,
  className = '',
  variant = 'primary',
  size = 'md',
  icon: Icon,
  loading = false,
  disabled,
  ...props
}) {
  return (
    <button
      className={cx(
        'inline-flex items-center justify-center gap-2 rounded-lg border font-semibold transition duration-150',
        'active:scale-[0.97]',
        'disabled:pointer-events-none disabled:opacity-55',
        buttonVariants[variant],
        buttonSizes[size],
        className
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : Icon ? <Icon className="h-4 w-4" /> : null}
      {children}
    </button>
  )
}

export function IconButton({ label, icon: Icon, className = '', variant = 'secondary', ...props }) {
  return (
    <button
      aria-label={label}
      title={label}
      className={cx(
        // 44px no toque; volta a 36px no desktop, onde o ponteiro e preciso.
        'inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border transition active:scale-95 lg:h-9 lg:w-9',
        buttonVariants[variant],
        className
      )}
      {...props}
    >
      <Icon className="h-4 w-4" />
    </button>
  )
}

const badgeTones = {
  neutral: 'border-zinc-200 bg-zinc-50 text-zinc-700',
  info: 'border-sky-200 bg-sky-50 text-sky-700',
  success: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  warning: 'border-amber-200 bg-amber-50 text-amber-700',
  danger: 'border-rose-200 bg-rose-50 text-rose-700',
}

export function Badge({ children, tone = 'neutral', className = '' }) {
  return (
    <span className={cx('inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold', badgeTones[tone], className)}>
      {children}
    </span>
  )
}

export function Panel({ children, className = '', as: Component = 'section', interactive = false, ...props }) {
  return (
    <Component
      {...props}
      className={cx(
        'rounded-xl border border-zinc-200/80 bg-white shadow-card',
        interactive && 'transition duration-200 hover:-translate-y-0.5 hover:border-zinc-300 hover:shadow-lift',
        className
      )}
    >
      {children}
    </Component>
  )
}

export function PanelHeader({ title, description, actions, className = '' }) {
  return (
    <div className={cx('flex flex-col gap-3 border-b border-zinc-100 px-5 py-4 sm:flex-row sm:items-start sm:justify-between', className)}>
      <div className="min-w-0">
        <h2 className="text-base font-semibold text-zinc-950">{title}</h2>
        {description ? <p className="mt-1 text-sm text-zinc-500">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  )
}

const metricTones = {
  neutral: 'bg-zinc-100 text-zinc-700',
  dark: 'bg-zinc-900 text-white',
  success: 'bg-emerald-100 text-emerald-700',
  info: 'bg-sky-100 text-sky-700',
  warning: 'bg-amber-100 text-amber-700',
  danger: 'bg-rose-100 text-rose-700',
}

// Conta de 0 ate o valor com ease-out. Ao mudar o valor, anima do anterior
// ate o novo — assim um pagamento de fatura "desce" o saldo na tela.
export function useCountUp(target, duration = 700) {
  const [display, setDisplay] = useState(target)
  const fromRef = useRef(0)
  const frameRef = useRef(null)

  useEffect(() => {
    const to = Number(target) || 0
    const from = fromRef.current
    const reduce = typeof window !== 'undefined'
      && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

    if (reduce || from === to) {
      fromRef.current = to
      setDisplay(to)
      return undefined
    }

    const start = performance.now()
    const tick = (now) => {
      const progress = Math.min((now - start) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      setDisplay(from + (to - from) * eased)
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(tick)
      } else {
        fromRef.current = to
      }
    }
    frameRef.current = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(frameRef.current)
      fromRef.current = to
    }
  }, [target, duration])

  return display
}

export function AnimatedNumber({ value, format = (v) => v, className = '' }) {
  const display = useCountUp(value)
  return <span className={className}>{format(display)}</span>
}

// Variacao percentual com seta. `inverse` para metricas em que subir e ruim
// (despesas): a cor segue o significado, nao o sinal.
export function DeltaBadge({ value, inverse = false, suffix = '', className = '' }) {
  if (value === null || value === undefined || !Number.isFinite(value)) return null
  const isUp = value >= 0
  const isGood = inverse ? !isUp : isUp
  const Icon = isUp ? ArrowUpRight : ArrowDownRight
  return (
    <span
      className={cx(
        'inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-xs font-semibold tabular',
        isGood ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700',
        className
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {Math.abs(value).toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%{suffix}
    </span>
  )
}

export function MetricCard({
  title,
  value,
  amount,
  format,
  subtitle,
  footer,
  icon: Icon,
  tone = 'neutral',
  valueClassName = '',
  className = '',
  delta,
  chart,
}) {
  const animated = typeof amount === 'number' && typeof format === 'function'
  return (
    <Panel interactive className={cx('relative overflow-hidden p-5', className)}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{title}</p>
          <p className={cx('mt-2 truncate text-2xl font-bold tracking-tight text-zinc-950', valueClassName)}>
            {animated ? <AnimatedNumber value={amount} format={format} /> : value}
          </p>
          {subtitle || delta ? (
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-zinc-500">
              {delta}
              {subtitle ? <span>{subtitle}</span> : null}
            </div>
          ) : null}
        </div>
        {Icon ? (
          <div className={cx('flex h-10 w-10 shrink-0 items-center justify-center rounded-xl', metricTones[tone])}>
            <Icon className="h-5 w-5" />
          </div>
        ) : null}
      </div>
      {chart ? <div className="-mx-1 mt-3 h-12">{chart}</div> : null}
      {footer ? <div className="mt-4 border-t border-zinc-100 pt-3 text-sm text-zinc-500">{footer}</div> : null}
    </Panel>
  )
}

export function Skeleton({ className = '' }) {
  return <div className={cx('skeleton', className)} />
}

export function PageHeader({ eyebrow, title, description, actions, meta }) {
  return (
    <div className="flex animate-fade-up flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow ? <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-emerald-700">{eyebrow}</p> : null}
        <h1 className="text-2xl font-bold tracking-tight text-zinc-950 sm:text-3xl">{title}</h1>
        {description ? <p className="mt-2 max-w-3xl text-sm text-zinc-500">{description}</p> : null}
        {meta ? <div className="mt-3 flex flex-wrap gap-2">{meta}</div> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  )
}

export function SegmentedControl({ items, value, onChange, className = '' }) {
  return (
    <div className={cx('inline-flex max-w-full gap-1 overflow-x-auto rounded-lg border border-zinc-200 bg-zinc-100 p-1', className)}>
      {items.map((item) => {
        const Icon = item.icon
        const isActive = item.value === value
        return (
          <button
            key={item.value}
            type="button"
            onClick={() => onChange(item.value)}
            className={cx(
              'inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-md px-3 text-sm font-semibold transition duration-200',
              isActive ? 'bg-white text-zinc-950 shadow-card ring-1 ring-zinc-200/70' : 'text-zinc-600 hover:bg-white/60 hover:text-zinc-950'
            )}
          >
            {Icon ? <Icon className="h-4 w-4" /> : null}
            {item.label}
          </button>
        )
      })}
    </div>
  )
}

export function Field({ label, children, className = '', hint }) {
  return (
    <label className={cx('block space-y-1.5', className)}>
      {label ? <span className="text-sm font-medium text-zinc-700">{label}</span> : null}
      {children}
      {hint ? <span className="block text-xs text-zinc-500">{hint}</span> : null}
    </label>
  )
}

export function EmptyState({ icon: Icon, title, message, action, className = '' }) {
  return (
    <div className={cx('flex min-h-52 animate-fade-in flex-col items-center justify-center rounded-xl border border-dashed border-zinc-200 bg-zinc-50 px-6 py-10 text-center', className)}>
      {Icon ? (
        <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-white text-zinc-500 shadow-sm">
          <Icon className="h-5 w-5" />
        </div>
      ) : null}
      <p className="font-semibold text-zinc-800">{title}</p>
      {message ? <p className="mt-1 max-w-md text-sm text-zinc-500">{message}</p> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  )
}

const alertTones = {
  danger: { classes: 'border-rose-200 bg-rose-50 text-rose-700', icon: AlertTriangle },
  warning: { classes: 'border-amber-200 bg-amber-50 text-amber-800', icon: AlertTriangle },
  success: { classes: 'border-emerald-200 bg-emerald-50 text-emerald-700', icon: CheckCircle2 },
  info: { classes: 'border-sky-200 bg-sky-50 text-sky-700', icon: Info },
}

// O unico banner de aviso/erro do app. `message` ou `children`; nada = nao renderiza.
export function AlertMessage({ tone = 'danger', message, children, onDismiss, className = '' }) {
  const content = children ?? message
  if (!content) return null
  const { classes, icon: Icon } = alertTones[tone] || alertTones.danger
  return (
    <div role={tone === 'danger' ? 'alert' : 'status'} className={cx('flex animate-slide-down items-start gap-3 rounded-lg border px-4 py-3 text-sm font-medium', classes, className)}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0 flex-1">{content}</div>
      {onDismiss ? (
        <button type="button" onClick={onDismiss} aria-label="Fechar aviso" className="-m-1 rounded p-1 opacity-70 hover:opacity-100">
          <X className="h-4 w-4" />
        </button>
      ) : null}
    </div>
  )
}

// Abas ligadas a rota: cada item e um link, o ativo e o da URL atual.
export function Tabs({ items, className = '' }) {
  return (
    <nav className={cx('inline-flex max-w-full gap-1 overflow-x-auto rounded-lg border border-zinc-200 bg-zinc-100 p-1', className)}>
      {items.map((item) => {
        const Icon = item.icon
        return (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) => cx(
              'inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-md px-3 text-sm font-semibold transition duration-200 lg:h-9',
              isActive ? 'bg-white text-zinc-950 shadow-card ring-1 ring-zinc-200/70' : 'text-zinc-600 hover:bg-white/60 hover:text-zinc-950'
            )}
          >
            {Icon ? <Icon className="h-4 w-4" /> : null}
            {item.label}
          </NavLink>
        )
      })}
    </nav>
  )
}

// Botao que expande um formulario logo abaixo. Controlado (`open` + `onOpenChange`)
// ou nao controlado (`defaultOpen`).
export function Collapsible({
  label,
  icon,
  open: openProp,
  defaultOpen = false,
  onOpenChange,
  variant = 'primary',
  size = 'md',
  className = '',
  buttonClassName = '',
  children,
}) {
  const [internalOpen, setInternalOpen] = useState(defaultOpen)
  const isControlled = openProp !== undefined
  const open = isControlled ? openProp : internalOpen
  const contentId = useId()

  const toggle = () => {
    const next = !open
    if (!isControlled) setInternalOpen(next)
    onOpenChange?.(next)
  }

  return (
    <div className={className}>
      <Button
        type="button"
        variant={open ? 'secondary' : variant}
        size={size}
        icon={icon}
        onClick={toggle}
        aria-expanded={open}
        aria-controls={contentId}
        className={buttonClassName}
      >
        {label}
        <ChevronDown className={cx('h-4 w-4 transition-transform', open && 'rotate-180')} />
      </Button>
      {open ? (
        <div id={contentId} className="mt-4 animate-slide-down">
          {children}
        </div>
      ) : null}
    </div>
  )
}

// Modal no desktop, folha que sobe de baixo no celular. Esc e clique fora fecham.
// Vai para document.body via portal: o wrapper animado do Layout tem transform,
// o que faria `fixed` se medir pela pagina e nao pela janela.
export function Sheet({ open, onClose, title, description, children, footer, className = '' }) {
  useEffect(() => {
    if (!open) return undefined
    const onKey = (event) => {
      if (event.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', onKey)
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previousOverflow
    }
  }, [open, onClose])

  if (!open) return null

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-4" role="dialog" aria-modal="true" aria-label={typeof title === 'string' ? title : undefined}>
      <div className="absolute inset-0 animate-fade-in bg-zinc-950/40 backdrop-blur-sm" onClick={onClose} />
      <div
        className={cx(
          'relative flex max-h-[92vh] w-full animate-fade-up flex-col overflow-hidden rounded-t-2xl bg-white shadow-lift',
          'sm:max-w-xl sm:animate-scale-in sm:rounded-2xl',
          className
        )}
      >
        <div className="mx-auto mt-2 h-1.5 w-10 rounded-full bg-zinc-200 sm:hidden" />
        <div className="flex items-start justify-between gap-4 border-b border-zinc-100 px-5 py-4">
          <div className="min-w-0">
            {title ? <h2 className="text-lg font-bold text-zinc-950">{title}</h2> : null}
            {description ? <p className="mt-1 text-sm text-zinc-600">{description}</p> : null}
          </div>
          <IconButton label="Fechar" icon={X} variant="subtle" onClick={onClose} />
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer ? <div className="border-t border-zinc-100 px-5 py-4 pb-[max(1rem,env(safe-area-inset-bottom))]">{footer}</div> : null}
      </div>
    </div>,
    document.body
  )
}
