import { useEffect, useState } from 'react'
import { Download } from 'lucide-react'
import {
  getApkInstall,
  getApkState,
  getLastCheck,
  installApk,
  isAppBundleAvailable,
  subscribeAppBundle,
} from '../lib/appBundle'
import { apkPrompt, installStatusMessage } from '../lib/appBundleRules'
import { AlertMessage, Button } from './ui'

// "Nova versão disponível", so no APK e so quando o CI publicou um APK mais novo
// que o instalado (lib/appBundle.js). Tocar baixa e abre o instalador do Android.
export default function ApkUpdateBanner({ className = '' }) {
  if (!isAppBundleAvailable()) return null
  return <ApkUpdatePrompt className={className} />
}

function useApkUpdate() {
  const read = () => ({ apk: getApkState(), bundle: getLastCheck(), install: getApkInstall() })
  const [state, setState] = useState(read)
  useEffect(() => subscribeAppBundle(() => setState(read())), [])
  return state
}

export function ApkUpdatePrompt({ className = '' }) {
  const { apk, bundle, install } = useApkUpdate()
  const [busy, setBusy] = useState(false)
  const prompt = apkPrompt({ apk, bundle })
  if (!prompt) return null
  const status = installStatusMessage(install)

  const handleInstall = async () => {
    setBusy(true)
    try {
      await installApk()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={className}>
      <AlertMessage tone={prompt.required ? 'warning' : 'info'}>
        <div className="flex flex-wrap items-center gap-3">
          <p className="min-w-[12rem] flex-1">
            <span className="font-semibold">Nova versão disponível</span>
            {' '}({prompt.versionName}).
            {prompt.required ? ' A tela nova precisa dela para atualizar.' : null}
          </p>
          <Button size="sm" icon={Download} loading={busy} onClick={handleInstall}>
            Instalar
          </Button>
        </div>
        {status ? <p className="mt-2 text-xs">{status.text}</p> : null}
      </AlertMessage>
    </div>
  )
}
