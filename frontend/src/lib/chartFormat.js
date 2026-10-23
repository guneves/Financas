// Rotulos dos eixos de valor dos graficos, como funcao pura (testada com
// `node --test`, chartFormat.test.js). components/charts.jsx a reexporta.
// Port: android/.../rules/HomeFlow.kt (compactAxis), os mesmos casos em
// HomeFlowTest.kt: mudou um, muda o outro.

// Eixo de valores: sem o "R$" (o titulo do grafico ja diz que e dinheiro), para
// o rotulo caber numa linha — "R$ 900 mil" quebrava em duas na largura do eixo.
export function compactAxis(value) {
  const numeric = Number(value || 0)
  const absolute = Math.abs(numeric)
  const sign = numeric < 0 ? '−' : ''
  if (absolute >= 1_000_000) {
    return `${sign}${(absolute / 1_000_000).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} mi`
  }
  if (absolute >= 1000) {
    return `${sign}${(absolute / 1000).toLocaleString('pt-BR', { maximumFractionDigits: absolute >= 10000 ? 0 : 1 })} mil`
  }
  return `${sign}${absolute.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`
}
