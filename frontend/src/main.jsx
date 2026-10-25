import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import App from './App.jsx'
import { dropLegacyCaches, queryClient } from './lib/queries'
import { persistQueryCache, restoreQueryCache } from './lib/queryPersist'
import { startOutbox } from './lib/outbox'
import './index.css' // Importa o Tailwind (adicione as diretivas @tailwind base, components, utilities neste arquivo)

dropLegacyCaches()

// Antes da primeira tela: o cache guardado no aparelho (o app abre sem o
// servidor com o que ja tinha visto) e a fila de envio. Ler o IndexedDB leva
// milissegundos, e assim nenhuma tela chega a buscar com o cache ainda vazio.
restoreQueryCache(queryClient).finally(() => {
  persistQueryCache(queryClient)
  startOutbox()
  ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </React.StrictMode>,
  )
})
