import { useEffect, useState } from 'react'

// O valor, so depois de `delay` ms sem mudar (busca enquanto digita).
export default function useDebouncedValue(value, delay) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}
