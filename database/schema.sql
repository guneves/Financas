-- ============================================================
-- FinanceMVP - schema.sql completo e compatível com o app
-- ============================================================

-- Extensões
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- PERFIS
-- ============================================================
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc'::text, NOW())
);

-- ============================================================
-- TRANSAÇÕES BANCÁRIAS
-- ============================================================
CREATE TABLE IF NOT EXISTS transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    date DATE NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    type TEXT NOT NULL CHECK (type IN ('INCOME', 'EXPENSE')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc'::text, NOW())
);

CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON transactions(user_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_user_type ON transactions(user_id, type);

-- ============================================================
-- INVESTIMENTOS / MOVIMENTAÇÕES DE INVESTIMENTO
-- Observação: esta tabela é usada tanto para posição quanto histórico.
-- ============================================================
CREATE TABLE IF NOT EXISTS investments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    asset_class TEXT NOT NULL CHECK (asset_class IN ('STOCKS', 'FIXED_INCOME', 'REIT', 'CATTLE', 'OTHER')),
    ticker_or_name TEXT NOT NULL,
    quantity NUMERIC(14, 4) NOT NULL,
    average_price NUMERIC(12, 2) NOT NULL CHECK (average_price >= 0),
    current_price NUMERIC(12, 2),
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc'::text, NOW())
);

CREATE INDEX IF NOT EXISTS idx_investments_user_id ON investments(user_id);
CREATE INDEX IF NOT EXISTS idx_investments_user_asset_class ON investments(user_id, asset_class);
CREATE INDEX IF NOT EXISTS idx_investments_user_ticker ON investments(user_id, ticker_or_name);
CREATE INDEX IF NOT EXISTS idx_investments_metadata_gin ON investments USING GIN(metadata);

-- ============================================================
-- CARTÕES DE CRÉDITO
-- ============================================================
CREATE TABLE IF NOT EXISTS credit_cards (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    due_day INTEGER NOT NULL CHECK (due_day BETWEEN 1 AND 31),
    closing_day INTEGER NOT NULL CHECK (closing_day BETWEEN 1 AND 31),
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc'::text, NOW())
);

CREATE INDEX IF NOT EXISTS idx_credit_cards_user_id ON credit_cards(user_id);
CREATE INDEX IF NOT EXISTS idx_credit_cards_user_name ON credit_cards(user_id, name);

-- Evita duplicidade exata de nome de cartão por usuário
CREATE UNIQUE INDEX IF NOT EXISTS ux_credit_cards_user_name ON credit_cards(user_id, name);

-- ============================================================
-- DESPESAS DE CARTÃO / FATURAS PARCELADAS
-- Cada linha representa uma parcela lançada em uma competência futura.
-- ============================================================
CREATE TABLE IF NOT EXISTS cc_expenses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    card_id UUID NOT NULL REFERENCES credit_cards(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    purchase_date DATE NOT NULL,
    invoice_month INTEGER NOT NULL CHECK (invoice_month BETWEEN 1 AND 12),
    invoice_year INTEGER NOT NULL CHECK (invoice_year >= 2000),
    installment_info TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'PAID')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc'::text, NOW())
);

CREATE INDEX IF NOT EXISTS idx_cc_expenses_user_id ON cc_expenses(user_id);
CREATE INDEX IF NOT EXISTS idx_cc_expenses_card_id ON cc_expenses(card_id);
CREATE INDEX IF NOT EXISTS idx_cc_expenses_status ON cc_expenses(status);
CREATE INDEX IF NOT EXISTS idx_cc_expenses_invoice ON cc_expenses(user_id, invoice_year, invoice_month);
CREATE INDEX IF NOT EXISTS idx_cc_expenses_purchase_date ON cc_expenses(user_id, purchase_date DESC);

