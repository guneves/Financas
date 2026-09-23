import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { Eye, EyeOff, LogOut, Plus, Settings, Wallet } from 'lucide-react'
import { Suspense, useCallback, useMemo, useRef, useState } from 'react'
import { apiFetch } from '../lib/api'
import { displayName, getCurrentUser, signOut } from '../lib/auth'
import { findSection, sections, SETTINGS_PATH } from '../lib/navigation'
import { DataVersionContext, NewEntryContext } from '../lib/newEntry'
import { setValuesHidden, useValuesHidden } from '../lib/privacy'
import InvestmentLaunchModal from './InvestmentLaunchModal'
import NewEntrySheet from './NewEntrySheet'
import { Button, cx, Skeleton, Tabs } from './ui'

const NEW_ENTRY_TYPE_VALUES = ['EXPENSE', 'INCOME', 'TRANSFER', 'CARD', 'INVESTMENT']

function BrandMark() {
  return (
    <div className="flex items-center gap-3">
      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-500 to-teal-700 text-white shadow-glow">
        <Wallet className="h-5 w-5" />
      </div>
      <div>
        <p className="text-sm font-bold leading-5 text-zinc-950">FinanceMVP</p>
        <p className="text-xs text-zinc-600">Painel financeiro</p>
      </div>
    </div>
  )
}

function SidebarItem({ to, name, icon: Icon }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cx(
          'group relative flex h-11 items-center gap-3 rounded-lg px-3 text-sm font-semibold transition duration-200',
          isActive
            ? 'bg-zinc-950 text-white shadow-lift'
            : 'text-zinc-600 hover:translate-x-0.5 hover:bg-zinc-100 hover:text-zinc-950'
        )
      }
    >
      {({ isActive }) => (
        <>
          <span
            className={cx(
              'absolute left-0 top-2.5 h-6 w-1 -translate-x-2 rounded-r-full bg-emerald-400 transition-all duration-300',
              isActive ? 'opacity-100' : 'opacity-0'
            )}
          />
          <Icon className={cx('h-4 w-4 shrink-0 transition-colors', isActive ? 'text-emerald-300' : 'text-zinc-500 group-hover:text-zinc-700')} />
          <span className="truncate">{name}</span>
        </>
      )}
    </NavLink>
  )
}

// Olho da barra lateral (e do cabecalho no celular): esconde saldos e carteira.
function PrivacyToggle({ hidden, onToggle, className = '' }) {
  const label = hidden ? 'Mostrar valores' : 'Ocultar valores'
  const Icon = hidden ? EyeOff : Eye
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={label}
      aria-pressed={hidden}
      title={label}
      className={cx(
        'inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border transition',
        hidden ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-zinc-300 bg-white text-zinc-700 hover:bg-zinc-50',
        className
      )}
    >
      <Icon className="h-5 w-5" />
    </button>
  )
}

function BottomTab({ to, name, icon: Icon }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cx(
          'flex min-h-[52px] flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-semibold transition',
          isActive ? 'text-emerald-700' : 'text-zinc-500 hover:text-zinc-900'
        )
      }
    >
      <Icon className="h-5 w-5" />
      <span className="max-w-full truncate px-1">{name}</span>
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
        <aside className="fixed inset-y-0 left-0 z-30 hidden w-72 border-r border-zinc-200/80 bg-white/90 backdrop-blur lg:flex lg:flex-col">
          <div className="border-b border-zinc-100 px-5 py-5">
            <BrandMark />
          </div>

          <div className="px-4 pt-5">
            <Button icon={Plus} size="lg" className="w-full" onClick={() => openNewEntry()}>
              Novo
            </Button>
          </div>

          <nav className="stagger flex-1 space-y-1 px-4 py-5">
            {sections.map((item) => (
              <SidebarItem key={item.path} to={item.path} name={item.name} icon={item.icon} />
            ))}
          </nav>

          <div className="space-y-1 border-t border-zinc-100 p-4">
            <SidebarItem to={SETTINGS_PATH} name="Ajustes" icon={Settings} />
            <div className="my-2 flex items-center gap-3 rounded-lg bg-zinc-50 p-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-100 text-sm font-bold text-emerald-700">
                {initials || 'FM'}
              </div>
              <p className="min-w-0 flex-1 truncate text-sm font-semibold text-zinc-900">
                {name}
              </p>
              <PrivacyToggle hidden={valuesHidden} onToggle={toggleValuesHidden} className="h-9 w-9" />
            </div>
            <button
              onClick={signOut}
              className="flex h-11 w-full items-center gap-3 rounded-lg px-3 text-sm font-semibold text-zinc-600 transition hover:bg-rose-50 hover:text-rose-700"
            >
              <LogOut className="h-4 w-4" />
              Sair
            </button>
          </div>
        </aside>

        <header className="sticky top-0 z-20 border-b border-zinc-200 bg-white/95 backdrop-blur lg:hidden">
          <div className="flex h-16 items-center justify-between px-4">
            <BrandMark />
            <div className="flex items-center gap-2">
              <PrivacyToggle hidden={valuesHidden} onToggle={toggleValuesHidden} />
              <NavLink
                to={SETTINGS_PATH}
                aria-label="Ajustes"
                title="Ajustes"
                className={({ isActive }) => cx(
                  'inline-flex h-11 w-11 items-center justify-center rounded-lg border transition',
                  isActive ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-zinc-300 bg-white text-zinc-700 hover:bg-zinc-50'
                )}
              >
                <Settings className="h-5 w-5" />
              </NavLink>
            </div>
          </div>
        </header>

        <div className="lg:pl-72">
          <main className="mx-auto min-h-screen w-full max-w-[1500px] px-4 pb-28 pt-6 sm:px-6 lg:px-8 lg:py-8">
            {section?.tabs.length ? (
              <Tabs items={section.tabs} className="mb-5" />
            ) : null}

            {/* Trocar de pagina remonta e anima a entrada. O modo privado nao
                remonta nada: so os valores sensiveis re-renderizam
                (lib/privacy.js). */}
            <div key={location.pathname} className={pageEnter.current.className}>
              <Suspense fallback={<PageLoading />}>
                <Outlet />
              </Suspense>
            </div>
          </main>
        </div>

        <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-zinc-200 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden">
          <div className="mx-auto flex max-w-lg items-stretch px-2">
            {sections.slice(0, 2).map((item) => (
              <BottomTab key={item.path} to={item.path} name={item.name} icon={item.icon} />
            ))}
            <div className="flex flex-1 items-center justify-center">
              <button
                type="button"
                onClick={() => openNewEntry()}
                aria-label="Novo lançamento"
                className="-mt-5 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-600 text-white shadow-glow ring-4 ring-white transition active:scale-95"
              >
                <Plus className="h-6 w-6" />
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
