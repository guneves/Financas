import { Monitor, Moon, Sun } from 'lucide-react'
import { Panel, PanelHeader, SegmentedControl } from '../../components/ui'
import { setThemePreference, useThemePreference } from '../../lib/theme'

const THEME_OPTIONS = [
  { value: 'system', label: 'Sistema', icon: Monitor },
  { value: 'light', label: 'Claro', icon: Sun },
  { value: 'dark', label: 'Escuro', icon: Moon },
]

// Tema claro/escuro (lib/theme.js). Vale para este aparelho; "Sistema" segue o
// tema do celular ou do computador.
export default function AparenciaSection() {
  const preference = useThemePreference()
  return (
    <Panel id="aparencia" className="scroll-mt-20 lg:scroll-mt-8">
      <PanelHeader title="Aparência" description="Tema do app neste aparelho. Sistema segue o tema do celular ou do computador." />
      <div className="p-5">
        <SegmentedControl items={THEME_OPTIONS} value={preference} onChange={setThemePreference} />
      </div>
    </Panel>
  )
}
