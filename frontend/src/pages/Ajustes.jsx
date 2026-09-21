import { LogOut } from 'lucide-react'
import { getCurrentUser, signOut } from '../lib/auth'
import { Button, PageHeader, Panel, PanelHeader } from '../components/ui'

// Configuracao feita uma vez: contas, cartoes, categorias, dados de exemplo, sessao.
export default function Ajustes() {
  const user = getCurrentUser()

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Configuração"
        title="Ajustes"
        description="Contas, cartões e categorias — o que se configura uma vez e raramente muda."
      />

      <Panel id="sessao">
        <PanelHeader title="Sessão" description="Conta conectada neste navegador." />
        <div className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
          <p className="truncate text-sm font-semibold text-zinc-900">{user?.email || 'Usuário'}</p>
          <Button variant="danger" icon={LogOut} onClick={signOut}>Sair</Button>
        </div>
      </Panel>
    </div>
  )
}
