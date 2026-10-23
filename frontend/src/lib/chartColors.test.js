// node --test src/lib   (npm test em frontend/)
// As cores dos graficos existem duas vezes: em components/charts.jsx (FLOW e
// SERIES, que o recharts usa) e em index.css (--flow-*, --series-0), de onde
// as telas nativas as leem (android/.../ui/theme/Tokens.kt, TokensTest). Este
// teste mantem as duas iguais, nos dois temas.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const charts = readFileSync(new URL('../components/charts.jsx', import.meta.url), 'utf8')
const css = readFileSync(new URL('../index.css', import.meta.url), 'utf8')

function hexOf(name) {
  const match = charts.match(new RegExp(`\\b${name}:\\s*'#([0-9a-fA-F]{6})'`))
  assert.ok(match, `FLOW.${name} em charts.jsx`)
  return match[1].toLowerCase()
}

function cssBlock(selector) {
  const start = css.indexOf(`${selector} {`)
  assert.ok(start >= 0, `bloco ${selector}`)
  return css.slice(start, css.indexOf('}', start))
}

function cssHex(block, name) {
  const match = block.match(new RegExp(`--${name}:\\s*(\\d+)\\s+(\\d+)\\s+(\\d+);`))
  assert.ok(match, `--${name}`)
  return match.slice(1).map((part) => Number(part).toString(16).padStart(2, '0')).join('')
}

test('FLOW e SERIES[0] de charts.jsx = as variaveis de index.css, nos dois temas', () => {
  const series = charts.match(/export const SERIES = \['#([0-9a-fA-F]{6})'/)
  assert.ok(series, 'SERIES em charts.jsx')
  const expected = {
    'flow-income': hexOf('income'),
    'flow-expense': hexOf('expense'),
    'flow-investment': hexOf('investment'),
    'flow-others': hexOf('others'),
    'series-0': series[1].toLowerCase(),
  }
  for (const selector of [':root', ':root.dark']) {
    const block = cssBlock(selector)
    for (const [name, hex] of Object.entries(expected)) {
      assert.equal(cssHex(block, name), hex, `--${name} em ${selector}`)
    }
  }
})
