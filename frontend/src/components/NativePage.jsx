import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { hasNativeScreen, openNativeScreen } from '../lib/nativeScreens'
import { nativePageExit, nativePageOpenRequest } from '../lib/nativeScreensRules'

// Uma pagina que o APK pode ter em nativo (Lancamentos › Aprovar): num APK
// que lista a tela (NativeScreens.routes()), a rota abre a nativa por cima e a
// WebView volta para onde estava; no navegador, num APK antigo ou se a nativa
// nao abrir, mostra a React (children). Vale para toda entrada da rota: a
// aba, a pilula do cabecalho, o link do Extrato e o caminho antigo /aprovar.
export default function NativePage({ screen, children }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [react, setReact] = useState(() => !hasNativeScreen(screen))
  const opened = useRef('')

  useEffect(() => {
    if (react || opened.current === location.key) return
    opened.current = location.key
    openNativeScreen(nativePageOpenRequest(screen))
      .then(() => {
        const exit = nativePageExit({ hasHistory: location.key !== 'default' })
        if (exit.back) navigate(-1)
        else navigate(exit.route, { replace: true })
      })
      .catch(() => setReact(true))
  }, [react, screen, location.key, navigate])

  return react ? children : null
}
