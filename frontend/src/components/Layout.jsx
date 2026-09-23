import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { Eye, EyeOff, LogOut, Moon, Plus, Settings, Sun } from 'lucide-react'
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch } from '../lib/api'
import { displayName, getCurrentUser, signOut } from '../lib/auth'
import { findSection, sections, SETTINGS_PATH } from '../lib/navigation'
import { DataVersionContext, NewEntryContext } from '../lib/newEntry'
import { setValuesHidden, useValuesHidden } from '../lib/privacy'
import { toggleTheme, useIsDark } from '../lib/theme'
import InvestmentLaunchModal from './InvestmentLaunchModal'
import NewEntrySheet from './NewEntrySheet'
import { cx, Skeleton, Tabs, Toaster } from './ui'

const NEW_ENTRY_TYPE_VALUES = ['EXPENSE', 'INCOME', 'TRANSFER', 'CARD', 'INVESTMENT']

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

// Claro/escuro (lib/theme.js). Segue o sistema ate o primeiro clique.
function ThemeToggle() {
  const dark = useIsDark()
  const label = dark ? 'Usar tema claro' : 'Usar tema escuro'
  const Icon = dark ? Sun : Moon
  return (
    <button type="button" onClick={toggleTheme} aria-label={label} title={label} className={cx(roundButton, roundIdle)}>
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
    const onKey = (event) => {
      if (event.key === 'Escape') {
        setOpen(false)
        buttonRef.current?.focus()
      }
    }
    document.addEventListener('pointerdown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

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

function BottomTab({ to, name, icon: Icon }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cx(
          'flex min-h-[52px] flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-semibold transition',
          isActive ? 'text-zinc-950' : 'text-zinc-500 hover:text-zinc-900'
        )
      }
    >
      {({ isActive }) => (
        <>
          <span className={cx('flex h-7 w-12 items-center justify-center rounded-full transition', isActive && 'bg-emerald-100 text-emerald-800')}>
            <Icon className="h-5 w-5" />
          </span>
          <span className="max-w-full truncate px-1">{name}</span>
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

  // "+ Novo" (docs/ux-reorganization.md D5): o sheet e o modal de investimento
  // moram aqui, fora das paginas. Cada gravacao bem-sucedida incrementa
  // dataVersion, e as paginas montadas recarregam (useDataVersion()).
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
    setSheetOpen(false)
    setInvestmentOpen(true)
    // Mesma carga da tela de investimentos: o modal precisa dos ativos da carteira.
    apiFetch('/api/investments/portfolio?refresh_prices=false')
      .then((data) => setInvestmentAssets(data?.assets || []))
      .catch((error) => console.warn('Erro ao buscar ativos:', error))
  }, [])

  const openNewEntry = useCallback((type) => {
    const nextType = NEW_ENTRY_TYPE_VALUES.includes(type) ? type : 'EXPENSE'
    if (nextType === 'INVESTMENT') {
      openInvestment()
      return
    }
    setSheetType(nextType)
    setSheetOpen(true)
  }, [openInvestment])

  const closeSheet = useCallback(() => setSheetOpen(false), [])
  const closeInvestment = useCallback(() => setInvestmentOpen(false), [])

  const newEntryValue = useMemo(() => ({ openNewEntry }), [openNewEntry])

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
            tema, olho, conta e "+ Novo". A altura (h-[4.5rem]) e o top do
            cabecalho das tabelas em index.css. */}
        <header className="sticky top-0 z-30 hidden border-b border-zinc-200/70 bg-zinc-50/90 backdrop-blur lg:block">
          <div className="mx-auto flex h-[4.5rem] w-full max-w-[1500px] items-center gap-4 px-8">
            <div className="w-44 shrink-0">
              <BrandMark />
            </div>
            <nav aria-label="Seções" className="flex items-center gap-1 rounded-full border border-zinc-200 bg-white p-1">
              {sections.map((item) => (
                <SectionPill key={item.path} to={item.path} name={item.name} icon={item.icon} />
              ))}
            </nav>
            <div className="flex-1" />
            <ThemeToggle />
            <PrivacyToggle hidden={valuesHidden} onToggle={toggleValuesHidden} />
            <UserMenu initials={initials} name={name} />
            <button
              type="button"
              onClick={() => openNewEntry()}
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
              <ThemeToggle />
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

        <main className="mx-auto min-h-screen w-full max-w-[1500px] px-4 pb-28 pt-6 sm:px-6 lg:px-8 lg:py-8">
          {section?.tabs.length ? (
            <Tabs items={section.tabs} className="mb-5" />
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
          <div className="mx-auto flex max-w-lg items-stretch px-2 py-1">
            {sections.slice(0, 2).map((item) => (
              <BottomTab key={item.path} to={item.path} name={item.name} icon={item.icon} />
            ))}
            <div className="flex flex-1 items-center justify-center">
              <button
                type="button"
                onClick={() => openNewEntry()}
                aria-label="Novo lançamento"
                className="flex h-[3.25rem] w-[3.25rem] items-center justify-center rounded-2xl bg-emerald-500 text-on-accent transition active:scale-95"
              >
                <Plus className="h-6 w-6" strokeWidth={2.4} />
              </button>
            </div>
            {sections.slice(2).map((item) => (
              <BottomTab key={item.path} to={item.path} name={item.name} icon={item.icon} />
            ))}
          </div>
        </nav>
      </div>

      <NewEntrySheet
        open={sheetOpen}
        initialType={sheetType}
        onClose={closeSheet}
        onSaved={bumpDataVersion}
        onPickInvestment={openInvestment}
      />
      <InvestmentLaunchModal
        open={investmentOpen}
        onClose={closeInvestment}
        assets={investmentAssets}
        onSaved={bumpDataVersion}
      />
      <Toaster />
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
