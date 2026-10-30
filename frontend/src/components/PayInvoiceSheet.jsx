import { useEffect, useState } from 'react'
import { CheckCircle } from 'lucide-react'
import { AlertMessage, Button, Field, Sheet } from './ui'
import { formatCurrency } from '../lib/format'
import { useValuesHidden } from '../lib/privacy'
import { accountBalanceBrl, isPortfolioAccount } from '../lib/transactions'
import { withoutGlobal } from '../lib/globalAccount'

// Confirmacao do pagamento de fatura, com a conta de onde sai o dinheiro.
//
// `defaultAccountId` e a conta pre-selecionada. Com `allowPerCard`, a opcao
// vazia "Conta de cada cartao" deixa o servidor escolher por cartao: a do
// debito automatico, se houver, senao a conta padrao (POST pay-invoice sem
// account_id). Usado no Inicio, que paga as faturas de varios cartoes juntas.
export default function PayInvoiceSheet({
  open,
  onClose,
  title,
  description,
  total,
  accounts,
  defaultAccountId = '',
  allowPerCard = false,
  saving = false,
  error = '',
  onConfirm,
}) {
  // Modo privado: a conta aparece sem o saldo.
  const hidden = useValuesHidden()
  // Sem a Conta global: fatura nao sai de conta em dolar.
  const activeAccounts = withoutGlobal(accounts).filter((account) => !account.archived_at)
  const [accountId, setAccountId] = useState(defaultAccountId)

  useEffect(() => {
    if (open) setAccountId(defaultAccountId)
  }, [open, defaultAccountId])

  const selected = activeAccounts.find((account) => account.id === accountId)
  // Em reais, como a fatura (null = conta sem cambio hoje: nao da para comparar).
  // A Corretora nao mostra saldo fora de Investimentos: sem comparar aqui.
  const selectedBalance = selected && !isPortfolioAccount(selected) ? accountBalanceBrl(selected) : null
  const shortfall = selectedBalance !== null && selectedBalance < total

  return (
    <Sheet
      open={open}
      onClose={saving ? undefined : onClose}
      title={title}
      description={description}
      footer={(
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="secondary" onClick={onClose} disabled={saving}>Cancelar</Button>
          <Button type="button" icon={CheckCircle} loading={saving} onClick={() => onConfirm(accountId)}>
            Pagar {formatCurrency(total)}
          </Button>
        </div>
      )}
    >
      <div className="space-y-4">
        {/* Recusa do servidor: o aviso balanca no lugar. O wrapper leva o
            nudge (o AlertMessage ja tem a propria entrada); key repete a cada recusa nova. */}
        {error ? (
          <div key={error} className="animate-nudge">
            <AlertMessage message={error} />
          </div>
        ) : null}
        <Field
          label="Debitar da conta"
          hint={allowPerCard && !accountId
            ? 'Cada fatura sai da conta do débito automático do cartão, ou da conta padrão.'
            : undefined}
        >
          <select value={accountId} onChange={(event) => setAccountId(event.target.value)} className="app-select">
            {allowPerCard ? <option value="">Conta de cada cartão</option> : null}
            {activeAccounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}{account.is_default ? ' (padrão)' : ''}{hidden || isPortfolioAccount(account) || accountBalanceBrl(account) === null ? '' : ` · ${formatCurrency(accountBalanceBrl(account))}`}
              </option>
            ))}
          </select>
        </Field>
        {shortfall ? (
          <AlertMessage
            tone="warning"
            message={`O saldo de ${selected.name}${hidden ? '' : ` (${formatCurrency(selectedBalance)})`} não cobre a fatura; a conta ficará negativa.`}
          />
        ) : null}
      </div>
    </Sheet>
  )
}
