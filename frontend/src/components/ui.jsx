import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { NavLink, useLocation } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  ChevronDown,
  Info,
  Loader2,
  X,
} from 'lucide-react'
import { MASKED_CURRENCY, useValuesHidden } from '../lib/privacy'

export function cx(...classes) {
  return classes.filter(Boolean).join(' ')
}

// O CSS (index.css) ja zera animacoes e transicoes no modo reduzido; isto e
// para o que roda em JS: contagem de numeros, graficos, tempos de saida.
export function prefersReducedMotion() {
  return typeof window !== 'undefined'
    && Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)
}

// Mantem montado durante a saida. `closing` e true nos `exitMs` entre o
// `open` virar false e a desmontagem — o tempo da animacao de saida.
export function usePresence(open, exitMs = 200) {
  const [mounted, setMounted] = useState(open)
  if (open && !mounted) setMounted(true)

  useEffect(() => {
    if (open || !mounted) return undefined
    const timer = setTimeout(() => setMounted(false), prefersReducedMotion() ? 0 : exitMs)
    return () => clearTimeout(timer)
  }, [open, mounted, exitMs])

  return { mounted: open || mounted, closing: !open && mounted }
}

const defaultGetId = (item) => item.id

// Ids que chegaram na lista depois que `version` mudou (um "+ Novo" salvo).
// A lista so muda quando a busca volta, entao a mudanca de versao "arma" e a
// proxima mudanca da lista compara com a foto tirada naquele momento.
// Filtros e a carga inicial nao armam: so o que acabou de ser gravado pisca.
export function useArrivals(items, version, getId = defaultGetId) {
  const [arrived, setArrived] = useState(() => new Set())
  const versionRef = useRef(version)
  const snapshotRef = useRef(null)
  const itemsRef = useRef(items)

  useEffect(() => {
    if (versionRef.current === version) return
    versionRef.current = version
    snapshotRef.current = new Set(itemsRef.current.map(getId))
  }, [version, getId])

  useEffect(() => {
    itemsRef.current = items
    const snapshot = snapshotRef.current
    if (!snapshot) return undefined
    // A primeira mudanca depois de armar e a recarga: desarma com ou sem
    // novidade, senao um filtro trocado depois piscaria linhas antigas.
    snapshotRef.current = null
    const fresh = items.map(getId).filter((id) => !snapshot.has(id))
    if (fresh.length === 0) return undefined
    setArrived(new Set(fresh))
    const timer = setTimeout(() => setArrived(new Set()), 1800)
    return () => clearTimeout(timer)
  }, [items, getId])

  return arrived
}

const buttonVariants = {
  // Primario no verde profundo da marca (direcao C); o verde vivo fica para "+ Novo".
  primary: 'bg-brand text-brand-ink hover:bg-brand/90 border-brand',
  secondary: 'bg-white text-zinc-800 hover:bg-zinc-100 border-zinc-200',
  dark: 'bg-zinc-900 text-white hover:bg-zinc-800 border-zinc-900',
  danger: 'bg-white text-rose-600 hover:bg-rose-50 border-rose-200',
  subtle: 'bg-zinc-100 text-zinc-700 hover:bg-zinc-200 border-zinc-100',
}

