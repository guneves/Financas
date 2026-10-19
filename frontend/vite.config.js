import { createHash } from 'node:crypto'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Hash do src/: muda so quando as telas mudam, entao o bundle do APK (versao
// por conteudo) nao vira outro a cada deploy.
function sourceHash(dir) {
  const hash = createHash('sha256')
  const walk = (current) => {
    for (const entry of readdirSync(current, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const path = join(current, entry.name)
      if (entry.isDirectory()) walk(path)
      else hash.update(entry.name).update(readFileSync(path))
    }
  }
  walk(dir)
  return hash.digest('hex').slice(0, 16)
}

export default defineConfig({
  plugins: [react()],
  define: {
    // O cache de leitura salvo no aparelho (lib/queryPersist.js) so volta com
    // as mesmas telas: uma tela nova pode nao entender uma resposta velha.
    'import.meta.env.VITE_BUILD_ID': JSON.stringify(sourceHash(fileURLToPath(new URL('./src', import.meta.url)))),
  },
})
