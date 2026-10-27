// A fila de Revisar (045, GET /api/review): o que gravou sozinho e espera o
// dono, e quantos movimentos ficaram no Aprovar (`waiting`). Rele a cada
// minuto com a tela na frente e ao voltar para ela, como o contador do Aprovar.
// A chave comeca com 'lancamentos': gravar algo a invalida (lib/queries.js).
import { reviewApi } from './dataApi'
import { useQuery } from './queries'

const EMPTY = { items: [], count: 0, waiting: 0 }

export function useReviewQueue() {
  const query = useQuery({
    queryKey: ['lancamentos', 'revisar'],
    queryFn: () => reviewApi.list(),
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
    retry: 0,
  })
  return { ...EMPTY, ...(query.data || {}), loading: query.isLoading }
}