const buttonSizes = {
  sm: 'h-9 px-3.5 text-sm',
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
        'inline-flex items-center justify-center gap-2 rounded-full border font-semibold transition duration-150',
        'active:scale-[0.97]',
        'disabled:pointer-events-none disabled:border-zinc-200 disabled:bg-zinc-100 disabled:text-zinc-400 disabled:shadow-none',
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

// 44px no toque; no desktop, onde o ponteiro e preciso, 36px — ou 32px com
// size="sm", para acoes dentro de linha de tabela (a linha fica em ~44px).
const iconButtonSizes = {
  md: 'lg:h-9 lg:w-9',
  sm: 'lg:h-8 lg:w-8',
}

export function IconButton({ label, icon: Icon, className = '', variant = 'secondary', size = 'md', ...props }) {
  return (
    <button
      aria-label={label}
      title={label}
      className={cx(
        'inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border transition active:scale-95',
        iconButtonSizes[size],
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
    <span className={cx('inline-flex items-center whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-semibold', badgeTones[tone], className)}>
      {children}
    </span>
  )
}

export function Panel({ children, className = '', as: Component = 'section', interactive = false, ...props }) {
  return (
    <Component
      {...props}
      className={cx(
        // Bloco liso e arredondado (direcao C): sem sombra; a borda fica para o
        // escuro nao virar uma massa unica.
        'rounded-[1.25rem] border border-zinc-200/60 bg-white',
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
    <div className={cx('flex flex-col gap-3 border-b border-zinc-100 px-5 py-4 sm:flex-row sm:items-start sm:justify-between sm:px-6', className)}>
      <div className="min-w-0">
        <h2 className="text-[17px] font-bold tracking-tight text-zinc-950">{title}</h2>
        {description ? <p className="mt-1 hidden text-sm text-zinc-500 sm:block">{description}</p> : null}
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

// Ultimo valor mostrado por `cacheKey`, na sessao. Voltar a uma pagina (ou
// remontar) comeca do valor que ja estava na tela — so a primeira carga conta
// a partir de zero, e dali em diante so uma mudanca real anima.
const countUpCache = new Map()

// Conta ate o valor com easeOutQuint (a curva do app). Ao mudar o valor, anima
// do que esta na tela ate o novo — assim um pagamento de fatura "desce" o saldo.
export function useCountUp(target, { duration = 500, cacheKey } = {}) {
  const displayRef = useRef(null)
  if (displayRef.current === null) {
    displayRef.current = prefersReducedMotion()
      ? Number(target) || 0
      : (cacheKey && countUpCache.has(cacheKey) ? countUpCache.get(cacheKey) : 0)
  }
  const [display, setDisplay] = useState(displayRef.current)

  useEffect(() => {
    const to = Number(target) || 0
    if (cacheKey) countUpCache.set(cacheKey, to)
    const from = displayRef.current

    if (prefersReducedMotion() || from === to) {
      displayRef.current = to
      setDisplay(to)
      return undefined
    }

    let frame = null
    const start = performance.now()
    const tick = (now) => {
      const progress = Math.min((now - start) / duration, 1)
      const value = from + (to - from) * (1 - Math.pow(1 - progress, 5))
      displayRef.current = progress < 1 ? value : to
      setDisplay(displayRef.current)
      if (progress < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [target, duration, cacheKey])

  return display
}

// `masked`: modo privado. A contagem segue montada por baixo, entao revelar
// mostra o valor direto, sem recontar.
export function AnimatedNumber({ value, format = (v) => v, cacheKey, masked = false, className = '' }) {
  const display = useCountUp(value, { cacheKey })
  return <span className={className}>{masked ? MASKED_CURRENCY : format(display)}</span>
}

// Variacao percentual com seta. `inverse` para metricas em que subir e ruim
// (despesas): a cor segue o significado, nao o sinal.
export function DeltaBadge({ value, inverse = false, suffix = '', className = '' }) {
  if (value === null || value === undefined || !Number.isFinite(value)) return null
  const isUp = value >= 0
  const isGood = inverse ? !isUp : isUp
  // Arredondado para 0% nao e nem bom nem ruim: sem cor.
  const isFlat = Math.abs(value) < 0.05
  const Icon = isUp ? ArrowUpRight : ArrowDownRight
  return (
    <span
      className={cx(
        'inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-xs font-semibold tabular',
        isFlat ? 'bg-zinc-100 text-zinc-600' : isGood ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700',
        className
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {Math.abs(value).toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%{suffix}
    </span>
  )
}

// Valor em uma linha que encolhe (nunca cresce) ate caber na largura. Mede
// `measure` — o texto final — numa copia invisivel no tamanho base, e reduz a
// fonte na proporcao que falta; a altura da linha fica a do tamanho base, para
// o cartao nao mudar de altura. Sem `measure`, so nao quebra a linha.
export function FitValue({ children, measure, baseSize = 24, minSize = 15, className = '' }) {
  const boxRef = useRef(null)
  const probeRef = useRef(null)
  const [size, setSize] = useState(baseSize)

  useLayoutEffect(() => {
    let active = true
    const fit = () => {
      const box = boxRef.current
      const probe = probeRef.current
      if (!active || !box || !probe) return
      const available = box.clientWidth
      const needed = probe.scrollWidth
      if (!available || !needed) return
      setSize(Math.max(minSize, Math.min(baseSize, Math.floor((baseSize * available * 10) / needed) / 10)))
    }
    fit()
    // A medida muda quando a fonte termina de carregar: observar a copia
    // invisivel pega isso (o fonts.ready pode resolver antes do peso usado).
    document.fonts?.ready?.then(fit)
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(fit) : null
    if (boxRef.current) observer?.observe(boxRef.current)
    if (probeRef.current) observer?.observe(probeRef.current)
    return () => {
      active = false
      observer?.disconnect()
    }
  }, [measure, baseSize, minSize])

  return (
    // overflow-hidden: a copia invisivel e mais larga que a caixa e, sem
    // isto, alarga a pagina quando o pai nao corta (bloco de patrimonio).
    <div ref={boxRef} className={cx('relative min-w-0 overflow-hidden', className)} style={{ lineHeight: `${Math.round(baseSize * 1.25)}px` }}>
      {measure ? (
        <span ref={probeRef} aria-hidden="true" className="invisible absolute left-0 top-0 whitespace-nowrap" style={{ fontSize: baseSize }}>
          {measure}
        </span>
      ) : null}
      <span className="block overflow-hidden text-ellipsis whitespace-nowrap" style={{ fontSize: measure ? size : baseSize }}>
        {children}
      </span>
    </div>
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
  // Saldo ou carteira: some no modo privado (lib/privacy.js).
  sensitive = false,
}) {
  const animated = typeof amount === 'number' && typeof format === 'function'
  const masked = useValuesHidden() && sensitive
  // O valor final, para medir: durante a contagem o texto muda a cada quadro.
  const finalText = masked
    ? MASKED_CURRENCY
    : animated ? format(amount) : (typeof value === 'string' || typeof value === 'number' ? String(value) : null)
  return (
    <Panel className={cx('relative overflow-hidden p-4 sm:p-6', className)}>
      {/* Icone ao lado do rotulo, nao do valor: o valor fica com a largura
          toda do cartao e nunca vira "R$ 1.99…". */}
      <div className="flex items-center gap-2.5">
        {Icon ? (
          <span className={cx('flex h-8 w-8 shrink-0 items-center justify-center rounded-xl', metricTones[tone])}>
            <Icon className="h-4 w-4" />
          </span>
        ) : null}
        <p className="min-w-0 text-sm font-semibold leading-5 text-zinc-600">{title}</p>
      </div>
      <FitValue measure={finalText} className={cx('mt-3 font-extrabold tracking-tight text-zinc-950', valueClassName)}>
        {animated ? (
          <AnimatedNumber
            value={amount}
            format={format}
            masked={masked}
            cacheKey={typeof title === 'string' ? `${window.location.pathname}|${title}` : undefined}
          />
        ) : masked ? MASKED_CURRENCY : value}
      </FitValue>
      {subtitle || delta ? (
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-zinc-500">
          {delta}
          {subtitle ? <span>{subtitle}</span> : null}
        </div>
      ) : null}
      {chart ? <div className="-mx-1 mt-3 h-12">{chart}</div> : null}
      {footer ? <div className="mt-4 border-t border-zinc-100 pt-3 text-sm text-zinc-500">{footer}</div> : null}
    </Panel>
  )
}

export function Skeleton({ className = '' }) {
  return <div className={cx('skeleton', className)} />
}

export function PageHeader({ title, description, actions, meta }) {
  return (
    <div className="flex animate-fade-up flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-3xl font-extrabold tracking-tight text-zinc-950">{title}</h1>
        {/* No celular a descricao sai: o conteudo sobe para a primeira dobra. */}
        {description ? <p className="mt-2 hidden max-w-3xl text-sm text-zinc-500 sm:block">{description}</p> : null}
        {meta ? <div className="mt-3 flex flex-wrap gap-2">{meta}</div> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  )
}

export function SegmentedControl({ items, value, onChange, className = '' }) {
  const containerRef = useRef(null)
  const pill = useSlidingPill(containerRef, '[aria-pressed="true"]', [value, items])
  return (
    <div ref={containerRef} className={cx('relative inline-flex max-w-full gap-1 overflow-x-auto rounded-full border border-zinc-200 bg-white p-1', className)}>
      <PillBackground pill={pill} />
      {items.map((item) => {
        const Icon = item.icon
        const isActive = item.value === value
        return (
          <button
            key={item.value}
            type="button"
            aria-pressed={isActive}
            onClick={() => onChange(item.value)}
            className={cx(
              'relative inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-full px-3.5 text-sm font-semibold transition duration-200',
              isActive
                ? cx('text-zinc-950', !pill.box && 'bg-zinc-100')
                : 'text-zinc-600 hover:text-zinc-950'
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
    <div className={cx('flex min-h-52 animate-fade-in flex-col items-center justify-center rounded-2xl border border-dashed border-zinc-200 bg-zinc-50 px-6 py-10 text-center', className)}>
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

// O CheckCircle2 do lucide, com o traco do check desenhado ao aparecer.
function DrawnCheck({ className = '' }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <path d="m9 12 2 2 4-4" pathLength="1" strokeDasharray="1" className="animate-check-draw" />
    </svg>
  )
}

const alertTones = {
  danger: { classes: 'border-rose-200 bg-rose-50 text-rose-700', icon: AlertTriangle },
  warning: { classes: 'border-amber-200 bg-amber-50 text-amber-800', icon: AlertTriangle },
  success: { classes: 'border-emerald-200 bg-emerald-50 text-emerald-700', icon: DrawnCheck },
  info: { classes: 'border-sky-200 bg-sky-50 text-sky-700', icon: Info },
}

// O unico banner de aviso/erro do app. `message` ou `children`; nada = nao renderiza.
export function AlertMessage({ tone = 'danger', message, children, onDismiss, className = '' }) {
  const content = children ?? message
  if (!content) return null
  const { classes, icon: Icon } = alertTones[tone] || alertTones.danger
  return (
    <div role={tone === 'danger' ? 'alert' : 'status'} className={cx('flex animate-slide-down items-start gap-3 rounded-2xl border px-4 py-3 text-sm font-medium', classes, className)}>
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

// O fundo branco do item ativo como uma pilula so, que desliza de um item
// para o outro. Mede o elemento que casa com `activeSelector` dentro do
// conteiner; `deps` e o que muda o ativo (rota, valor).
function useSlidingPill(containerRef, activeSelector, deps) {
  const [box, setBox] = useState(null)
  const [ready, setReady] = useState(false)

  useLayoutEffect(() => {
    const container = containerRef.current
    if (!container) return undefined
    const measure = () => {
      const active = container.querySelector(activeSelector)
      setBox(active ? { left: active.offsetLeft, width: active.offsetWidth } : null)
    }
    measure()
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null
    observer?.observe(container)
    return () => observer?.disconnect()
  }, [containerRef, activeSelector, ...deps])

  // A transicao so liga depois da primeira medida: a pilula nao entra
  // deslizando da borda esquerda.
  useEffect(() => {
    if (!box || ready) return undefined
    const frame = requestAnimationFrame(() => setReady(true))
    return () => cancelAnimationFrame(frame)
  }, [box, ready])

  return { box, ready }
}

function PillBackground({ pill }) {
  if (!pill.box) return null
  return (
    <span
      aria-hidden="true"
      className={cx(
        'absolute bottom-1 left-0 top-1 rounded-full bg-zinc-100',
        pill.ready && 'transition-[transform,width] duration-200 ease-out-quint'
      )}
      style={{ width: pill.box.width, transform: `translateX(${pill.box.left}px)` }}
    />
  )
}

// Abas ligadas a rota: cada item e um link, o ativo e o da URL atual.
// O Layout nao remonta as abas ao trocar de rota, entao a pilula desliza.
export function Tabs({ items, className = '' }) {
  const navRef = useRef(null)
  const { pathname } = useLocation()
  const pill = useSlidingPill(navRef, '[aria-current="page"]', [pathname, items])

  return (
    <nav ref={navRef} className={cx('relative inline-flex max-w-full gap-1 overflow-x-auto rounded-full border border-zinc-200 bg-white p-1', className)}>
      <PillBackground pill={pill} />
      {items.map((item) => {
        const Icon = item.icon
        return (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) => cx(
              'relative inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-full px-4 text-sm font-semibold transition duration-200 lg:h-9',
              isActive
                ? cx('text-zinc-950', !pill.box && 'bg-zinc-100')
                : 'text-zinc-600 hover:text-zinc-950'
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
      <Expand open={open} id={contentId} innerClassName="pt-4">
        {children}
      </Expand>
    </div>
  )
}

// Abre e fecha na altura real do conteudo: grid-template-rows 0fr -> 1fr
// transiciona ate "auto", o que `height` nao faz. Fechado, desmonta (como
// sempre foi) — so que depois da animacao de saida.
export function Expand({ open, id, className = '', innerClassName = '', children }) {
  const { mounted, closing } = usePresence(open, 220)
  const [expanded, setExpanded] = useState(false)
  const [settled, setSettled] = useState(false)

  useEffect(() => {
    setSettled(false)
    if (!open) {
      setExpanded(false)
      return undefined
    }
    // Dois frames: o 0fr precisa ser pintado antes, senao nao ha transicao.
    let inner = null
    const outer = requestAnimationFrame(() => {
      inner = requestAnimationFrame(() => setExpanded(true))
    })
    return () => {
      cancelAnimationFrame(outer)
      cancelAnimationFrame(inner)
    }
  }, [open])

  if (!mounted) return null
  const isOpen = expanded && !closing

  return (
    <div
      id={id}
      // minmax(0, 1fr): sem isso a coluna cresce ate o conteudo e um texto
      // com truncate/nowrap la dentro vaza para fora da tela.
      className={cx('grid grid-cols-[minmax(0,1fr)] transition-[grid-template-rows] duration-200 ease-out-quint', className)}
      style={{ gridTemplateRows: isOpen ? '1fr' : '0fr' }}
      onTransitionEnd={(event) => {
        if (event.target === event.currentTarget && event.propertyName === 'grid-template-rows') {
          setSettled(isOpen)
        }
      }}
    >
      {/* Aberto e parado, o overflow volta a visible: o anel de foco dos campos nao e cortado. */}
      <div className={cx('min-h-0', settled ? 'overflow-visible' : 'overflow-hidden')}>
        <div className={innerClassName}>{children}</div>
      </div>
    </div>
  )
}

// Modal no desktop, folha que sobe de baixo no celular. Esc e clique fora fecham.
// Vai para document.body via portal: o wrapper animado do Layout tem transform,
// o que faria `fixed` se medir pela pagina e nao pela janela.
export function Sheet({ open, onClose, title, description, children, footer, className = '' }) {
  const { mounted, closing } = usePresence(open, 200)
  // Na saida, mostra o ultimo conteudo aberto: quem chama costuma zerar o
  // estado junto com o `open` (ex.: `paying` vira null), e o sheet piscaria
  // "Pagar R$ 0,00" enquanto some.
  const lastOpenRef = useRef(null)
  if (open) lastOpenRef.current = { title, description, children, footer }
  const shown = open ? { title, description, children, footer } : lastOpenRef.current || {}

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

  if (!mounted) return null

  return createPortal(
    <div
      className={cx('fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-4', closing && 'pointer-events-none')}
      role="dialog"
      aria-modal="true"
      aria-label={typeof shown.title === 'string' ? shown.title : undefined}
    >
      <div className={cx('absolute inset-0 bg-zinc-950/40 backdrop-blur-sm', closing ? 'animate-fade-out' : 'animate-fade-in')} onClick={onClose} />
      <div
        className={cx(
          'relative flex max-h-[92vh] w-full flex-col overflow-hidden rounded-t-[1.75rem] bg-white shadow-lift',
          'sm:max-w-xl sm:rounded-[1.75rem]',
          closing ? 'animate-slide-out-down sm:animate-scale-out' : 'animate-fade-up sm:animate-scale-in',
          className
        )}
      >
        <div className="mx-auto mt-2 h-1.5 w-10 rounded-full bg-zinc-200 sm:hidden" />
        <div className="flex items-start justify-between gap-4 border-b border-zinc-100 px-5 py-4">
          <div className="min-w-0">
            {shown.title ? <h2 className="text-lg font-extrabold tracking-tight text-zinc-950">{shown.title}</h2> : null}
            {shown.description ? <p className="mt-1 text-sm text-zinc-600">{shown.description}</p> : null}
          </div>
          <IconButton label="Fechar" icon={X} variant="subtle" onClick={onClose} />
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{shown.children}</div>
        {shown.footer ? <div className="border-t border-zinc-100 px-5 py-4 pb-[max(1rem,env(safe-area-inset-bottom))]">{shown.footer}</div> : null}
      </div>
    </div>,
    document.body
  )
}
