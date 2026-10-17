import { useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { accountsApi } from '../lib/dataApi'
import { useQuery } from '../lib/queries'
import { pickPortfolioAccountId, portfolioAccounts } from '../lib/portfolioAccount'
import { Field, cx } from './ui'

// A regra mora em lib/portfolioAccount.js: toda operacao sai da conta da
// carteira (uma conta Corretora) e vai para o Extrato nela, a nao ser que o dono
// marque "Não descontar de nenhuma conta". A conta viaja em
// `metadata.cash_account_id` e o backend cria (ou tira) o lancamento ligado.
export { cashLinkFromMetadata, cashLinkMetadata, emptyCashLink } from '../lib/portfolioAccount'

const HINTS = {
  BUY: 'O valor sai desta conta.',
  SELL: 'O valor líquido entra nesta conta.',
  // No resgate o lancamento e o valor resgatado menos os custos: o IR da
  // renda fixa e estimado na carteira, nao descontado aqui.
  REDEMPTION: 'O valor resgatado, menos os custos, entra nesta conta. O IR retido na fonte não é descontado.',
}

const NO_ACCOUNTS = []

// Conta da carteira + a marca "Não descontar de nenhuma conta", compartilhada
// pelo lancamento, pela edicao em Operacoes e pelo resgate em Posicao.
// `savedAccountId` e a conta ja gravada na operacao que esta sendo editada.
export default function CashLinkField({
  value,
  onChange,
  movementType = 'BUY',
  savedAccountId = '',
  enabled = true,
  selectClassName = 'app-select h-11',
  className = '',
}) {
  const accountsQuery = useQuery({ queryKey: ['contas', 'ativas'], queryFn: () => accountsApi.list(), enabled })
  const accounts = accountsQuery.data || NO_ACCOUNTS
  const portfolio = useMemo(() => portfolioAccounts(accounts), [accounts])
  const defaultAccountId = useMemo(() => pickPortfolioAccountId(accounts), [accounts])
  const missing = accountsQuery.isSuccess && portfolio.length === 0

  // A conta gravada numa operacao antiga pode nao ser da carteira (outra conta,
  // ou arquivada depois): continua escolhida, senao salvar a edicao trocaria a
  // conta do lancamento sem ninguem pedir.
  const savedIsMissing = Boolean(savedAccountId)
    && accountsQuery.isSuccess
    && !portfolio.some((account) => account.id === savedAccountId)
  const allAccountsQuery = useQuery({
    queryKey: ['contas', 'todas'],
    queryFn: () => accountsApi.list({ include_archived: 1 }),
    enabled: enabled && savedIsMissing,
  })
  const options = useMemo(() => {
    if (!savedIsMissing) return portfolio
    const saved = (allAccountsQuery.data || NO_ACCOUNTS).find((account) => account.id === savedAccountId)
    const name = saved ? `${saved.name}${saved.archived_at ? ' (arquivada)' : ''}` : 'Conta arquivada'
    return [...portfolio, { id: savedAccountId, name }]
  }, [portfolio, savedIsMissing, savedAccountId, allAccountsQuery.data])

  // A conta da carteira assim que a lista chega (ou ja estava no cache), e a
  // falta dela, que a operacao nova recusa (cashLinkMetadata).
  useEffect(() => {
    if (!accountsQuery.isSuccess) return
    const next = { ...value, missing }
    if (next.enabled && !next.accountId && defaultAccountId) next.accountId = defaultAccountId
    if (next.missing !== value.missing || next.accountId !== value.accountId) onChange(next)
  }, [value, missing, defaultAccountId, accountsQuery.isSuccess, onChange])

  const canLink = options.length > 0
  const hint = HINTS[movementType] || HINTS.BUY

  return (
    <div className={cx('space-y-3 rounded-lg border border-zinc-200 px-4 py-3 text-sm', className)}>
      {value.enabled && canLink ? (
        <Field label="Conta da carteira" hint={hint}>
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

      {missing ? (
        <p className="text-zinc-700">
          Nenhuma conta vinculada à carteira. Cadastre uma conta do tipo <strong>Corretora</strong>, em reais:
          as operações saem dela.{' '}
          <Link to="/ajustes#contas" className="font-semibold text-emerald-700 underline-offset-2 hover:underline">
            Ajustes › Contas
          </Link>
        </p>
      ) : null}

      <label className={cx('flex items-start gap-3', canLink || !value.enabled ? 'cursor-pointer' : 'cursor-not-allowed')}>
        <input
          type="checkbox"
          checked={!value.enabled}
          disabled={!canLink && !value.enabled}
          onChange={(event) => onChange({
            ...value,
            enabled: !event.target.checked,
            accountId: value.accountId || defaultAccountId,
          })}
          className="mt-0.5 h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500"
        />
        <span>
          <span className="block font-medium text-zinc-800">Não descontar de nenhuma conta</span>
          <span className="block text-zinc-600">
            A operação entra na carteira sem mexer em saldo. Use quando o dinheiro já está no extrato (importado ou lançado à mão).
          </span>
        </span>
      </label>

      {accountsQuery.error ? <p className="text-zinc-600">Não foi possível carregar as contas.</p> : null}
    </div>
  )
}
