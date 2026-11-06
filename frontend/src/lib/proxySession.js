// O proxy de autenticacao na frente do app (Caddy + oauth2-proxy, porta 8443 do
// Funnel; README "Remote access"). Quando a sessao do Google vence, o proxy
// responde ele mesmo, sem o pedido chegar ao app:
//   - em /api: 401 com `X-Proxy-Auth: required`;
//   - fora de /api: um 302 para o login do Google, que o fetch com
//     `redirect: 'manual'` ve como `opaqueredirect`.
// Nao e o login do app expirado: o JWT fica, e a pagina recarrega para passar
// pelo login do Google de novo (lib/api.js). Puro, testado em proxySession.test.js.

export const PROXY_RELOAD_MIN_MS = 30_000

export function isProxyAuthResponse(response) {
  if (!response) return false
  if (response.type === 'opaqueredirect') return true
  return response.status === 401 && response.headers?.get?.('X-Proxy-Auth') === 'required'
}

// No maximo uma recarga a cada 30 s: se o login do Google nao resolver, a
// pagina nao entra num laco de recargas.
export function shouldReload(lastTs, now) {
  const last = Number(lastTs)
  if (!Number.isFinite(last) || last <= 0) return true
  if (now < last) return true
  return now - last >= PROXY_RELOAD_MIN_MS
}
