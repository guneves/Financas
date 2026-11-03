-- A receber: a receita (o Pix) que pagou a parte dos outros (dono, 2026-11-02).
-- Com ela, a parte dos outros sai dessa receita, no mes dela; sem ela, o "pago"
-- abate a receita do mes em que foi marcado (apply_settled_others()).
ALTER TABLE transactions ADD COLUMN share_paid_by TEXT;
ALTER TABLE cc_expenses ADD COLUMN share_paid_by TEXT;
