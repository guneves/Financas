import {
  Briefcase,
  Calculator,
  CalendarDays,
  Coins,
  CreditCard,
  FileText,
  Flag,
  History,
  Home,
  PieChart,
  Receipt,
  Repeat,
  Scale,
  Upload,
  Target,
  TrendingUp,
  Wallet,
} from 'lucide-react'

export const APROVAR_PATH = '/lancamentos/aprovar'

// Mapa de telas (docs/ux-reorganization.md §3). Layout, rotas e abas saem daqui.
export const sections = [
  { name: 'Início', path: '/inicio', icon: Home, tabs: [] },
  {
    name: 'Lançamentos',
    path: '/lancamentos',
    icon: Receipt,
    tabs: [
      // O que gravou sozinho e espera o dono confirmar (045). Aprovar saiu das
      // abas: so o que nao grava sozinho fica la, e o Extrato aponta.
      { to: '/lancamentos/extrato', label: 'Extrato', icon: Wallet, badge: 'review' },
      { to: '/lancamentos/cartoes', label: 'Cartões', icon: CreditCard },
      // A parte dos outros nas despesas, ate o dono marcar que pagaram (032).
      { to: '/lancamentos/a-receber', label: 'A receber', icon: Coins },
      { to: '/lancamentos/importar', label: 'Importar', icon: Upload },
    ],
  },
  {
    name: 'Planejamento',
    // Nome curto da barra de baixo do celular: cinco colunas de 72 px.
    shortName: 'Planejar',
    path: '/planejamento',
    icon: Target,
    tabs: [
      { to: '/planejamento/orcamento', label: 'Orçamento', icon: Target },
      { to: '/planejamento/recorrentes', label: 'Recorrentes', icon: Repeat },
      { to: '/planejamento/metas', label: 'Metas', icon: Flag },
    ],
  },
  {
    name: 'Investimentos',
    shortName: 'Investir',
    path: '/investimentos',
    icon: Briefcase,
    tabs: [
      { to: '/investimentos/posicao', label: 'Posição', icon: PieChart },
      { to: '/investimentos/rentabilidade', label: 'Rentabilidade', icon: TrendingUp },
      { to: '/investimentos/operacoes', label: 'Operações', icon: History },
      { to: '/investimentos/alocacao', label: 'Alocação', icon: Scale },
      { to: '/investimentos/proventos', label: 'Proventos', icon: CalendarDays },
      { to: '/investimentos/ir', label: 'IR', icon: FileText },
      // Simulacao de juros compostos: so conta, nao le nem grava nada da carteira.
      { to: '/investimentos/calculadora', label: 'Calculadora', icon: Calculator },
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
  '/aprovar': APROVAR_PATH,
}

export function findSection(pathname) {
  return sections.find((section) => pathname === section.path || pathname.startsWith(`${section.path}/`)) || null
}
