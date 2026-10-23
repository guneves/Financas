import { useCallback, useEffect, useState } from 'react'
import { Bell, FileJson, FileText, RefreshCw, Settings2, Trash2 } from 'lucide-react'
import {
  AlertMessage,
  Badge,
  Button,
  Collapsible,
  ListSkeleton,
  Panel,
  PanelHeader,
  SegmentedControl,
} from '../../components/ui'
import { confirmAction } from '../../lib/confirm'
import {
  clearCapture,
  exportCapture,
  getNotifyStatus,
  isNotifyAvailable,
  latestCaptured,
  openAccessSettings,
  openAppDetails,
  setCapture,
  subscribeNotify,
} from '../../lib/notifyCapture'
import {
  ADB_TEST_COMMAND,
  accessMessage,
  appRows,
  captureMessage,
  countLabel,
  formatStamp,
  installerLabel,
  listenerMessage,
  showsRestrictedHelp,
} from '../../lib/notifyRules'
import { toast } from '../../lib/toast'

const CAPTURE_ITEMS = [
  { value: 'off', label: 'Desligada' },
  { value: 'on', label: 'Ligada' },
]

// Notificacoes dos bancos, so no APK (lib/notifyCapture.js): o acesso que o Android
// precisa dar, a captura (os textos de verdade, para escrever os leitores de cada
// banco), o que ela guardou e a exportacao. Nada daqui vai ao servidor.
export default function NotificacoesSection() {
  if (!isNotifyAvailable()) return null
  return <NotificacoesPanel />
}

