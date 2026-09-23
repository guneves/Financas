// Rolagem ao navegar. Tela nova comeca do topo; voltar/avancar (POP) devolve a
// rolagem que a entrada do historico tinha. O navegador sozinho nao consegue:
// ele tenta restaurar antes de a pagina carregar os dados, quando ela ainda e
// curta demais, e desiste. Aqui a posicao fica guardada por `location.key` e o
// restauro espera a pagina crescer ate caber (ou o usuario rolar, ou 3 s).
import { useEffect, useLayoutEffect, useRef } from 'react'
import { useLocation, useNavigationType } from 'react-router-dom'

const STORAGE_KEY = 'financeMVP:scroll'
const RESTORE_TIMEOUT_MS = 3000
const MAX_ENTRIES = 50

function readPositions() {
  try {
    return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '{}') || {}
  } catch {
    return {}
  }
}

function writePositions(positions) {
  try {
    const keys = Object.keys(positions)
    const trimmed = keys.length > MAX_ENTRIES
      ? Object.fromEntries(keys.slice(-MAX_ENTRIES).map((key) => [key, positions[key]]))
      : positions
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed))
  } catch {
    // Sem sessionStorage (janela privada, bloqueio): so nao restaura.
  }
}

export function useScrollRestoration() {
  const location = useLocation()
  const navigationType = useNavigationType()
  const positions = useRef(null)
  if (positions.current === null) positions.current = readPositions()
  const currentKey = useRef(location.key)

  useEffect(() => {
    if ('scrollRestoration' in window.history) window.history.scrollRestoration = 'manual'
    let frame = 0
    const onScroll = () => {
      if (frame) return
      frame = requestAnimationFrame(() => {
        frame = 0
        positions.current[currentKey.current] = window.scrollY
      })
    }
    const onHide = () => writePositions(positions.current)
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('pagehide', onHide)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('pagehide', onHide)
    }
  }, [])

  const lastPathname = useRef(location.pathname)

  useLayoutEffect(() => {
    currentKey.current = location.key
    writePositions(positions.current)
    const pathChanged = lastPathname.current !== location.pathname
    lastPathname.current = location.pathname

    const target = navigationType === 'POP' ? positions.current[location.key] : undefined
    if (!target) {
      // So troca de tela volta ao topo: um filtro que reescreve a URL
      // (?busca=) nao pode pular a pagina. Link com #ancora fica com o navegador.
      if (pathChanged && !location.hash) window.scrollTo(0, 0)
      return undefined
    }

    let frame = 0
    let stopped = false
    const started = performance.now()
    const stop = () => {
      stopped = true
      cancelAnimationFrame(frame)
      window.removeEventListener('wheel', stop)
      window.removeEventListener('touchstart', stop)
      window.removeEventListener('keydown', stop)
    }
    // Rolar de proposito interrompe: nao puxa a tela de volta.
    window.addEventListener('wheel', stop, { passive: true })
    window.addEventListener('touchstart', stop, { passive: true })
    window.addEventListener('keydown', stop)
    const attempt = () => {
      if (stopped) return
      const maxScroll = document.documentElement.scrollHeight - window.innerHeight
      window.scrollTo(0, Math.min(target, maxScroll))
      if (maxScroll >= target || performance.now() - started > RESTORE_TIMEOUT_MS) {
        stop()
        return
      }
      frame = requestAnimationFrame(attempt)
    }
    attempt()
    return stop
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.key])
}
