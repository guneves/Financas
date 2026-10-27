import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { BellRing, CloudOff, Eye, EyeOff, LogOut, Plus, Settings, UploadCloud } from 'lucide-react'
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch } from '../lib/api'
import { displayName, getCurrentUser, signOut } from '../lib/auth'
import { useServerReachable } from '../lib/connection'
import { REVIEW_PATH } from '../lib/review'
import { useReviewQueue } from '../lib/reviewQueue'
import { findSection, sections, SETTINGS_PATH } from '../lib/navigation'
import { DataVersionContext, NewEntryContext } from '../lib/newEntry'
import { useOutbox } from '../lib/outbox'
import { NEEDS_ATTENTION } from '../lib/outboxRules'
import { setValuesHidden, useValuesHidden } from '../lib/privacy'
import { useLayer } from '../lib/layers'
import { useScrollRestoration } from '../lib/scroll'
import { AttentionBell } from './Attention'
import InvestmentLaunchModal from './InvestmentLaunchModal'
import NewEntrySheet from './NewEntrySheet'
import PendingSheet from './PendingSheet'
import { ConfirmHost, cx, Skeleton, Tabs, Toaster } from './ui'

const NEW_ENTRY_TYPE_VALUES = ['EXPENSE', 'INCOME', 'TRANSFER', 'CARD']
// Secao em que o "+ Novo" registra uma operacao em vez de um lancamento.
const INVESTMENTS_PATH = '/investimentos'

export function BrandMark({ compact = false }) {
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand text-base font-extrabold text-brand-ink">
        F
      </div>
      {compact ? null : <span className="text-lg font-extrabold tracking-tight text-zinc-950">Finanças</span>}
    </div>
  )
}

// Navegacao de secoes no desktop: pilulas numa faixa branca; a ativa e o
// verde profundo da marca.
function SectionPill({ to, name, icon: Icon }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cx(
          'flex h-10 items-center gap-2 rounded-full px-4 text-sm font-semibold transition duration-150',
          isActive ? 'bg-brand text-brand-ink' : 'text-zinc-600 hover:bg-zinc-100 hover:text-zinc-950'
        )
      }
    >
      <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
      <span>{name}</span>
    </NavLink>
  )
}

const roundButton = 'inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border transition'
const roundIdle = 'border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-100 hover:text-zinc-950'
const roundOn = 'border-emerald-200 bg-emerald-50 text-emerald-700'

// Olho: esconde saldos e carteira (lib/privacy.js).
function PrivacyToggle({ hidden, onToggle }) {
  const label = hidden ? 'Mostrar valores' : 'Ocultar valores'
  const Icon = hidden ? EyeOff : Eye
  return (
    <button type="button" onClick={onToggle} aria-label={label} aria-pressed={hidden} title={label} className={cx(roundButton, hidden ? roundOn : roundIdle)}>
      <Icon className="h-5 w-5" />
    </button>
  )
}

