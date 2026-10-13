import { useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { accountsApi } from '../lib/dataApi'
import { useQuery } from '../lib/queries'
import { pickDefaultAccountId } from '../pages/lancamentos/helpers'
import { Field, cx } from './ui'

// Uma operacao de investimento so vai para o Extrato quando o dono pede, por
// operacao: a conta escolhida viaja em `metadata.cash_account_id` e o backend
// cria (ou tira) o lancamento ligado. O valor do campo e { enabled, accountId }.
export const emptyCashLink = () => ({ enabled: false, accountId: '' })

export function cashLinkFromMetadata(metadata) {
  const accountId = typeof metadata?.cash_account_id === 'string' ? metadata.cash_account_id.trim() : ''
  return { enabled: Boolean(accountId), accountId }
}

// O pedaco do metadata. Ao criar, sem a caixa marcada a chave nem vai. Ao
// editar (`explicit`) ela vai sempre: um PATCH sem a chave mantem o vinculo
// que a operacao ja tinha, e so `null` o desfaz.
export function cashLinkMetadata(value, { explicit = false } = {}) {
  const accountId = value?.enabled ? String(value.accountId || '') : ''
  if (accountId) return { cash_account_id: accountId }
  return explicit ? { cash_account_id: null } : {}
}

const HINTS = {
  BUY: 'Cria uma saída deste valor na conta escolhida. Deixe desmarcado se o débito já está no extrato (importado ou lançado à mão).',
  SELL: 'Cria uma entrada do valor líquido na conta escolhida.',
  // No resgate o lancamento e o valor resgatado menos os custos: o IR da
  // renda fixa e estimado na carteira, nao descontado aqui.
  REDEMPTION: 'Cria uma entrada do valor resgatado, menos os custos, na conta escolhida. O IR retido na fonte não é descontado.',
}

const NO_ACCOUNTS = []

// O lancamento ligado e sempre em reais.
const isBrlAccount = (account) => !account.currency || String(account.currency).toUpperCase() === 'BRL'

// Caixa "Lançar no extrato" + conta, compartilhada pelo lancamento, pela
// edicao em Operacoes e pelo resgate em Posicao. Desmarcada por padrao.
// `savedAccountId` e a conta ja gravada na operacao que esta sendo editada.
export default function CashLinkField({
  value,
  onChange,
  movementType = 'BUY',
  foreign = false,
  savedAccountId = '',
  enabled = true,
  selectClassName = 'app-select h-11',
  className = '',
}) {
  const accountsQuery = useQuery({ queryKey: ['contas', 'ativas'], queryFn: () => accountsApi.list(), enabled })
  const accounts = useMemo(() => (accountsQuery.data || NO_ACCOUNTS).filter(isBrlAccount), [accountsQuery.data])
  const defaultAccountId = useMemo(() => pickDefaultAccountId(accounts), [accounts])

  // Conta gravada que saiu da lista (arquivada depois): continua escolhida,
  // senao salvar a edicao trocaria a conta do lancamento sem ninguem pedir.
  const savedIsMissing = Boolean(savedAccountId)
    && accountsQuery.isSuccess
    && !accounts.some((account) => account.id === savedAccountId)
  const allAccountsQuery = useQuery({
    queryKey: ['contas', 'todas'],
    queryFn: () => accountsApi.list({ include_archived: 1 }),
    enabled: enabled && savedIsMissing,
  })
  const options = useMemo(() => {
    if (!savedIsMissing) return accounts
    const saved = (allAccountsQuery.data || NO_ACCOUNTS).find((account) => account.id === savedAccountId)
    const name = saved ? `${saved.name}${saved.archived_at ? ' (arquivada)' : ''}` : 'Conta arquivada'
    return [...accounts, { id: savedAccountId, name }]
  }, [accounts, savedIsMissing, savedAccountId, allAccountsQuery.data])

  // Conta padrao assim que a lista chega (ou ja estava no cache).
  useEffect(() => {
    if (value.enabled && !value.accountId && defaultAccountId) {
      onChange({ ...value, accountId: defaultAccountId })
    }
  }, [value, defaultAccountId, onChange])

  const canLink = options.length > 0
  const hint = `${HINTS[movementType] || HINTS.BUY}${foreign ? ' O valor vai em reais, pelo câmbio da operação.' : ''}`

  return (
    <div className={cx('rounded-lg border border-zinc-200 px-4 py-3 text-sm', className)}>
      <label className={cx('flex items-start gap-3', canLink || value.enabled ? 'cursor-pointer' : 'cursor-not-allowed')}>
        <input
          type="checkbox"
          checked={value.enabled}
          disabled={!canLink && !value.enabled}
          onChange={(event) => onChange({
            enabled: event.target.checked,
            accountId: value.accountId || defaultAccountId,
          })}
          className="mt-0.5 h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500"
        />
        <span>
          <span className="block font-medium text-zinc-800">Lançar no extrato</span>
          <span className="block text-zinc-600">{hint}</span>
        </span>
      </label>

      {value.enabled ? (
        <Field label="Conta" className="mt-3">
          <select
            value={value.accountId}
            onChange={(event) => onChange({ ...value, accountId: event.target.value })}
            className={selectClassName}
            required
          >
            {options.some((account) => account.id === value.accountId) ? null : <option value="">Selecione...</option>}
            {options.map((account) => (
              <option key={account.id} value={account.id}>{account.name}</option>
            ))}
          </select>
        </Field>
      ) : null}

      {accountsQuery.error ? (
        <p className="mt-2 text-zinc-600">Não foi possível carregar as contas.</p>
      ) : accountsQuery.isSuccess && !canLink ? (
        <p className="mt-2 text-zinc-600">
          Nenhuma conta em reais.{' '}
          <Link to="/ajustes#contas" className="font-semibold text-emerald-700 underline-offset-2 hover:underline">
            Cadastre em Ajustes › Contas
          </Link>.
        </p>
      ) : null}
    </div>
  )
}
