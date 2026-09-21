import Operacoes from './investimentos/Operacoes'
import Posicao from './investimentos/Posicao'

// Ponto de entrada das rotas /investimentos/posicao e /investimentos/operacoes.
// A aba vem da rota (App.jsx); Proventos tem pagina propria.
export default function Investments({ tab = 'posicao' }) {
  return tab === 'operacoes' ? <Operacoes /> : <Posicao />
}
