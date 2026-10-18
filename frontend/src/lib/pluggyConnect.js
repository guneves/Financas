// O Pluggy Connect: o widget da Pluggy em que o dono escolhe o banco e da o
// consentimento do Open Finance. O backend pede o token (a apiKey nunca chega
// aqui); o SDK so e baixado quando o widget abre, porque o app abre offline.
import { pluggyApi } from './dataApi'

// Abre o widget e resolve com o item conectado, ou null se o dono fechou.
// Com itemRowId, reconecta aquela conexao (consentimento vencido, senha nova).
export async function openPluggyConnect({ itemRowId, dark = false } = {}) {
  const [{ access_token: connectToken }, { PluggyConnect }] = await Promise.all([
    pluggyApi.connectToken(itemRowId),
    import('pluggy-connect-sdk'),
  ])
  return new Promise((resolve, reject) => {
    let settled = false
    // Um erro (senha errada...) deixa o widget aberto para tentar de novo; so
    // vira erro aqui se o dono fechar sem conseguir.
    let lastError = null
    const finish = (fn, value) => {
      if (settled) return
      settled = true
      fn(value)
    }
    const widget = new PluggyConnect({
      connectToken,
      language: 'pt',
      theme: dark ? 'dark' : 'light',
      countries: ['BR'],
      onSuccess: ({ item }) => finish(resolve, item),
      onError: (error) => {
        lastError = new Error(error?.message || 'A Pluggy não conseguiu conectar o banco.')
      },
      onClose: () => (lastError ? finish(reject, lastError) : finish(resolve, null)),
    })
    widget.init().catch((error) => finish(reject, error))
  })
}