-- ============================================================
-- TRIGGER OPCIONAL: cria profile automaticamente ao cadastrar usuário
-- ============================================================
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.profiles (id)
  VALUES (NEW.id)
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
AFTER INSERT ON auth.users
FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();

-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE investments ENABLE ROW LEVEL SECURITY;
ALTER TABLE credit_cards ENABLE ROW LEVEL SECURITY;
ALTER TABLE cc_expenses ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- POLÍTICAS: PROFILES
-- ============================================================
DROP POLICY IF EXISTS "Users can view own profile" ON profiles;
DROP POLICY IF EXISTS "Users can insert own profile" ON profiles;
DROP POLICY IF EXISTS "Users can update own profile" ON profiles;
DROP POLICY IF EXISTS "Users can delete own profile" ON profiles;

CREATE POLICY "Users can view own profile"
ON profiles FOR SELECT
USING (auth.uid() = id);

CREATE POLICY "Users can insert own profile"
ON profiles FOR INSERT
WITH CHECK (auth.uid() = id);

CREATE POLICY "Users can update own profile"
ON profiles FOR UPDATE
USING (auth.uid() = id)
WITH CHECK (auth.uid() = id);

CREATE POLICY "Users can delete own profile"
ON profiles FOR DELETE
USING (auth.uid() = id);

-- ============================================================
-- POLÍTICAS: TRANSACTIONS
-- ============================================================
DROP POLICY IF EXISTS "Users can manage own transactions" ON transactions;

CREATE POLICY "Users can manage own transactions"
ON transactions FOR ALL
USING (auth.uid() = user_id)
WITH CHECK (auth.uid() = user_id);

-- ============================================================
-- POLÍTICAS: INVESTMENTS
-- ============================================================
DROP POLICY IF EXISTS "Users can manage own investments" ON investments;

CREATE POLICY "Users can manage own investments"
ON investments FOR ALL
USING (auth.uid() = user_id)
WITH CHECK (auth.uid() = user_id);

-- ============================================================
-- POLÍTICAS: CREDIT_CARDS
-- ============================================================
DROP POLICY IF EXISTS "Users can manage own credit cards" ON credit_cards;

CREATE POLICY "Users can manage own credit cards"
ON credit_cards FOR ALL
USING (auth.uid() = user_id)
WITH CHECK (auth.uid() = user_id);

-- ============================================================
-- POLÍTICAS: CC_EXPENSES
-- ============================================================
DROP POLICY IF EXISTS "Users can manage own cc expenses" ON cc_expenses;

CREATE POLICY "Users can manage own cc expenses"
ON cc_expenses FOR ALL
USING (auth.uid() = user_id)
WITH CHECK (auth.uid() = user_id);

-- ============================================================
-- VIEW OPCIONAL PARA CONSULTA DE FATURAS EM ABERTO
-- ============================================================
CREATE OR REPLACE VIEW open_credit_card_invoices AS
SELECT
    cce.user_id,
    cce.card_id,
    cc.name AS card_name,
    cce.invoice_month,
    cce.invoice_year,
    SUM(cce.amount) AS total_open_amount,
    COUNT(*) AS installments_count
FROM cc_expenses cce
JOIN credit_cards cc ON cc.id = cce.card_id
WHERE cce.status = 'OPEN'
GROUP BY
    cce.user_id,
    cce.card_id,
    cc.name,
    cce.invoice_month,
    cce.invoice_year;

-- ============================================================
-- COMENTÁRIOS DE MODELAGEM
-- ============================================================
COMMENT ON TABLE investments IS
'Usada pelo app tanto para registrar movimentações (compra/venda/resgate) quanto para consolidar posições em carteira.';

COMMENT ON COLUMN investments.metadata IS
'Campo flexível para dados específicos como purchase_date, cdi_percentage, is_tax_free, mortality_rate, is_redemption e related_id.';

COMMENT ON TABLE cc_expenses IS
'Cada registro representa uma parcela/fração de compra lançada em uma fatura específica.';
