# Roadmap de melhorias

## Inspecao rapida

O projeto agora usa React/Vite no frontend, Flask como API unica, SQLite local como persistencia e autenticacao propria com JWT. Os pontos mais fortes sao a reducao de dependencia externa, a centralizacao das regras de dados no backend e uma cobertura funcional ampla para transacoes, cartoes e investimentos.

Os principais riscos encontrados estao em manutencao e configuracao:

- O backend ainda concentra rotas, persistencia, autenticacao, calculo de carteira e integracoes externas em um unico arquivo.
- Ainda nao ha testes automatizados para regras financeiras criticas.
- O SQLite e excelente para uso local/MVP, mas um deploy multiusuario deve migrar para PostgreSQL proprio.
- A documentacao de migracao de dados antigos ainda pode ser detalhada com exemplos operacionais.

## Curto prazo

- Separar o backend em modulos (`auth`, `database`, `routes`, `services`).
- Extrair formatadores e helpers compartilhados de data, moeda e parcelas no frontend.
- Padronizar mensagens de erro visiveis ao usuario.
- Adicionar interface visual para status e backup/exportacao do SQLite.

## Medio prazo

- Criar testes unitarios para calculo de carteira, IR regressivo, CDI e faturas.
- Adicionar validacao de payloads no backend.
- Criar uma camada de dominio para transacoes de cartao e consolidacao de investimentos.
- Adicionar CI com build do frontend e testes do backend.

## Longo prazo

- Adicionar logs estruturados e rastreamento de falhas de integracoes externas.
- Containerizar frontend/backend para deploy reproduzivel.
- Adicionar suporte a proventos, dividendos, juros sobre capital proprio e eventos corporativos.
- Implementar importacao de extratos, metas financeiras e alertas.

## Implementado agora

- Cliente HTTP compartilhado em `frontend/src/lib/api.js`.
- Autenticacao local em `frontend/src/lib/auth.js` e `/api/auth/*`.
- CRUD local em `frontend/src/lib/dataApi.js` e endpoints Flask.
- SQLite local inicializado automaticamente pelo backend.
- Migrations SQL versionadas em `database/migrations`.
- SQLite local com foreign keys, WAL, synchronous normal e busy timeout.
- Endpoints autenticados de status e backup do banco local.
- Modelo de investimentos normalizado com `assets`, `investment_transactions`, `price_quotes` e `investment_positions`.
- Migracao automatica dos dados antigos de `investments` para o modelo novo.
- Endpoints diretos para ativos, transacoes de investimento e posicoes materializadas.
- Compra, venda e resgate de investimento integrados ao caixa por `transactions.source_type/source_id`.
- Resultado realizado de vendas/resgates com custo FIFO, custos, preco liquido, IR estimado e historico fiscal por operacao.
- Operacoes destrutivas e atualizacao manual de cotacao protegidas por `asset_id`/classe, com bloqueio de edicoes/exclusoes que deixariam venda ou resgate sem lastro.
- Cotacoes com fonte, ultima atualizacao, status stale/missing, falhas por ativo e atualizacao individual por ativo.
- `VITE_API_BASE_URL`, `DATABASE_PATH`, `JWT_SECRET` e `CORS_ORIGINS` documentados.
- Chamadas do frontend para portfolio, historico e atualizacao de precos usando o cliente compartilhado.
- Healthcheck `/api/health`.
- Atualizacao de precos filtrada por `investment_id` quando informado.
