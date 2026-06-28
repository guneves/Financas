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

export async function signUp(email, password) {
  const authData = await apiFetch('/api/auth/signup', {
    auth: false,
    method: 'POST',
    body: JSON.stringify({ email, password })
  })
  setStoredAuth(authData)
  return authData
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
