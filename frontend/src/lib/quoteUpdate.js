// "Atualizar cotações" (Posição) mostra só as falhas (dono 2026-11-11): o que
// atualizou não vira aviso. Uma linha por motivo: um tempo limite do provedor
// não se repete ticker a ticker. Sem falha, nada aparece.
export function quoteFailureGroups(result) {
  const groups = new Map()
  for (const item of result?.failed_assets || []) {
    const error = item?.error || 'sem detalhe'
    const name = item?.ticker || item?.name || ''
    if (!groups.has(error)) groups.set(error, [])
    groups.get(error).push(name)
  }
  return [...groups].map(([error, names]) => ({ error, names }))
}

export function quoteFailureCount(result) {
  return (result?.failed_assets || []).length
}
