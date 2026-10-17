// As camadas abertas por cima da tela (Sheet, menu "⋯", menu da conta), da
// mais antiga para a mais nova. Esc fecha so a de cima, e o voltar do Android
// tambem (lib/nativeApp.js). Antes cada uma ouvia o Esc por conta propria: com
// a confirmacao aberta sobre "Pendentes", um Esc fechava o sheet de baixo e
// deixava a pergunta solta; um Esc no "⋯" dentro de um sheet fechava o sheet.
//
// A rolagem da pagina fica travada enquanto houver um sheet aberto. Cada sheet
// guardava e restaurava o overflow do body sozinho, e dois fechando fora de
// ordem deixavam a pagina sem rolar.
import { useEffect, useRef } from 'react'

const layers = []

function syncBodyScroll() {
  document.body.style.overflow = layers.some((layer) => layer.locksScroll) ? 'hidden' : ''
}

// Fecha a camada de cima. false quando nao ha nenhuma aberta.
export function closeTopLayer() {
  const top = layers[layers.length - 1]
  if (!top) return false
  top.close()
  return true
}

// Ha algo aberto por cima da tela? (lib/appBundle.js nao troca de tela no meio de um sheet.)
export function hasOpenLayer() {
  return layers.length > 0
}

export function useLayer(open, onClose, { locksScroll = false } = {}) {
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  })

  useEffect(() => {
    if (!open) return undefined
    const layer = { locksScroll, close: () => onCloseRef.current?.() }
    layers.push(layer)
    syncBodyScroll()
    const onKey = (event) => {
      // defaultPrevented: a camada de cima ja tratou este Esc e ainda nao saiu da lista.
      if (event.key !== 'Escape' || event.defaultPrevented || layers[layers.length - 1] !== layer) return
      event.preventDefault()
      layer.close()
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      layers.splice(layers.indexOf(layer), 1)
      syncBodyScroll()
    }
  }, [open, locksScroll])
}
