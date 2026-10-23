import { apiFetch, clearStoredAuth, getStoredAuth, setStoredAuth } from './api'

export function getSession() {
  return getStoredAuth()
}

export function getCurrentUser() {
  return getStoredAuth()?.user || null
}

export async function signIn(email, password) {
  const authData = await apiFetch('/api/auth/login', {
    auth: false,
    method: 'POST',
    body: JSON.stringify({ email, password })
  })
  setStoredAuth(authData)
  return authData
}

export async function signUp(email, password, username) {
  const authData = await apiFetch('/api/auth/signup', {
    auth: false,
    method: 'POST',
    body: JSON.stringify({ email, password, username })
  })
  setStoredAuth(authData)
  return authData
}

// O cadastro fecha quando o servidor ja tem o seu usuario (ALLOW_SIGNUP abre).
// Sem resposta, fechado: a tela so oferece entrar.
export async function signupOpen() {
  try {
    const status = await apiFetch('/api/auth/signup', { auth: false })
    return Boolean(status?.open)
  } catch {
    return false
  }
}

// Troca o nome de usuario e atualiza a sessao guardada, para a barra lateral
// mostrar o nome novo sem precisar entrar de novo.
export async function updateUsername(username) {
  const data = await apiFetch('/api/auth/me', {
    method: 'PATCH',
    body: JSON.stringify({ username })
  })
  const session = getStoredAuth()
  if (session) setStoredAuth({ ...session, user: data.user })
  return data.user
}

// Nome exibido na interface. Nunca o e-mail: conta antiga sem nome aparece
// como "Usuário" ate escolher um em Ajustes.
export function displayName(user) {
  return user?.username || 'Usuário'
}

export function signOut() {
  clearStoredAuth()
}

export function onAuthStateChange(callback) {
  const handler = (event) => {
    callback(event.detail)
  }

  const storageHandler = (event) => {
    if (event.key === '@financeMVP:auth') {
      callback(getStoredAuth())
    }
  }

  window.addEventListener('finance-auth-change', handler)
  window.addEventListener('storage', storageHandler)

  return () => {
    window.removeEventListener('finance-auth-change', handler)
    window.removeEventListener('storage', storageHandler)
  }
}
