// A API e sempre a mesma origem da tela: o build e servido pelo proprio Flask
// (routes/frontend.py) e, em desenvolvimento, o Vite (5173) repassa /api ao
// Flask (vite.config.js). O servidor nao tem CORS: VITE_API_BASE_URL, se usado,
// tem de ser da mesma origem da tela (um caminho, ou o proprio endereco).
import { isProxyAuthResponse, shouldReload } from './proxySession.js'

const DEFAULT_API_BASE_URL = ''
const AUTH_STORAGE_KEY = '@financeMVP:auth'

const normalizeBaseUrl = (value) => {
  return (value || DEFAULT_API_BASE_URL).replace(/\/+$/, '')
}

// O pedido nao chegou ao servidor (sem rede, backend parado). So este erro
// manda uma criacao para a fila (lib/outbox.js): uma resposta do servidor,
// qualquer que seja, nunca e reenviada sozinha.
export class ApiNetworkError extends Error {
  constructor(message) {
    super(message)
    this.name = 'ApiNetworkError'
    this.network = true
  }
}

const NETWORK_MESSAGE = 'Sem conexão com o servidor. Esta ação só funciona conectado.'

const PROXY_AUTH_MESSAGE = 'O login do Google venceu. A página vai recarregar para você entrar de novo.'

// O proxy de autenticacao (login do Google na porta 8443) recusou o pedido
// antes do app: a sessao do Google venceu. Nao e ApiNetworkError (o servidor
// respondeu) nem o login do app vencido (o JWT fica). Uma criacao do "+ Novo"
// tambem vai para a fila (lib/outboxRules.js `queuesCreation()`), e a pagina
// recarrega para passar pelo login do Google (lib/proxySession.js).
export class ApiProxyAuthError extends Error {
  constructor(message = PROXY_AUTH_MESSAGE) {
    super(message)
    this.name = 'ApiProxyAuthError'
    this.proxyAuth = true
    this.status = 401
  }
}

const PROXY_RELOAD_KEY = '@financeMVP:proxyReloadAt'
// A recarga espera um pouco: quem recebeu o erro (createEntry) ainda guarda o
// lancamento na fila antes de a pagina sair.
const PROXY_RELOAD_DELAY_MS = 1_000

function readReloadTs() {
  try {
    return sessionStorage.getItem(PROXY_RELOAD_KEY)
  } catch {
    return null
  }
}

function proxyAuthFailure() {
  const now = Date.now()
  if (typeof window !== 'undefined' && shouldReload(readReloadTs(), now)) {
    try {
      sessionStorage.setItem(PROXY_RELOAD_KEY, String(now))
    } catch {
      // sem sessionStorage: recarrega mesmo assim (o login do Google para o laco)
    }
    setTimeout(() => window.location.reload(), PROXY_RELOAD_DELAY_MS)
  }
  return new ApiProxyAuthError()
}

// O servidor respondeu da ultima vez? Quem mostra o aviso de "sem conexao"
// (Layout) assina aqui; muda a cada pedido, com ou sem sucesso.
let serverReachable = true
const reachabilityListeners = new Set()

function setServerReachable(value) {
  if (serverReachable === value) return
  serverReachable = value
  reachabilityListeners.forEach((listener) => listener())
}

export function subscribeServerReachable(listener) {
  reachabilityListeners.add(listener)
  return () => reachabilityListeners.delete(listener)
}

export function isServerReachable() {
  return serverReachable
}

const normalizePath = (path) => {
  return path.startsWith('/') ? path : `/${path}`
}

export const API_BASE_URL = normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL)

export function getStoredAuth() {
  const raw = localStorage.getItem(AUTH_STORAGE_KEY)
  if (!raw) return null

  try {
    return JSON.parse(raw)
  } catch {
    localStorage.removeItem(AUTH_STORAGE_KEY)
    return null
  }
}

export function setStoredAuth(authData) {
  localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(authData))
  window.dispatchEvent(new CustomEvent('finance-auth-change', { detail: authData }))
}

export function clearStoredAuth() {
  localStorage.removeItem(AUTH_STORAGE_KEY)
  window.dispatchEvent(new CustomEvent('finance-auth-change', { detail: null }))
}

// Quem quer saber que uma gravacao deu certo (lib/queries.js invalida o
// cache). Fica aqui, e nao em cada tela, para que nenhuma gravacao esqueca.
let mutationListener = null
export function setMutationListener(listener) {
  mutationListener = listener
}

// Para quem gravou com `invalidate: false` e so depois sabe se algo mudou
// (a sincronizacao de proventos): avisa como uma gravacao comum.
export function notifyMutation(path) {
  if (mutationListener) mutationListener(normalizePath(path))
}

// Metodo que grava, menos as previas (POST que so calcula e nao muda nada).
function isWrite(method, path) {
  const verb = String(method || 'GET').toUpperCase()
  if (verb === 'GET' || verb === 'HEAD') return false
  return !/\/preview(\?|$)/.test(path) && !path.startsWith('/api/auth/login') && !path.startsWith('/api/auth/signup')
}

