-- De quem e o gasto (services/sharing.py): um lancamento ou uma compra no
-- cartao pode ser, em parte ou inteiro, de outra pessoa — a pizza dividida, a
-- conta paga por alguem que vai devolver. O dinheiro sai da conta do mesmo
-- jeito; so o Fluxo de caixa (que mostra "outras pessoas" a parte), Despesas
-- por categoria, o orcamento e o plano do mes passam a contar a parte do dono.
--
-- share_mode: NULL = so do dono; 'OTHERS' = inteiro de outra pessoa;
-- 'SPLIT' = dividido, com share_others_amount = a parte dos outros (0 < x <
-- amount). Numa compra parcelada, cada parcela guarda a sua fatia.
-- share_person: quem (obrigatorio com share_mode). share_settled_at: quando o
-- dono marcou que a pessoa pagou; NULL numa despesa = "A receber" pendente.

ALTER TABLE transactions ADD COLUMN share_mode TEXT CHECK (share_mode IN ('OTHERS', 'SPLIT'));
ALTER TABLE transactions ADD COLUMN share_others_amount REAL CHECK (share_others_amount >= 0);
ALTER TABLE transactions ADD COLUMN share_person TEXT;
ALTER TABLE transactions ADD COLUMN share_settled_at TEXT;

ALTER TABLE cc_expenses ADD COLUMN share_mode TEXT CHECK (share_mode IN ('OTHERS', 'SPLIT'));
ALTER TABLE cc_expenses ADD COLUMN share_others_amount REAL CHECK (share_others_amount >= 0);
ALTER TABLE cc_expenses ADD COLUMN share_person TEXT;
ALTER TABLE cc_expenses ADD COLUMN share_settled_at TEXT;
