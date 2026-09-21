import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { LogOut } from 'lucide-react'
import { getCurrentUser, signOut } from '../lib/auth'
import { Button, PageHeader, Panel, PanelHeader } from '../components/ui'
import ContasSection from './ajustes/ContasSection'
import CartoesSection from './ajustes/CartoesSection'
import CategoriasSection from './ajustes/CategoriasSection'
import DemoDataSection from './ajustes/DemoDataSection'

const SECTION_LINKS = [
  { id: 'contas', label: 'Contas' },
  { id: 'cartoes', label: 'Cartões' },
  { id: 'categorias', label: 'Categorias' },
  { id: 'dados-de-exemplo', label: 'Dados de exemplo' },
  { id: 'sessao', label: 'Sessão' },
]

// O router nao rola ate a ancora sozinho. Rola na chegada e de novo depois que
// as secoes carregaram, porque a altura das listas muda quando os dados chegam.
function useHashScroll() {
  const { hash } = useLocation()

  useEffect(() => {
    const id = decodeURIComponent(hash.replace('#', ''))
    if (!id) return undefined

    const scroll = (behavior) => {
      document.getElementById(id)?.scrollIntoView({ behavior, block: 'start' })
    }
    const frame = requestAnimationFrame(() => scroll('auto'))
    const timer = setTimeout(() => scroll('smooth'), 450)
    return () => {
      cancelAnimationFrame(frame)
      clearTimeout(timer)
    }
  }, [hash])
}

// Configuracao feita uma vez: contas, cartoes, categorias, dados de exemplo, sessao.
export default function Ajustes() {
  const user = getCurrentUser()
  // Os dados de exemplo criam cartoes e mexem nos saldos: as outras secoes
  // recarregam quando esse numero muda.
  const [dataVersion, setDataVersion] = useState(0)
  useHashScroll()
  // Os chips do cabecalho rolam tambem no clique: repetir a mesma ancora nao muda a URL.

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Configuração"
        title="Ajustes"
        description="Contas, cartões e categorias — o que se configura uma vez e raramente muda."
        meta={SECTION_LINKS.map((section) => (
          <Link
            key={section.id}
            to={{ hash: section.id }}
            replace
            onClick={() => document.getElementById(section.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
            className="inline-flex h-10 items-center rounded-full border border-zinc-200 bg-white px-3 text-sm font-semibold text-zinc-700 hover:border-zinc-300 hover:text-zinc-950"
          >
            {section.label}
          </Link>
        ))}
      />

      <ContasSection refreshKey={dataVersion} />
      <CartoesSection refreshKey={dataVersion} />
      <CategoriasSection refreshKey={dataVersion} />
      <DemoDataSection onDataChanged={() => setDataVersion((version) => version + 1)} />

      <Panel id="sessao" className="scroll-mt-20 lg:scroll-mt-8">
        <PanelHeader title="Sessão" description="Conta conectada neste navegador." />
        <div className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
          <p className="truncate text-sm font-semibold text-zinc-900">{user?.email || 'Usuário'}</p>
          <Button variant="danger" icon={LogOut} onClick={signOut}>Sair</Button>
        </div>
      </Panel>
    </div>
  )
}
