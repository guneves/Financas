const DEFAULT_API_BASE_URL = 'http://localhost:5000'
const AUTH_STORAGE_KEY = '@financeMVP:auth'

const normalizeBaseUrl = (value) => {
  return (value || DEFAULT_API_BASE_URL).replace(/\/+$/, '')
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

export async function apiFetch(path, options = {}) {
  const { auth = true, ...fetchOptions } = options
  const headers = new Headers(fetchOptions.headers || {})

  if (auth) {
    const authData = getStoredAuth()
    if (!authData?.access_token) {
      throw new Error('Sessao expirada. Entre novamente para continuar.')
    }
    headers.set('Authorization', `Bearer ${authData.access_token}`)
  }

  if (fetchOptions.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let response
  try {
    response = await fetch(`${API_BASE_URL}${normalizePath(path)}`, {
      ...fetchOptions,
      headers
    })
  } catch {
    throw new Error(`API indisponivel em ${API_BASE_URL}. Verifique se o backend Flask esta rodando.`)
  }

  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json')
    ? await response.json()
    : await response.text()

  if (!response.ok) {
    const message = typeof payload === 'object' && payload !== null
      ? payload.error || payload.message
      : payload

    throw new Error(message || `Erro HTTP ${response.status}`)
  }

  return payload
}
