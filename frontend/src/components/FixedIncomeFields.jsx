import { Field } from './ui'
import {
  FIXED_INCOME_TYPES,
  INDEXERS,
  RATE_MODES,
  isTaxFreeFixedIncomeType,
  rateFieldLabel,
  rateFieldsForMode,
  rateModeOf,
  ratePlaceholder,
} from '../lib/fixedIncome'

// Campos de renda fixa compartilhados pelo lancamento e pela edicao.
// `value` tem o formato de emptyFixedIncomeForm(); `onChange` recebe o objeto inteiro.
// A isencao de IR nao e um campo: segue o tipo do titulo (isTaxFreeFixedIncomeType).
export default function FixedIncomeFields({ value, onChange, inputClassName = 'app-input h-11', selectClassName = 'app-select h-11' }) {
  const update = (patch) => onChange({ ...value, ...patch })
  const rateMode = rateModeOf(value)
  const isTaxFree = isTaxFreeFixedIncomeType(value.fixed_income_type)

  return (
    <>
      <Field label="Tipo de título">
        <select
          value={value.fixed_income_type}
          onChange={(event) => update({ fixed_income_type: event.target.value })}
          className={selectClassName}
          required
        >
          {!value.fixed_income_type ? <option value="">Selecionar</option> : null}
          {FIXED_INCOME_TYPES.map((type) => (
            <option key={type.value} value={type.value}>{type.label}</option>
          ))}
        </select>
      </Field>

      <Field label="Rentabilidade">
        <select
          value={rateMode}
          onChange={(event) => update({ ...rateFieldsForMode(event.target.value), rate: '' })}
          className={selectClassName}
        >
          {RATE_MODES.map((mode) => (
            <option key={mode.value} value={mode.value}>{mode.label}</option>
          ))}
        </select>
      </Field>

      {rateMode === 'POS' ? (
        <Field label="Indexador">
          <select
            value={value.indexer}
            onChange={(event) => update({ indexer: event.target.value, rate: '' })}
            className={selectClassName}
          >
            {INDEXERS.map((indexer) => (
              <option key={indexer.value} value={indexer.value}>{indexer.label}</option>
            ))}
          </select>
        </Field>
      ) : null}

      <Field label={rateFieldLabel(value.rate_type, value.indexer)}>
        <input
          type="number"
          min="0"
          step="0.01"
          inputMode="decimal"
          value={value.rate}
          onChange={(event) => update({ rate: event.target.value })}
          placeholder={ratePlaceholder(value.rate_type, value.indexer)}
          className={inputClassName}
          required
        />
      </Field>

      <Field label="Imposto de renda">
        <p className="flex min-h-11 items-center rounded-lg border border-zinc-200 px-4 text-sm font-medium text-zinc-700">
          {!value.fixed_income_type
            ? 'Definido pelo tipo do título'
            : isTaxFree ? 'Isento de IR' : 'Tributado (tabela regressiva)'}
        </p>
      </Field>
    </>
  )
}
