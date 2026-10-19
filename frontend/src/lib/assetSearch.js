// Busca de um ativo da carteira enquanto se digita (AssetPicker): ticker ou
// nome, sem acento nem caixa. Quem comeca com o texto vem antes de quem so o
// contem, e o ticker antes do nome — como a busca do catalogo da B3
// (market_catalog.search). Puro: testado por node --test.

export function normalizeSearchText(value) {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toUpperCase()
    .replace(/\s+/g, ' ')
    .trim()
}

// options: [{ value, label, name?, ... }]. Sem texto, todas na ordem dada.
export function filterAssetOptions(options, query, limit = 50) {
  const list = options || []
  const needle = normalizeSearchText(query)
  if (!needle) return list.slice(0, limit)
  const ranked = []
  list.forEach((option, index) => {
    const label = normalizeSearchText(option.label)
    const name = normalizeSearchText(option.name)
    let rank
    if (label.startsWith(needle)) rank = 0
    else if (label.includes(needle)) rank = 1
    else if (name.startsWith(needle)) rank = 2
    else if (name.includes(needle)) rank = 3
    else return
    ranked.push({ rank, index, option })
  })
  ranked.sort((a, b) => a.rank - b.rank || a.index - b.index)
  return ranked.slice(0, limit).map((item) => item.option)
}
