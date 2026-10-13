// Em desenvolvimento o Vite (5173) fala com o Flask (5000). O build e servido
// pelo proprio Flask (routes/frontend.py), entao a API e a mesma origem da
// tela: e o que o celular abre pelo endereco do Tailscale. VITE_API_BASE_URL
// vence os dois (o APK aponta para o endereco do Tailscale no build).
const DEFAULT_API_BASE_URL = import.meta.env.DEV ? 'http://localhost:5000' : ''
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

// Metodo que grava, menos as previas (POST que so calcula e nao muda nada).
function isWrite(method, path) {
  const verb = String(method || 'GET').toUpperCase()
  if (verb === 'GET' || verb === 'HEAD') return false
  return !/\/preview(\?|$)/.test(path) && !path.startsWith('/api/auth/login') && !path.startsWith('/api/auth/signup')
}

export async function apiFetch(path, options = {}) {
  const { auth = true, ...fetchOptions } = options
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
  try {
    response = await fetch(`${API_BASE_URL}${normalizePath(path)}`, {
      ...fetchOptions,
      headers
    })
  } catch {
    setServerReachable(false)
    throw new ApiNetworkError(NETWORK_MESSAGE)
  }
  setServerReachable(true)

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

  if (mutationListener && isWrite(fetchOptions.method, normalizePath(path))) mutationListener()
  return payload
}

// Download autenticado: o token vai no cabecalho, entao um <a href> simples
// nao serve — a resposta vira um Blob e um link temporario dispara o salvamento.
// O nome do arquivo vem do Content-Disposition quando o navegador consegue
// ler o cabecalho (CORS o expoe); senao, cai no nome sugerido aqui.
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
      headers: { Authorization: `Bearer ${authData.access_token}` }
    })
  } catch {
    setServerReachable(false)
    throw new ApiNetworkError(NETWORK_MESSAGE)
  }
  setServerReachable(true)

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
