import {
  Briefcase,
  CalendarDays,
  CreditCard,
  History,
  Home,
  PieChart,
  Receipt,
  Repeat,
  Target,
  Wallet,
} from 'lucide-react'

// Mapa de telas (docs/ux-reorganization.md §3). Layout, rotas e abas saem daqui.
export const sections = [
  { name: 'Início', path: '/inicio', icon: Home, tabs: [] },
  {
    name: 'Lançamentos',
    path: '/lancamentos',
    icon: Receipt,
    tabs: [
      { to: '/lancamentos/extrato', label: 'Extrato', icon: Wallet },
      { to: '/lancamentos/cartoes', label: 'Cartões', icon: CreditCard },
    ],
  },
  {
    name: 'Planejamento',
    path: '/planejamento',
    icon: Target,
    tabs: [
      { to: '/planejamento/orcamento', label: 'Orçamento', icon: Target },
      { to: '/planejamento/recorrentes', label: 'Recorrentes', icon: Repeat },
    ],
  },
  {
    name: 'Investimentos',
    path: '/investimentos',
    icon: Briefcase,
    tabs: [
      { to: '/investimentos/posicao', label: 'Posição', icon: PieChart },
      { to: '/investimentos/operacoes', label: 'Operações', icon: History },
      { to: '/investimentos/proventos', label: 'Proventos', icon: CalendarDays },
    ],
  },
]

export const SETTINGS_PATH = '/ajustes'

// Caminhos antigos -> novos. Links salvos e o historico do navegador continuam valendo.
export const legacyRedirects = {
  '/dashboard': '/inicio',
  '/transactions': '/lancamentos/extrato',
  '/carteira': '/lancamentos/extrato',
  '/orcamento': '/planejamento/orcamento',
  '/recorrentes': '/planejamento/recorrentes',
  '/investments': '/investimentos/posicao',
  '/proventos': '/investimentos/proventos',
}

export function findSection(pathname) {
  return sections.find((section) => pathname === section.path || pathname.startsWith(`${section.path}/`)) || null
}
