-- O outro lado de um Pix ou transferencia, como a notificacao disse
-- (services/inbox.py): quem recebeu ou mandou (counterparty), os digitos do
-- meio do CPF que o banco mostra mascarado (counterparty_doc, "378195" de
-- "***.378.195-**") e a instituicao do outro lado (counterparty_bank, o texto
-- do banco). E o que separa uma transferencia entre contas do dono de um Pix
-- para outra pessoa quando so uma das pontas notifica.
--
-- Quem e o dono do lado de la fica em inbox_hints, aprendido: chaves
-- "self:doc:<digitos>" e "self:name:<nome normalizado>", gravadas quando as
-- duas pontas de uma transferencia se juntam ou o dono aprova uma
-- transferencia.

ALTER TABLE notify_detections ADD COLUMN counterparty TEXT;
ALTER TABLE notify_detections ADD COLUMN counterparty_doc TEXT;
ALTER TABLE notify_detections ADD COLUMN counterparty_bank TEXT;