// Menu do usuario: Ajustes e Sair. Fecha com Esc, clique fora ou ao navegar.
function UserMenu({ initials, name }) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)
  const buttonRef = useRef(null)
  const location = useLocation()

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

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Conta de ${name}`}
        title={name}
        className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-emerald-100 text-sm font-bold text-emerald-800 transition hover:ring-2 hover:ring-emerald-200"
      >
        {initials || 'F'}
      </button>
      {open ? (
        <div role="menu" className="absolute right-0 top-full z-40 mt-2 w-56 animate-slide-down rounded-2xl border border-zinc-200 bg-white p-1.5 shadow-lift">
          <p className="truncate px-3 py-2 text-sm font-semibold text-zinc-950">{name}</p>
          <NavLink role="menuitem" to={SETTINGS_PATH} className="flex h-10 items-center gap-3 rounded-xl px-3 text-sm font-medium text-zinc-700 hover:bg-zinc-100 hover:text-zinc-950">
            <Settings className="h-4 w-4" />
            Ajustes
          </NavLink>
          <button role="menuitem" type="button" onClick={signOut} className="flex h-10 w-full items-center gap-3 rounded-xl px-3 text-sm font-medium text-zinc-700 hover:bg-rose-50 hover:text-rose-700">
            <LogOut className="h-4 w-4" />
            Sair
          </button>
        </div>
      ) : null}
    </div>
  )
}

// Aparece so quando ha o que dizer: lancamentos guardados no aparelho a
// espera do servidor, ou o servidor sem responder. Abre "Pendentes". Ambar e
// aviso (recusado, sem conexao); a fila andando normalmente e neutra.
function PendingPill({ count, attention, reachable, onClick, compact = false }) {
  if (!count && reachable) return null
  const warn = attention > 0 || !reachable
  const Icon = reachable ? UploadCloud : CloudOff
  const label = count
    ? `${count} ${count === 1 ? 'pendente' : 'pendentes'}`
    : 'Sem conexão'
  const title = reachable
    ? 'Lançamentos guardados neste aparelho, à espera do servidor'
    : 'Sem conexão com o servidor: só novos lançamentos são guardados'
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-label={`${label}. ${title}`}
      className={cx(
        'inline-flex h-11 shrink-0 items-center gap-2 rounded-full border px-4 text-sm font-semibold transition',
        warn ? 'border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100' : roundIdle
      )}
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
      <span className={compact && !count ? 'sr-only' : undefined}>{label}</span>
    </button>
  )
}

// O que o celular e o banco gravaram sozinhos esperando o dono confirmar
// (045, o painel Revisar do Extrato). Ambar: e algo a fazer. Some sem nada.
function ReviewPill({ count, compact = false }) {
  if (!count) return null
  const label = `${count} para revisar`
  return (
    <NavLink
      to={REVIEW_PATH}
      title="Lançamentos gravados sozinhos esperando você confirmar"
      aria-label={label}
      className="inline-flex h-11 shrink-0 items-center gap-2 rounded-full border border-amber-200 bg-amber-50 px-4 text-sm font-semibold text-amber-800 transition hover:bg-amber-100"
    >
      <BellRing className="h-4 w-4" aria-hidden="true" />
      <span>{compact ? count : label}</span>
    </NavLink>
  )
}

function BottomTab({ to, name, icon: Icon }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cx(
          'flex min-h-[52px] min-w-0 flex-col items-center justify-center gap-0.5 text-[11px] font-semibold tracking-tight transition',
          isActive ? 'text-zinc-950' : 'text-zinc-500 hover:text-zinc-900'
        )
      }
    >
      {({ isActive }) => (
        <>
          <span className={cx('flex h-7 w-12 items-center justify-center rounded-full transition', isActive && 'bg-emerald-100 text-emerald-800')}>
            <Icon className="h-5 w-5" />
          </span>
          <span className="max-w-full truncate">{name}</span>
        </>
      )}
    </NavLink>
  )
}

export default function Layout() {
  const location = useLocation()
  const user = getCurrentUser()
  const section = useMemo(() => findSection(location.pathname), [location.pathname])

  // Entrada da pagina: fade-up ao mudar de secao; entre abas da mesma secao
  // (troca frequente, as abas ficam paradas) so fade-in, sem deslocamento.
  const pageEnter = useRef({ pathname: location.pathname, sectionPath: section?.path, className: 'animate-fade-up' })
  if (pageEnter.current.pathname !== location.pathname) {
    const sameSection = Boolean(section) && pageEnter.current.sectionPath === section.path
    pageEnter.current = {
      pathname: location.pathname,
      sectionPath: section?.path,
      className: sameSection ? 'animate-fade-in' : 'animate-fade-up',
    }
  }

  // Tela nova comeca do topo; voltar/avancar devolve a rolagem (lib/scroll.js).
  useScrollRestoration()

  // "+ Novo": o sheet e o modal de investimento moram aqui, fora das paginas.
  // O sheet e so da area bancaria (despesa, receita, transferencia, cartao);
  // dentro de Investimentos o mesmo botao abre "Registrar operacao". A gravacao
  // invalida o cache de dados (lib/queries.js, pelo apiFetch); dataVersion so
  // conta as gravacoes do "+ Novo", para o Extrato piscar a linha nova
  // (useArrivals).
  const inInvestments = section?.path === INVESTMENTS_PATH
  const [dataVersion, setDataVersion] = useState(0)
  const [sheetOpen, setSheetOpen] = useState(false)
  const [sheetType, setSheetType] = useState('EXPENSE')
  const [investmentOpen, setInvestmentOpen] = useState(false)
  const [investmentAssets, setInvestmentAssets] = useState([])
  const valuesHidden = useValuesHidden()

  const toggleValuesHidden = useCallback(() => {
    setValuesHidden(!valuesHidden)
  }, [valuesHidden])

  const bumpDataVersion = useCallback(() => {
    setDataVersion((version) => version + 1)
  }, [])

  const openInvestment = useCallback(() => {
    setInvestmentOpen(true)
    // Mesma carga da tela de investimentos: o modal precisa dos ativos da carteira.
    apiFetch('/api/investments/portfolio?refresh_prices=false')
      .then((data) => setInvestmentAssets(data?.assets || []))
      .catch((error) => console.warn('Erro ao buscar ativos:', error))
  }, [])

  // O sheet do "+ Novo".
  const openEntrySheet = useCallback((type, item = null) => {
    setEditingPending(item)
    setSheetType(NEW_ENTRY_TYPE_VALUES.includes(type) ? type : 'EXPENSE')
    setSheetOpen(true)
  }, [])

  // Sem tipo, o botao segue a area em que se esta. Com tipo
  // (`openNewEntry('CARD')`) e sempre o sheet bancario.
  const openNewEntry = useCallback((type) => {
    if (!type && inInvestments) {
      openInvestment()
      return
    }
    openEntrySheet(type)
  }, [inInvestments, openInvestment, openEntrySheet])

  const closeSheet = useCallback(() => {
    setSheetOpen(false)
    setEditingPending(null)
  }, [])

  // "Pendentes": a fila de envio (lib/outbox.js). Corrigir um item reabre o
  // sheet do "+ Novo" preenchido com ele.
  const pending = useOutbox()
  const reachable = useServerReachable()
  const pendingAttention = useMemo(() => pending.filter((item) => item.status === NEEDS_ATTENTION).length, [pending])
  const [pendingOpen, setPendingOpen] = useState(false)
  const [editingPending, setEditingPending] = useState(null)
  const openPending = useCallback(() => setPendingOpen(true), [])
  const closePending = useCallback(() => setPendingOpen(false), [])
  const editPending = useCallback((item) => {
    setPendingOpen(false)
    openEntrySheet(item.kind, item)
  }, [openEntrySheet])

  const closeInvestment = useCallback(() => setInvestmentOpen(false), [])

  const newEntryValue = useMemo(() => ({ openNewEntry }), [openNewEntry])
  const reviewCount = useReviewQueue().count
  const tabCounts = useMemo(() => ({ review: reviewCount }), [reviewCount])

  const name = displayName(user)
  const initials = name
    .split(/[\s.\-_]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase()

  return (
    <NewEntryContext.Provider value={newEntryValue}>
      <DataVersionContext.Provider value={dataVersion}>
      <div className="min-h-screen text-zinc-950">
        {/* Desktop: uma faixa so, fixa no topo — marca, secoes, e a direita
            sino, olho, conta e "+ Novo". A altura (h-[4.5rem]) e o top do
            cabecalho das tabelas em index.css. Entre 1024 e ~1110 px a faixa
            nao cabe com a marca em w-44 e folga larga: "+ Novo" saia da tela. */}
        <header className="sticky top-0 z-30 hidden border-b border-zinc-200/70 bg-zinc-50/90 backdrop-blur lg:block">
          <div className="mx-auto flex h-[4.5rem] w-full max-w-[1500px] items-center gap-3 px-6 xl:gap-4 xl:px-8">
            <div className="shrink-0 xl:w-44">
              <BrandMark />
            </div>
            <nav aria-label="Seções" className="flex items-center gap-1 rounded-full border border-zinc-200 bg-white p-1">
              {sections.map((item) => (
                <SectionPill key={item.path} to={item.path} name={item.name} icon={item.icon} />
              ))}
            </nav>
            <div className="flex-1" />
            <ReviewPill count={reviewCount} />
            <PendingPill count={pending.length} attention={pendingAttention} reachable={reachable} onClick={openPending} />
            <AttentionBell />
            <PrivacyToggle hidden={valuesHidden} onToggle={toggleValuesHidden} />
            <UserMenu initials={initials} name={name} />
            <button
              type="button"
              onClick={() => openNewEntry()}
              title={inInvestments ? 'Registrar operação' : 'Novo lançamento'}
              className="inline-flex h-11 items-center gap-2 rounded-full bg-emerald-500 px-5 text-sm font-bold text-on-accent transition hover:bg-emerald-400 active:scale-[0.97]"
            >
              <Plus className="h-5 w-5" strokeWidth={2.4} />
              Novo
            </button>
          </div>
        </header>

        <header className="sticky top-0 z-20 border-b border-zinc-200/70 bg-zinc-50/95 backdrop-blur lg:hidden">
          <div className="flex h-16 items-center justify-between gap-2 px-4">
            <BrandMark />
            <div className="flex items-center gap-2">
              <ReviewPill count={reviewCount} compact />
              <PendingPill count={pending.length} attention={pendingAttention} reachable={reachable} onClick={openPending} compact />
              <AttentionBell />
              <PrivacyToggle hidden={valuesHidden} onToggle={toggleValuesHidden} />
              <NavLink
                to={SETTINGS_PATH}
                aria-label="Ajustes"
                title="Ajustes"
                className={({ isActive }) => cx(roundButton, isActive ? roundOn : roundIdle)}
              >
                <Settings className="h-5 w-5" />
              </NavLink>
            </div>
          </div>
        </header>

        <main className="mx-auto min-h-screen w-full max-w-[1500px] px-4 pb-28 pt-6 sm:px-6 lg:py-8 xl:px-8">
          {section?.tabs.length ? (
            <Tabs items={section.tabs} counts={tabCounts} className="mb-5" />
          ) : null}

          {/* Trocar de pagina remonta e anima a entrada. O modo privado e o
              tema nao remontam nada: so o que depende deles re-renderiza
              (lib/privacy.js, lib/theme.js). */}
          <div key={location.pathname} className={pageEnter.current.className}>
            <Suspense fallback={<PageLoading />}>
              <Outlet />
            </Suspense>
          </div>
        </main>

        <nav aria-label="Seções" className="fixed inset-x-0 bottom-0 z-30 border-t border-zinc-200 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden">
          {/* Cinco colunas iguais: o "+" fica no meio exato, qualquer que seja
              o tamanho dos nomes ao lado. */}
          <div className="mx-auto grid max-w-lg grid-cols-5 items-stretch py-1">
            {sections.slice(0, 2).map((item) => (
              <BottomTab key={item.path} to={item.path} name={item.shortName || item.name} icon={item.icon} />
            ))}
            <div className="flex items-center justify-center">
              <button
                type="button"
                onClick={() => openNewEntry()}
                aria-label={inInvestments ? 'Registrar operação' : 'Novo lançamento'}
                className="flex h-[3.25rem] w-[3.25rem] items-center justify-center rounded-2xl bg-emerald-500 text-on-accent transition active:scale-95"
              >
                <Plus className="h-6 w-6" strokeWidth={2.4} />
              </button>
            </div>
            {sections.slice(2).map((item) => (
              <BottomTab key={item.path} to={item.path} name={item.shortName || item.name} icon={item.icon} />
            ))}
          </div>
        </nav>
      </div>

      <NewEntrySheet
        open={sheetOpen}
        initialType={sheetType}
        editingItem={editingPending}
        onClose={closeSheet}
        onSaved={bumpDataVersion}
      />
      <PendingSheet open={pendingOpen} onClose={closePending} onEdit={editPending} />
      <InvestmentLaunchModal
        open={investmentOpen}
        onClose={closeInvestment}
        assets={investmentAssets}
        onSaved={bumpDataVersion}
      />
      <Toaster />
      <ConfirmHost />
      </DataVersionContext.Provider>
    </NewEntryContext.Provider>
  )
}

// Enquanto o chunk da tela carrega (primeira visita a cada tela).
function PageLoading() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Carregando">
      <Skeleton className="h-10 w-56" />
      <Skeleton className="h-32 w-full" />
      <Skeleton className="h-64 w-full" />
    </div>
  )
}
