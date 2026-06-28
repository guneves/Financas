import { NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  Briefcase,
  LayoutDashboard,
  LogOut,
  Menu,
  PieChart,
  Receipt,
  Wallet,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { getCurrentUser, signOut } from '../lib/auth'
import { cx, IconButton } from './ui'

const navItems = [
  { name: 'Visão geral', path: '/dashboard', icon: LayoutDashboard },
  { name: 'Movimentações', path: '/transactions', icon: Receipt },
  { name: 'Carteira', path: '/carteira', icon: PieChart },
  { name: 'Investimentos', path: '/investments', icon: Briefcase },
]

function BrandMark() {
  return (
    <div className="flex items-center gap-3">
      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-zinc-950 text-white">
        <Wallet className="h-5 w-5" />
      </div>
      <div>
        <p className="text-sm font-bold leading-5 text-zinc-950">FinanceMVP</p>
        <p className="text-xs text-zinc-500">Painel financeiro</p>
      </div>
    </div>
  )
}

function NavItem({ item, onClick }) {
  const Icon = item.icon

  return (
    <NavLink
      to={item.path}
      onClick={onClick}
      className={({ isActive }) =>
        cx(
          'flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-semibold transition',
          isActive
            ? 'bg-zinc-950 text-white shadow-sm'
            : 'text-zinc-600 hover:bg-zinc-100 hover:text-zinc-950'
        )
      }
    >
      <Icon className="h-4 w-4 shrink-0" />
      <span className="truncate">{item.name}</span>
    </NavLink>
  )
}

export default function Layout() {
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)
  const user = getCurrentUser()

  const activePage = useMemo(() => {
    return navItems.find((item) => item.path === location.pathname) || navItems[0]
  }, [location.pathname])

  const initials = (user?.email || 'FM')
    .split('@')[0]
    .split(/[.\-_]/)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase()

  const handleLogout = () => {
    signOut()
  }

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-950">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-72 border-r border-zinc-200 bg-white lg:flex lg:flex-col">
        <div className="border-b border-zinc-100 px-5 py-5">
          <BrandMark />
        </div>

        <nav className="flex-1 space-y-1 px-4 py-5">
          {navItems.map((item) => (
            <NavItem key={item.path} item={item} />
          ))}
        </nav>

        <div className="border-t border-zinc-100 p-4">
          <div className="mb-3 flex items-center gap-3 rounded-lg bg-zinc-50 p-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-100 text-sm font-bold text-emerald-700">
              {initials || 'FM'}
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-zinc-900">{user?.email || 'Usuário'}</p>
              <p className="text-xs text-zinc-500">Sessão ativa</p>
            </div>
          </div>

          <button
            onClick={handleLogout}
            className="flex h-10 w-full items-center gap-3 rounded-lg px-3 text-sm font-semibold text-zinc-600 transition hover:bg-rose-50 hover:text-rose-700"
          >
            <LogOut className="h-4 w-4" />
            Sair
          </button>
        </div>
      </aside>

      <header className="sticky top-0 z-20 border-b border-zinc-200 bg-white/95 backdrop-blur lg:hidden">
        <div className="flex h-16 items-center justify-between px-4">
          <BrandMark />
          <IconButton
            label="Abrir menu"
            icon={Menu}
            variant="secondary"
            onClick={() => setMobileOpen((current) => !current)}
          />
        </div>

        {mobileOpen ? (
          <nav className="space-y-1 border-t border-zinc-100 px-4 py-3">
            {navItems.map((item) => (
              <NavItem key={item.path} item={item} onClick={() => setMobileOpen(false)} />
            ))}
            <button
              onClick={handleLogout}
              className="flex h-10 w-full items-center gap-3 rounded-lg px-3 text-sm font-semibold text-zinc-600 transition hover:bg-rose-50 hover:text-rose-700"
            >
              <LogOut className="h-4 w-4" />
              Sair
            </button>
          </nav>
        ) : null}
      </header>

      <div className="lg:pl-72">
        <main className="mx-auto min-h-screen w-full max-w-[1500px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <div className="mb-6 hidden items-center justify-between border-b border-zinc-200 pb-5 lg:flex">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Área atual</p>
              <p className="mt-1 text-lg font-bold text-zinc-950">{activePage.name}</p>
            </div>
            <div className="flex items-center gap-3 rounded-lg border border-zinc-200 bg-white px-3 py-2 shadow-sm">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-100 text-xs font-bold text-emerald-700">
                {initials || 'FM'}
              </div>
              <span className="max-w-56 truncate text-sm font-semibold text-zinc-700">{user?.email || 'Usuário'}</span>
            </div>
          </div>

          <Outlet />
        </main>
      </div>
    </div>
  )
}
