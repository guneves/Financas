// Tema claro/escuro. 'system' segue o sistema operacional; 'light' e 'dark'
// sao a escolha manual (Ajustes › Aparencia). O index.html aplica a mesma
// regra antes da primeira pintura; aqui ela continua valendo quando o sistema
// troca de tema com o app aberto.
//
// O modo escuro e so a classe `dark` no <html>: index.css troca as variaveis
// de cor, e nenhuma pagina remonta nem busca de novo ao alternar.
import { useSyncExternalStore } from 'react'

const THEME_KEY = '@financeMVP:theme'
const THEMES = ['system', 'light', 'dark']

const media = typeof window !== 'undefined' && window.matchMedia
  ? window.matchMedia('(prefers-color-scheme: dark)')
  : null

let preference = (() => {
  try {
    const stored = localStorage.getItem(THEME_KEY)
    return THEMES.includes(stored) ? stored : 'system'
  } catch {
    return 'system'
  }
})()

const listeners = new Set()

function isDark() {
  return preference === 'dark' || (preference === 'system' && Boolean(media?.matches))
}

function apply() {
  const dark = isDark()
  document.documentElement.classList.toggle('dark', dark)
  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.setAttribute('content', dark ? '#0B1210' : '#EFF2ED')
  listeners.forEach((listener) => listener())
}

media?.addEventListener?.('change', () => {
  if (preference === 'system') apply()
})

function subscribe(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function setThemePreference(next) {
  preference = THEMES.includes(next) ? next : 'system'
  try {
    localStorage.setItem(THEME_KEY, preference)
  } catch {
    // Sem localStorage a escolha so dura ate recarregar a pagina.
  }
  apply()
}

// A escolha atual ('system' | 'light' | 'dark'), fora do React.
export function themePreferenceNow() {
  return preference
}

export function useIsDark() {
  return useSyncExternalStore(subscribe, isDark)
}

export function useThemePreference() {
  return useSyncExternalStore(subscribe, () => preference)
}
