import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { hasNativeScreen, openNativeScreen, takeStartRoute } from '../lib/nativeScreens'
import { nativePageExit, nativePageOpenRequest, wantsWebPage } from '../lib/nativeScreensRules'

// Uma pagina que o APK pode ter em nativo (Lancamentos › Aprovar): num APK
// que lista a tela (NativeScreens.routes()), a rota abre a nativa por cima e a
// WebView volta para onde estava; no navegador, num APK antigo ou se a nativa
// nao abrir, mostra a React (children). Vale para toda entrada da rota: a
// aba, a pilula do cabecalho, o link do Extrato e o caminho antigo /aprovar.
//
// `stay` (Inicio): a WebView fica na rota, sem desenhar nada, por baixo da
// nativa — o Inicio e a tela de partida, nao ha "tela de antes" para onde
// voltar; os links da nativa trazem a WebView pelo evento "navigate", e
// voltar na nativa minimiza o app. `?web=1` na rota pede a pagina React (a
// nativa leva para ela o que ainda nao tem).
export default function NativePage({ screen, stay = false, children }) {
  const navigate = useNavigate()
  const location = useLocation()
  const webPage = wantsWebPage(location.search)
  const [react, setReact] = useState(() => !hasNativeScreen(screen))
  const opened = useRef('')

  useEffect(() => {
    // Na pagina web (?web=1) a nativa nao abre; voltar dela para a rota
    // (a mesma entrada do historico) abre a nativa de novo.
    if (webPage) {
      opened.current = ''
      return
    }
    if (react || opened.current === location.key) return
    // O app foi recriado a partir de uma tela nativa que pediu outra rota (um
    // link do Inicio nativo): vai para ela em vez de reabrir a nativa.
    const start = takeStartRoute()
    if (start) {
      navigate(start)
      return
    }
    opened.current = location.key
    openNativeScreen(nativePageOpenRequest(screen))
      .then(() => {
        if (stay) return
        const exit = nativePageExit({ hasHistory: location.key !== 'default' })
        if (exit.back) navigate(-1)
        else navigate(exit.route, { replace: true })
      })
      .catch(() => setReact(true))
  }, [react, webPage, stay, screen, location.key, navigate])

  return react || webPage ? children : null
}