function NotificacoesPanel() {
  const [status, setStatus] = useState(null)
  const [latest, setLatest] = useState([])
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  const reload = useCallback(async () => {
    try {
      const [nextStatus, nextLatest] = await Promise.all([getNotifyStatus(), latestCaptured(20)])
      setStatus(nextStatus)
      setLatest(nextLatest)
    } catch (err) {
      setError(err?.message || 'Não foi possível ler o leitor de notificações.')
    }
  }, [])

  useEffect(() => {
    reload()
    return subscribeNotify(reload)
  }, [reload])

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

  const handleCapture = (value) => run('capture', async () => {
    const on = value === 'on'
    if (on === status?.captureOn) return
    setStatus(await setCapture(on))
    toast(on ? 'Captura ligada.' : 'Captura desligada. O que já foi guardado continua aqui.')
  })

  const handleExport = (format) => run(`export-${format}`, async () => {
    const { count } = await exportCapture(format)
    toast(`${countLabel(count)} no arquivo. Escolha onde guardar.`)
  })

  const handleClear = async () => {
    const ok = await confirmAction({
      title: 'Apagar as notificações capturadas?',
      message: `${countLabel(status?.total)} saem deste aparelho para sempre. Exporte antes se ainda for usá-las. A captura continua ${status?.captureOn ? 'ligada' : 'desligada'}.`,
      confirmLabel: 'Apagar',
    })
    if (!ok) return
    await run('clear', async () => {
      setStatus(await clearCapture())
      setLatest([])
      toast('Capturas apagadas.')
    })
  }

  const access = accessMessage(status)
  const listener = listenerMessage(status)
  const total = Number(status?.total) || 0

  return (
    <Panel id="notificacoes" className="scroll-mt-20 lg:scroll-mt-8">
      <PanelHeader
        title="Notificações dos bancos"
        description="O app ouve o Samsung Wallet, a Flash e os apps do Itaú, BB e BTG. Cada notificação com valor vira um item em Aprovar: só os campos lidos (valor, loja, cartão) vão ao servidor, nunca o texto. O modo de captura guarda os textos no celular, para exportar."
        actions={(
          <Button variant="secondary" size="sm" icon={RefreshCw} onClick={() => run('reload', reload)} loading={busy === 'reload'}>
            Atualizar
          </Button>
        )}
      />
      <div className="space-y-4 p-5">
        <AlertMessage message={error} onDismiss={() => setError('')} />
        {!status ? (error ? null : <ListSkeleton rows={3} />) : (
          <>
            <section className="space-y-3" aria-label="Acesso às notificações">
              <AlertMessage tone={access.tone} message={access.text} />
              {listener ? <p className="text-xs text-zinc-500">{listener}</p> : null}
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant={status.granted ? 'secondary' : 'primary'} icon={Bell} onClick={() => run('access', openAccessSettings)}>
                  Abrir acesso às notificações
                </Button>
              </div>
              <Collapsible
                key={showsRestrictedHelp(status) ? 'restricted-open' : 'restricted-closed'}
                label="O Android diz “Configuração restrita”?"
                defaultOpen={showsRestrictedHelp(status)}
                variant="secondary"
                size="sm"
              >
                <RestrictedSettingsHelp installer={status.installer} onOpenAppDetails={() => run('details', openAppDetails)} />
              </Collapsible>
            </section>

            <section className="space-y-3 border-t border-zinc-100 pt-4" aria-label="Captura">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-[12rem] flex-1">
                  <p className="text-sm font-semibold text-zinc-900">Modo captura</p>
                  <p className="text-xs text-zinc-500">{captureMessage(status)}</p>
                </div>
                <SegmentedControl items={CAPTURE_ITEMS} value={status.captureOn ? 'on' : 'off'} onChange={handleCapture} />
              </div>
              <p className="text-xs text-zinc-500">
                Cada notificação desses apps fica guardada palavra por palavra, só neste aparelho. Ela sai daqui
                apenas quando você exporta; nada vai para o servidor.
              </p>
              {status.acceptsShell ? (
                <AlertMessage tone="info">
                  <p>APK de teste: também guarda notificações postadas pelo adb. Para testar sem uma compra:</p>
                  <code className="mt-2 block select-all break-all rounded-lg bg-white px-2 py-1.5 text-xs font-normal text-zinc-800">
                    {ADB_TEST_COMMAND}
                  </code>
                </AlertMessage>
              ) : null}
              <ul className="divide-y divide-zinc-100 rounded-2xl border border-zinc-200">
                {appRows(status).map((app) => (
                  <li key={app.package} className="flex flex-wrap items-center gap-3 p-3">
                    <div className="min-w-[10rem] flex-1">
                      <p className="text-sm font-semibold text-zinc-900">{app.label}</p>
                      <p className="break-all text-xs text-zinc-500">{app.package}</p>
                    </div>
                    <span className="text-xs text-zinc-500 tabular">{app.detail}</span>
                  </li>
                ))}
              </ul>
            </section>

            {latest.length ? (
              <Collapsible label={`Últimas capturadas (${latest.length})`} variant="secondary" size="sm">
                <ul className="space-y-2">
                  {latest.map((item) => (
                    <li key={item.dedupKey} className="rounded-2xl border border-zinc-200 p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs font-semibold text-zinc-700">{item.app}</span>
                        <span className="text-xs text-zinc-500 tabular">{formatStamp(item.postedAt, { seconds: true })}</span>
                        {item.groupSummary ? <Badge>resumo</Badge> : null}
                        {item.via === 'active' ? <Badge>lida ao religar</Badge> : null}
                      </div>
                      {item.title ? <p className="mt-1 whitespace-pre-wrap break-words text-sm font-semibold text-zinc-900">{item.title}</p> : null}
                      {item.text ? <p className="mt-0.5 whitespace-pre-wrap break-words text-sm text-zinc-700">{item.text}</p> : null}
                    </li>
                  ))}
                </ul>
              </Collapsible>
            ) : null}

            <div className="flex flex-wrap gap-2 border-t border-zinc-100 pt-4">
              <Button size="sm" variant="secondary" icon={FileJson} disabled={!total} loading={busy === 'export-json'} onClick={() => handleExport('json')}>
                Exportar JSON
              </Button>
              <Button size="sm" variant="secondary" icon={FileText} disabled={!total} loading={busy === 'export-text'} onClick={() => handleExport('text')}>
                Exportar texto
              </Button>
              <Button size="sm" variant="danger" icon={Trash2} disabled={!total} loading={busy === 'clear'} onClick={handleClear}>
                Apagar capturas
              </Button>
            </div>
          </>
        )}
      </div>
    </Panel>
  )
}

function RestrictedSettingsHelp({ installer, onOpenAppDetails }) {
  return (
    <div className="space-y-3 rounded-2xl border border-zinc-200 p-4 text-sm text-zinc-700">
      <p>
        A partir do Android 13, um app instalado por um arquivo APK aberto no celular não recebe o acesso às
        notificações até você liberar. Para liberar:
      </p>
      <ol className="list-decimal space-y-1.5 pl-5">
        <li>
          Toque em “Abrir acesso às notificações” e tente ligar o Finanças uma vez. O Android recusa e avisa
          “Configuração restrita” — é essa tentativa que faz a opção do passo 2 aparecer.
        </li>
        <li>
          Abra as informações do app, toque no menu ⋮ no canto de cima e em “Permitir configurações restritas”.
          Confirme com a digital ou o PIN.
        </li>
        <li>Volte ao acesso às notificações e ligue o Finanças.</li>
      </ol>
      <p className="text-xs text-zinc-500">
        Este APK foi instalado por: {installerLabel(installer)}. Um APK instalado pelo cabo (adb install)
        normalmente não passa por isso.
      </p>
      <Button size="sm" variant="secondary" icon={Settings2} onClick={onOpenAppDetails}>
        Abrir informações do app
      </Button>
    </div>
  )
}
