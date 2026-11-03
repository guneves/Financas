-- Toda transacao entra no momento em que a Pluggy a tem (dono, 2026-11-01):
-- "Trazer pendentes" passa a valer ligado, inclusive para quem tinha desligado.
-- Desligar de novo em Ajustes continua valendo (o padrao sem escolha e ligado).
UPDATE user_settings SET value = '1' WHERE setting_key = 'open_finance_include_pending';
