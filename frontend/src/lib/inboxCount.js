// Quantos itens esperam em Lançamentos › Aprovar: o contador do cabecalho e da
// aba. Rele a cada minuto com a tela na frente, e ao voltar para ela: uma
// decisao tomada no outro aparelho some daqui sem recarregar. Sem servidor, 0
// (o contador some; nada a aprovar offline).
import { inboxApi } from './dataApi'
import { useQuery } from './queries'

export function useInboxCount() {
  const query = useQuery({
    queryKey: ['aprovar', 'contagem'],
    queryFn: () => inboxApi.count(),
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
    retry: 0,
  })
  return Number(query.data?.pending_count) || 0
}
