import { createContext, useContext } from 'react'

// "+ Novo" mora no Layout, fora das paginas. Qualquer pagina abre o sheet com
// `openNewEntry('CARD')` (ou sem tipo, para a escolha padrao).
// Tipos: 'EXPENSE' | 'INCOME' | 'TRANSFER' | 'CARD' | 'INVESTMENT'.
export const NewEntryContext = createContext({ openNewEntry: () => {} })

export function useNewEntry() {
  return useContext(NewEntryContext)
}

// Contador incrementado pelo Layout depois de cada gravacao feita pelo "+ Novo".
// Paginas o colocam nas dependencias do efeito de busca para recarregar.
export const DataVersionContext = createContext(0)

export function useDataVersion() {
  return useContext(DataVersionContext)
}
