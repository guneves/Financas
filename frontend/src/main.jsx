import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import App from './App.jsx'
import { dropLegacyCaches, queryClient } from './lib/queries'
import './index.css' // Importa o Tailwind (adicione as diretivas @tailwind base, components, utilities neste arquivo)

dropLegacyCaches()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
)
