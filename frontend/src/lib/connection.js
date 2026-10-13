// O servidor respondeu ao ultimo pedido? (lib/api.js guarda; aqui so o hook.)
import { useSyncExternalStore } from 'react'
import { isServerReachable, subscribeServerReachable } from './api'

export function useServerReachable() {
  return useSyncExternalStore(subscribeServerReachable, isServerReachable)
}
