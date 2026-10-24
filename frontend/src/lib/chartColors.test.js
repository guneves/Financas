// node --test src/lib   (npm test em frontend/)
// As cores dos graficos moram em index.css (--flow-*, --series-0..7):
// components/charts.jsx (FLOW e SERIES, que o recharts usa) as referencia, e as
// telas nativas leem os mesmos valores (android/.../ui/theme/Tokens.kt,
// TokensTest). Este teste fixa a paleta, igual nos dois temas, e que charts.jsx
// so aponta para as variaveis.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const charts = readFileSync(new URL('../components/charts.jsx', import.meta.url), 'utf8')
const css = readFileSync(new URL('../index.css', import.meta.url), 'utf8')

// A paleta validada para daltonismo, na ordem fixa (a cor segue a entidade).
const PALETTE = {
  'series-0': '2a78d6',
  'series-1': 'eb6834',
  'series-2': '1baf7a',
  'series-3': 'eda100',
  'series-4': 'e87ba4',
  'series-5': '008300',
  'series-6': '4a3aa7',
  'series-7': 'e34948',
  'flow-income': '1baf7a',
  'flow-expense': 'e34948',
  'flow-investment': '2a78d6',
  'flow-others': 'eda100',
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

test('a paleta dos graficos em index.css, a mesma nos dois temas', () => {
  for (const selector of [':root', ':root.dark']) {
    const block = cssBlock(selector)
    for (const [name, hex] of Object.entries(PALETTE)) {
      assert.equal(cssHex(block, name), hex, `--${name} em ${selector}`)
    }
  }
})

test('FLOW e SERIES de charts.jsx apontam para as variaveis, sem hex proprio', () => {
  assert.match(charts, /export const SERIES = Array\.from\(\{ length: 8 \}, \(_, index\) => `rgb\(var\(--series-\$\{index\}\)\)`\)/)
  for (const key of ['income', 'expense', 'investment', 'others']) {
    assert.match(charts, new RegExp(`\\b${key}: 'rgb\\(var\\(--flow-${key}\\)\\)'`), `FLOW.${key}`)
  }
  const flowAndSeries = charts.slice(charts.indexOf('export const SERIES'), charts.indexOf('export const CHART'))
  assert.doesNotMatch(flowAndSeries, /'#[0-9a-fA-F]{6}'/)
})
