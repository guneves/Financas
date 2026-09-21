import { createContext, useContext } from 'react'

// "+ Novo" mora no Layout, fora das paginas. Qualquer pagina abre o sheet com
// `openNewEntry('CARD')` (ou sem tipo, para a escolha padrao).
export const NewEntryContext = createContext({ openNewEntry: () => {} })

export function useNewEntry() {
  return useContext(NewEntryContext)
}