// Leituras desistem sozinhas: no celular, com a VPN do Tailscale "conectada"
// sem rede por baixo (modo aviao), um pedido nao falha, fica pendurado. Escritas
// so desistem quando pedem (`timeoutMs`): uma edicao que estourou o tempo pode ter
// sido gravada. As criacoes do "+ Novo" pedem, porque o client_id torna o reenvio
// seguro (lib/outbox.js).
const READ_TIMEOUT_MS = 45_000

export async function apiFetch(path, options = {}) {
  // `invalidate: false`: uma gravacao que nao invalida o cache sozinha (quem
  // chama decide, por `notifyMutation()`).
  const { auth = true, timeoutMs, invalidate = true, ...fetchOptions } = options
  const isRead = !fetchOptions.method || ['GET', 'HEAD'].includes(String(fetchOptions.method).toUpperCase())
  const limit = timeoutMs ?? (isRead ? READ_TIMEOUT_MS : 0)
  const headers = new Headers(fetchOptions.headers || {})

  if (auth) {
    const authData = getStoredAuth()
    if (!authData?.access_token) {
      clearStoredAuth()
      const expired = new Error('Sessao expirada. Entre novamente para continuar.')
      expired.status = 401
      throw expired
    }
    headers.set('Authorization', `Bearer ${authData.access_token}`)
  }

  // FormData (upload) leva o Content-Type com o boundary que o navegador gera.
  if (fetchOptions.body && !(fetchOptions.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let response
  // Sem resposta no prazo conta como "nao chegou" (ApiNetworkError), igual a sem rede.
  const controller = limit && !fetchOptions.signal ? new AbortController() : null
  const timer = controller ? setTimeout(() => controller.abort(), limit) : null
  try {
    response = await fetch(`${API_BASE_URL}${normalizePath(path)}`, {
      ...fetchOptions,
      ...(controller ? { signal: controller.signal } : {}),
      headers,
      // Um 302 do proxy (login do Google) nao e seguido: vira `opaqueredirect`.
      redirect: 'manual'
    })
  } catch {
    setServerReachable(false)
    throw new ApiNetworkError(NETWORK_MESSAGE)
  } finally {
    if (timer) clearTimeout(timer)
  }
  setServerReachable(true)

  // Antes do 401 do app: o do proxy nunca apaga o JWT.
  if (isProxyAuthResponse(response)) throw proxyAuthFailure()

  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json')
    ? await response.json()
    : await response.text()

  if (!response.ok) {
    if (auth && response.status === 401) {
      clearStoredAuth()
    }

    const message = typeof payload === 'object' && payload !== null
      ? payload.error || payload.message
      : payload

    const failure = new Error(message || `Erro HTTP ${response.status}`)
    failure.status = response.status
    throw failure
  }

  if (invalidate && mutationListener && isWrite(fetchOptions.method, normalizePath(path))) mutationListener(normalizePath(path))
  return payload
}

// Download autenticado: o token vai no cabecalho, entao um <a href> simples
// nao serve — a resposta vira um Blob e um link temporario dispara o salvamento.
// O nome do arquivo vem do Content-Disposition quando o navegador consegue
// ler o cabecalho; senao, cai no nome sugerido aqui.
function filenameFromDisposition(disposition, fallback) {
  if (!disposition) return fallback
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition)
  return match ? decodeURIComponent(match[1]) : fallback
}

// Busca autenticada que devolve o Blob (comprovantes, extrato em CSV).
export async function apiBlob(path) {
  const authData = getStoredAuth()
  if (!authData?.access_token) {
    clearStoredAuth()
    throw new Error('Sessao expirada. Entre novamente para continuar.')
  }

  let response
  try {
    response = await fetch(`${API_BASE_URL}${normalizePath(path)}`, {
      headers: { Authorization: `Bearer ${authData.access_token}` },
      redirect: 'manual'
    })
  } catch {
    setServerReachable(false)
    throw new ApiNetworkError(NETWORK_MESSAGE)
  }
  setServerReachable(true)

  if (isProxyAuthResponse(response)) throw proxyAuthFailure()

  if (!response.ok) {
    if (response.status === 401) clearStoredAuth()
    let message = `Erro HTTP ${response.status}`
    try {
      const payload = await response.json()
      message = payload?.error || payload?.message || message
    } catch {
      // resposta sem JSON: fica a mensagem padrao
    }
    throw new Error(message)
  }

  return { blob: await response.blob(), disposition: response.headers.get('content-disposition') }
}

export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  // Revogar no mesmo tique pode vencer o download: o arquivo sai sem nome.
  setTimeout(() => URL.revokeObjectURL(url), 30_000)
}

export async function apiDownload(path, fallbackName) {
  const { blob, disposition } = await apiBlob(path)
  const filename = filenameFromDisposition(disposition, fallbackName)
  saveBlob(blob, filename)
  return filename
}
