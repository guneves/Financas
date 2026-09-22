import { Field } from './ui'
import {
  FIXED_INCOME_TYPES,
  INDEXERS,
  RATE_TYPES,
  TAX_FREE_FIXED_INCOME_TYPES,
  rateFieldLabel,
  ratePlaceholder,
} from '../lib/fixedIncome'

// Campos de renda fixa compartilhados pelo lancamento e pela edicao.
// `value` tem o formato de emptyFixedIncomeForm(); `onChange` recebe o objeto inteiro.
export default function FixedIncomeFields({ value, onChange, inputClassName = 'app-input h-11', selectClassName = 'app-select h-11' }) {
  const update = (patch) => onChange({ ...value, ...patch })

  const handleTypeChange = (nextType) => {
    const wasTaxFreeType = TAX_FREE_FIXED_INCOME_TYPES.includes(value.fixed_income_type)
    const isTaxFreeType = TAX_FREE_FIXED_INCOME_TYPES.includes(nextType)
    update({
      fixed_income_type: nextType,
      // Segue o tipo quando ele define a isencao; senao preserva a escolha manual.
      is_tax_free: isTaxFreeType ? true : wasTaxFreeType ? false : value.is_tax_free,
    })
  }

  return (
    <>
      <Field label="Tipo de título">
        <select
          value={value.fixed_income_type}
          onChange={(event) => handleTypeChange(event.target.value)}
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
          value={value.rate_type}
          onChange={(event) => update({ rate_type: event.target.value, rate: '' })}
          className={selectClassName}
        >
          {RATE_TYPES.map((type) => (
            <option key={type.value} value={type.value}>{type.label}</option>
          ))}
        </select>
      </Field>

      {value.rate_type === 'POS' ? (
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

      <label className="flex min-h-11 cursor-pointer items-center gap-3 self-end rounded-lg border border-zinc-200 px-4 text-sm font-medium text-zinc-700">
        <input
          type="checkbox"
          checked={value.is_tax_free}
          onChange={(event) => update({ is_tax_free: event.target.checked })}
          className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500"
        />
        Isento de IR
      </label>
    </>
  )
}
