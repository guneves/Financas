import { useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { PageHeader } from '../components/ui'
import { isAppBundleAvailable } from '../lib/appBundle'
import AppVersionSection from './ajustes/AppVersionSection'
import ContasSection from './ajustes/ContasSection'
import CartoesSection from './ajustes/CartoesSection'
import CategoriasSection from './ajustes/CategoriasSection'
import IntegracoesSection from './ajustes/IntegracoesSection'
import PerfilSection from './ajustes/PerfilSection'
import RegrasSection from './ajustes/RegrasSection'

const SECTION_LINKS = [
  { id: 'contas', label: 'Contas' },
  { id: 'cartoes', label: 'Cartões' },
  { id: 'categorias', label: 'Categorias' },
  { id: 'regras-de-importacao', label: 'Regras de importação' },
  { id: 'integracoes', label: 'Integrações' },
  { id: 'perfil', label: 'Perfil' },
  // So no APK (AppVersionSection).
  ...(isAppBundleAvailable() ? [{ id: 'versao', label: 'Versão' }] : []),
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

// Configuracao feita uma vez: contas, cartoes, categorias, regras, integracoes, perfil
// (e, no APK, a versao do app).
export default function Ajustes() {
  useHashScroll()
  // Os chips do cabecalho rolam tambem no clique: repetir a mesma ancora nao muda a URL.

  return (
    <div className="space-y-6">
      <PageHeader
        title="Ajustes"
        description="Contas, cartões e categorias — o que se configura uma vez e raramente muda."
        meta={(
          <nav aria-label="Seções de Ajustes" className="inline-flex max-w-full gap-1 overflow-x-auto rounded-full border border-zinc-200 bg-white p-1">
            {SECTION_LINKS.map((section) => (
              <Link
                key={section.id}
                to={{ hash: section.id }}
                replace
                onClick={() => document.getElementById(section.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
                className="inline-flex h-10 shrink-0 items-center rounded-full px-4 text-sm font-semibold text-zinc-600 transition hover:bg-zinc-100 hover:text-zinc-950 lg:h-9"
              >
                {section.label}
              </Link>
            ))}
          </nav>
        )}
      />

      <ContasSection />
      <CartoesSection />
      <CategoriasSection />
      <RegrasSection />
      <IntegracoesSection />
      <PerfilSection />
      <AppVersionSection />
    </div>
  )
}
