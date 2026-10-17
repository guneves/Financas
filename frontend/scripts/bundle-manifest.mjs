// Grava <pasta>/bundle.json no build do APK: a versao da tela que o app baixa do
// servidor (mobile-docs/steps-to-production.md, "A tela se atualiza sozinha").
//
//   node scripts/bundle-manifest.mjs dist-android https://servidor
//
// - version: os 16 primeiros hex do SHA-256 do conteudo (caminho + bytes de cada
//   arquivo, em ordem). Mesmo codigo, mesma versao: o build do APK e o da imagem
//   chegam ao mesmo valor, e o celular nao baixa o que ja tem.
// - native_level: frontend/native-level.txt. A tela so vai para um APK do mesmo
//   nivel; mudou o Java, o plugin ou o Capacitor, sobe o numero e gera o APK de novo.
// - api_base: o endereco da API compilado nesta tela (VITE_API_BASE_URL). O app
//   recusa uma tela que fale com outro servidor.
import { createHash } from 'node:crypto'
import { readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const MANIFEST = 'bundle.json'

function listFiles(dir) {
  const files = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) files.push(...listFiles(path))
    else if (entry.isFile()) files.push(path)
  }
  return files
}

const [dir, apiBase] = process.argv.slice(2)
if (!dir || !apiBase || !/^https:\/\//.test(apiBase)) {
  console.error('Uso: node scripts/bundle-manifest.mjs <pasta do build> <https://endereco-da-api>')
  process.exit(1)
}

const nativeLevel = Number.parseInt(
  readFileSync(fileURLToPath(new URL('../native-level.txt', import.meta.url)), 'utf8').trim(),
  10,
)
if (!Number.isInteger(nativeLevel) || nativeLevel < 1) {
  console.error('native-level.txt precisa de um inteiro >= 1.')
  process.exit(1)
}

const hash = createHash('sha256')
const paths = listFiles(dir)
  .map((path) => relative(dir, path).split(sep).join('/'))
  .filter((path) => path !== MANIFEST)
  .sort()
for (const path of paths) {
  const bytes = readFileSync(join(dir, path))
  hash.update(`${path}\0${bytes.length}\0`)
  hash.update(bytes)
}

const manifest = {
  version: hash.digest('hex').slice(0, 16),
  native_level: nativeLevel,
  api_base: apiBase.replace(/\/+$/, ''),
}
writeFileSync(join(dir, MANIFEST), `${JSON.stringify(manifest, null, 2)}\n`)
console.log(`Tela ${manifest.version} (nivel nativo ${nativeLevel}, ${paths.length} arquivos)`)
