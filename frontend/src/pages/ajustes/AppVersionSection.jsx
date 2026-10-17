import { useEffect, useState } from 'react'
import { RefreshCw, RotateCcw, Smartphone } from 'lucide-react'
import { ApkUpdatePrompt } from '../../components/ApkUpdateBanner'
import { AlertMessage, Badge, Button, Panel, PanelHeader } from '../../components/ui'
import {
  appBundleInfo,
  applyAppBundle,
  checkForUpdate,
  getApkState,
  getLastCheck,
  isAppBundleAvailable,
  resetAppBundle,
  subscribeAppBundle,
} from '../../lib/appBundle'
import { checkStatusMessage, shortVersion } from '../../lib/appBundleRules'
import { confirmAction } from '../../lib/confirm'

// Versao do app, so no APK: o APK instalado e a tela em uso — a que veio nele ou
// uma baixada do servidor (lib/appBundle.js). Daqui se procura atualizacao, se
// troca na hora e se volta para a tela do APK se a baixada estiver ruim. O APK
// novo publicado pelo CI aparece aqui tambem ("Nova versão disponível").
export default function AppVersionSection() {
  if (!isAppBundleAvailable()) return null
  return <AppVersionPanel />
}

function AppVersionPanel() {
  const [info, setInfo] = useState(null)
  const [lastCheck, setLastCheck] = useState(getLastCheck())
  const [apk, setApk] = useState(getApkState())
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  const reloadInfo = () => appBundleInfo().then(setInfo).catch((err) => setError(err?.message || 'Versão indisponível.'))

  useEffect(() => {
    reloadInfo()
    return subscribeAppBundle((result) => {
      setLastCheck(result)
      setApk(getApkState())
      reloadInfo()
    })
  }, [])

  const run = async (name, action) => {
    setBusy(name)
    setError('')
    try {
      await action()
    } catch (err) {
      setError(err?.message || 'Não foi possível concluir.')
    } finally {
      setBusy('')
    }
  }

  const handleReset = async () => {
    const ok = await confirmAction({
      title: 'Voltar à versão do APK?',
      message: 'O app recarrega com a tela que veio no APK. A versão baixada em uso não será baixada de novo; a próxima que o servidor publicar, sim.',
      confirmLabel: 'Voltar',
      tone: 'neutral',
    })
    if (ok) await run('reset', resetAppBundle)
  }

  const status = checkStatusMessage(lastCheck)
  const staged = info?.staged

  return (
    <Panel id="versao" className="scroll-mt-20 lg:scroll-mt-8">
      <PanelHeader
        title="Versão do app"
        description="A tela se atualiza sozinha pelo servidor; um APK novo só é preciso quando o servidor pede."
        actions={(
          <Button variant="secondary" size="sm" icon={RefreshCw} loading={busy === 'check'} onClick={() => run('check', checkForUpdate)}>
            Verificar atualizações
          </Button>
        )}
      />
      <div className="space-y-4 p-5">
        <AlertMessage message={error} onDismiss={() => setError('')} />
        <ApkUpdatePrompt />
        {status ? <AlertMessage tone={status.tone} message={status.text} /> : null}
        {info ? (
          <ul className="divide-y divide-zinc-100 rounded-2xl border border-zinc-200">
            <li className="flex flex-wrap items-center gap-3 p-3">
              <Smartphone className="h-4 w-4 shrink-0 text-zinc-400" aria-hidden="true" />
              <div className="min-w-[12rem] flex-1">
                <p className="text-sm font-semibold text-zinc-900">APK</p>
                <p className="text-xs text-zinc-500">{info.apkVersion || '—'} · nível nativo {info.nativeLevel}</p>
                {apk?.latest && !apk.newer ? <p className="text-xs text-zinc-500">É o mais novo publicado.</p> : null}
              </div>
            </li>
            <li className="flex flex-wrap items-center gap-3 p-3">
              <RefreshCw className="h-4 w-4 shrink-0 text-zinc-400" aria-hidden="true" />
              <div className="min-w-[12rem] flex-1">
                <p className="text-sm font-semibold text-zinc-900">Tela</p>
                <p className="text-xs text-zinc-500 tabular">
                  {shortVersion(info.running)} · {info.onBuiltin ? 'a que veio no APK' : 'baixada do servidor'}
                </p>
              </div>
              {info.inTrial ? <Badge tone="warning">Em teste</Badge> : null}
            </li>
          </ul>
        ) : null}
        <div className="flex flex-wrap gap-2">
          {staged ? (
            <Button size="sm" icon={RefreshCw} loading={busy === 'apply'} onClick={() => run('apply', applyAppBundle)}>
              {staged === 'builtin' ? 'Voltar à tela do APK agora' : 'Reiniciar agora'}
            </Button>
          ) : null}
          {info && !info.onBuiltin ? (
            <Button variant="secondary" size="sm" icon={RotateCcw} loading={busy === 'reset'} onClick={handleReset}>
              Voltar à versão do APK
            </Button>
          ) : null}
        </div>
      </div>
    </Panel>
  )
}
