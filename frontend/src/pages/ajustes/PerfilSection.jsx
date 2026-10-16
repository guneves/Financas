import { useState } from 'react'
import { LogOut, Save } from 'lucide-react'
import { displayName, getCurrentUser, signOut, updateUsername } from '../../lib/auth'
import { maskEmail } from '../../lib/format'
import { AlertMessage, Button, Field, Panel, PanelHeader } from '../../components/ui'

// Perfil: nome de usuario exibido no app e a saida da sessao. O e-mail so
// aparece aqui, mascarado (maskEmail), como informacao de login.
export default function PerfilSection() {
  const user = getCurrentUser()
  const [username, setUsername] = useState(user?.username || '')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null)

  const trimmed = username.trim()
  const unchanged = trimmed === (user?.username || '')

  const handleSubmit = async (event) => {
    event.preventDefault()
    setSaving(true)
    setMessage(null)
    try {
      const updated = await updateUsername(trimmed)
      setUsername(updated.username || '')
      setMessage({ tone: 'success', text: 'Nome de usuário atualizado.' })
    } catch (error) {
      setMessage({ tone: 'danger', text: error.message || 'Não foi possível salvar o nome.' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Panel id="perfil" className="scroll-mt-20 lg:scroll-mt-8">
      <PanelHeader title="Perfil" description="Nome exibido no app e conta conectada neste navegador." />
      <div className="space-y-4 p-5">
        {!user?.username ? (
          <AlertMessage tone="info" message="Sua conta ainda não tem nome de usuário. Escolha um abaixo." />
        ) : null}
        <AlertMessage tone={message?.tone} message={message?.text} onDismiss={() => setMessage(null)} />

        <form onSubmit={handleSubmit} className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <Field label="Nome de usuário" className="flex-1" hint="De 2 a 40 caracteres. Não pode ser um e-mail.">
            <input
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="app-input"
              placeholder={displayName(null)}
              required
              minLength={2}
              maxLength={40}
            />
          </Field>
          <Button type="submit" icon={Save} loading={saving} disabled={unchanged || trimmed.length < 2} className="sm:mb-6">
            Salvar
          </Button>
        </form>

        <div className="flex flex-col gap-3 border-t border-zinc-100 pt-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">E-mail de acesso</p>
            <p className="truncate text-sm font-semibold text-zinc-900">{maskEmail(user?.email)}</p>
          </div>
          <Button variant="danger" icon={LogOut} onClick={signOut}>Sair</Button>
        </div>
      </div>
    </Panel>
  )
}
