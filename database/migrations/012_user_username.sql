-- Nome de usuario exibido no app.
--
-- O e-mail continua sendo o login, mas deixa de aparecer na interface: a barra
-- lateral e os Ajustes mostram `username`. Nao e unico — e um nome de exibicao,
-- nao um identificador. Usuarios anteriores ficam com NULL ate escolherem um
-- nome em Ajustes; o frontend mostra "Usuário" nesse meio tempo, nunca o e-mail.

ALTER TABLE users
ADD COLUMN username TEXT;
