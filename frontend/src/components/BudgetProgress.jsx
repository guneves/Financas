import { cx } from './ui'

// Orcamento e Inicio mostram o mesmo status. "No plano" e o normal: sem cor.
// Ambar e vermelho so quando pede atencao.
export const BUDGET_STATUS_TONES = {
  OK: 'neutral',
  WARNING: 'warning',
  OVER: 'danger',
  NEEDS_INCOME: 'warning',
}

export const BUDGET_STATUS_LABELS = {
  OK: 'No plano',
  WARNING: 'Perto do limite',
  OVER: 'Estourou',
  NEEDS_INCOME: 'Falta a renda',
}

const BAR_COLORS = {
  OK: 'bg-emerald-500',
  WARNING: 'bg-amber-500',
  OVER: 'bg-rose-500',
}

// Mesma regra de budget_status() no backend (services/budgets.py), para o total do mes. O backend
// arredonda o percentual (ROUND_HALF_UP, centesimos) antes de comparar com 80:
// 799,99 de 1.000,00 da 79,999% -> 80,00% -> "Perto do limite".
export function budgetStatus(spent, available) {
  if (spent > available) return 'OVER'
  if (available <= 0) return 'OK'
  const percent = Math.floor((spent / available) * 10000 + 0.5 + 1e-9) / 100
  return percent >= 80 ? 'WARNING' : 'OK'
}

export function BudgetProgressBar({ percent, status, className = 'h-2' }) {
  const width = Math.min(Math.max(Number(percent || 0), 0), 100)
  return (
    <div className={cx('w-full overflow-hidden rounded-full bg-zinc-100', className)}>
      <div className={cx('bar-grow h-full rounded-full transition-[width] duration-500 ease-out-quint', BAR_COLORS[status] || BAR_COLORS.OK)} style={{ width: `${width}%` }} />
    </div>
  )
}
