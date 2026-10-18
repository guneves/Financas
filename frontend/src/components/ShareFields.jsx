import { SHARE_OPTIONS } from '../lib/sharing'
import { Field } from './ui'

// "De quem é?" (032, lib/sharing.js): só minha, dividida ou de outra pessoa,
// com o nome de quem. Usado ao editar um lançamento no Extrato e numa compra
// em Cartões. `form` = { share_mode, share_person, share_others_amount }.
export default function ShareFields({ form, onChange, type = 'EXPENSE', disabled = false }) {
  const set = (key) => (event) => onChange({ ...form, [key]: event.target.value })
  const income = type === 'INCOME'
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <Field label="De quem é?">
        <select value={form.share_mode} onChange={set('share_mode')} className="app-select" disabled={disabled}>
          {SHARE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </Field>
      {form.share_mode ? (
        <Field
          label="Nome da pessoa"
          hint={income ? 'Dinheiro que era para pagar algo dela.' : 'Fica em A receber até você marcar que ela pagou.'}
        >
          <input
            type="text"
            value={form.share_person}
            onChange={set('share_person')}
            className="app-input"
            maxLength={120}
            autoComplete="off"
            disabled={disabled}
          />
        </Field>
      ) : null}
      {form.share_mode === 'SPLIT' ? (
        <Field label="Parte dela (R$)">
          <input
            type="number"
            inputMode="decimal"
            step="0.01"
            min="0"
            value={form.share_others_amount}
            onChange={set('share_others_amount')}
            className="app-input"
            disabled={disabled}
          />
        </Field>
      ) : null}
    </div>
  )
}
