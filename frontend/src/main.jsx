import React, { useEffect } from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import App from './App.jsx'
import { dropLegacyCaches, queryClient } from './lib/queries'
import { persistQueryCache, restoreQueryCache } from './lib/queryPersist'
import { startOutbox } from './lib/outbox'
import { startNativeApp } from './lib/nativeApp'
import { startAppBundle } from './lib/appBundle'
import './index.css' // Importa o Tailwind (adicione as diretivas @tailwind base, components, utilities neste arquivo)

dropLegacyCaches()

// Roda so depois que a tela desenhou sem erro: no APK, e o que confirma uma tela
// baixada do servidor (lib/appBundle.js). Uma tela que quebra no primeiro desenho
// nunca chega aqui, e o app volta para a do APK.
function AppStarted() {
  useEffect(() => {
    startAppBundle()
  }, [])
  return null
}

// Antes da primeira tela: o cache guardado no aparelho (o app abre sem o
// servidor com o que ja tinha visto) e a fila de envio. Ler o IndexedDB leva
// milissegundos, e assim nenhuma tela chega a buscar com o cache ainda vazio.
// No APK a fila e nativa: startNativeApp() troca o armazenamento antes de
// startOutbox() ler a fila (no navegador ela nao faz nada).
restoreQueryCache(queryClient).finally(async () => {
  persistQueryCache(queryClient)
  await startNativeApp().catch((error) => console.warn('Integracao nativa indisponivel:', error))
  startOutbox()
  ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <App />
        <AppStarted />
      </QueryClientProvider>
    </React.StrictMode>,
  )
})
