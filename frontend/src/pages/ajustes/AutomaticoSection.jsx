import { AlertMessage, EmptyState, ListSkeleton, Panel, PanelHeader } from '../../components/ui'
import { shownDecisions } from '../../lib/autoDecisions'
import { reviewApi } from '../../lib/dataApi'
import { queryErrorMessage, useQuery } from '../../lib/queries'
import AutoDecisionList from './AutoDecisionList'

const KEY = ['review', 'automatic']

// Decidido sozinho (dono, 2026-11-18: "tudo automatico"): o que o app antes
// perguntava e agora decide por uma regra escrita — a categoria da Pluggy, a
// ponta so da Corretora, o cambio sem a PTAX do dia, o conflito com o banco, a
// carteira (a confirmacao automatica fica de fora: shownDecisions). Cada uma com "Desfazer"; desfeita, a
// regra nao decide de novo aquele lancamento.
export default function AutomaticoSection() {
  const query = useQuery({ queryKey: KEY, queryFn: () => reviewApi.automatic() })
  const items = shownDecisions(query.data?.items)

  return (
    <Panel id="automatico" className="scroll-mt-20 lg:scroll-mt-8">
      <PanelHeader
        title="Decidido sozinho"
        description="O que o app resolveu sem perguntar. Desfazer devolve a linha como era e a regra não volta a mexer nela."
      />
      <div className="p-5">
        {query.isError ? (
          <AlertMessage message={queryErrorMessage(query, 'Não foi possível ler as decisões automáticas.')} className="mb-4" />
        ) : null}
        {query.isLoading ? <ListSkeleton rows={3} /> : items.length === 0 ? (
          <EmptyState title="Nada decidido sozinho ainda" message="Quando o app resolver algo por você, aparece aqui." />
        ) : <AutoDecisionList items={items} />}
      </div>
    </Panel>
  )
}
