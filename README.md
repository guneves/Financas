# FinanceMVP

Aplicacao full-stack para gestao de financas pessoais e acompanhamento de carteira de investimentos.

## Arquitetura atual

O projeto nao depende mais do Supabase. A aplicacao usa:

- Frontend React/Vite para a interface.
- Backend Flask como API unica da aplicacao.
- SQLite local como banco de dados padrao.
- Autenticacao propria com email, senha criptografada e JWT.
- Integracoes externas no backend para precos de ativos e CDI.

Por padrao, o banco e criado automaticamente em `backend/finance.db` quando o backend inicia. Esse arquivo fica fora do Git por seguranca e por ser dado local.

## Funcionalidades

- Cadastro e login de usuario local.
- Dashboard financeiro com saldo, patrimonio, investimentos e faturas.
- Lancamento de receitas e despesas.
- Cadastro de cartoes de credito.
- Compras parceladas e baixa de faturas.
- Cadastro de investimentos de renda variavel, renda fixa e outros ativos.
- Consolidacao da carteira, rentabilidade, impostos estimados e distribuicao por classe.
- Atualizacao de cotacoes por API externa no backend.

## Estrutura

```text
Financas/
├── backend/
│   ├── app.py
│   ├── requirements.txt
│   └── .env.example
├── database/
│   └── schema.sql
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── lib/
│   │   │   ├── api.js
│   │   │   ├── auth.js
│   │   │   ├── dataApi.js
│   │   │   └── portfolio.js
│   │   ├── pages/
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── .env.example
├── ROADMAP.md
└── README.md
```

## Como rodar localmente

### 1. Backend

Crie `backend/.env` a partir de `backend/.env.example`:

```env
DATABASE_PATH=finance.db
DATABASE_MIGRATIONS_DIR=../database/migrations
DATABASE_BACKUP_DIR=backups
SQLITE_BUSY_TIMEOUT_MS=5000
JWT_SECRET=troque-esta-chave-em-producao
JWT_EXP_DAYS=30
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
FLASK_DEBUG=0
PRICE_CACHE_TTL_SECONDS=60
PRICE_FETCH_TIMEOUT_SECONDS=6
PRICE_DOWNLOAD_TIMEOUT_SECONDS=8
PRICE_FETCH_WORKERS=2
PRICE_QUOTE_STALE_HOURS=36
```

Instale dependencias e rode:

```bash
cd backend
pip install -r requirements.txt
python app.py
```

A API sobe em `http://localhost:5000`.

### 2. Frontend

Crie `frontend/.env` a partir de `frontend/.env.example`:

```env
VITE_API_BASE_URL=http://localhost:5000
```

Instale dependencias e rode:

```bash
cd frontend
npm install
npm run dev
```

O frontend sobe normalmente em `http://localhost:5173`.

## Banco de dados

O banco local padrao fica em `backend/finance.db`. A estrutura e evoluida por migrations SQL em `database/migrations`, aplicadas automaticamente quando o backend inicia. O arquivo `database/schema.sql` funciona como referencia consolidada do schema inicial.

O backend tambem configura o SQLite para uso local mais robusto:

- `PRAGMA foreign_keys = ON`
- `PRAGMA journal_mode = WAL`
- `PRAGMA synchronous = NORMAL`
- `PRAGMA busy_timeout` configuravel por `SQLITE_BUSY_TIMEOUT_MS`

As principais tabelas sao:

- `users`
- `transactions`
- `credit_cards`
- `cc_expenses`
- `assets`
- `investment_transactions`
- `price_quotes`
- `investment_positions`
- `investment_realized_results`
- `investments` (legado/migracao, mantida para preservar dados antigos)
- `schema_migrations`

Todos os registros financeiros possuem `user_id` e sao filtrados pelo backend com base no JWT do usuario autenticado.

### Investimentos

O modelo de investimentos foi separado para evitar misturar cadastro, movimentacao, cotacao e posicao consolidada:

- `assets`: cadastro do ativo por usuario, classe e ticker/nome.
- `investment_transactions`: compras, vendas, resgates e ajustes.
- `price_quotes`: historico de cotacoes manuais, mercado, CDI ou legadas.
- `investment_positions`: posicao atual materializada, recalculada depois das mudancas relevantes.
- `investment_realized_results`: resultado realizado por venda/resgate, com custo FIFO, custos, valor liquido, lucro/prejuizo, IR estimado e alocacoes fiscais em JSON.

Os endpoints antigos de `/api/investments` continuam respondendo no formato usado pela interface atual, mas agora leem e gravam nas tabelas normalizadas. Tambem existem consultas diretas em `/api/assets`, `/api/investment-transactions`, `/api/investment-positions` e `/api/investment-realized-results`.

A posicao em aberto fica separada do resultado realizado. Vendas de renda variavel consomem lotes por FIFO e resgates de renda fixa apuram o custo do lote relacionado. A estimativa fiscal e operacional e deve ser validada antes de qualquer declaracao oficial.

Operacoes destrutivas e atualizacao manual de cotacao usam `asset_id` e `asset_class`, nao apenas ticker. As rotas amplas por ticker foram desativadas para evitar apagar ou atualizar ativos diferentes que compartilhem o mesmo codigo. Ao excluir ou editar uma movimentacao, o backend tambem valida se vendas e resgates continuarao com lastro de compra/lote anterior.

O portfolio retorna metadados da cotacao atual em `asset.quote`, incluindo fonte, data/hora, idade e status (`fresh`, `stale` ou `missing`). A atualizacao de cotacoes pode ser global ou por ativo e retorna listas de ativos atualizados, falhos, em cache e ainda stale.

Compras, vendas e resgates tambem geram uma transacao de caixa vinculada em `transactions`:

- compra: saida na categoria `Investimento`;
- venda: entrada pelo valor de venda liquido de custos;
- resgate: entrada pelo valor resgatado liquido de custos.

O vinculo usa `transactions.source_type = INVESTMENT_TRANSACTION` e `transactions.source_id = investment_transactions.id`, com indice unico para evitar duplicidade. Esses lancamentos vinculados nao devem ser apagados manualmente pelo extrato; para desfazer, exclua a movimentacao de investimento.

### Backups locais

Use `POST /api/database/backups` autenticado para criar um backup em `DATABASE_BACKUP_DIR`. A rotina gera:

- uma copia `.db` feita pela API nativa de backup do SQLite;
- um dump `.sql`;
- um `.zip` com os dois arquivos.

## Variaveis importantes

### Backend

- `DATABASE_PATH`: caminho do arquivo SQLite. Padrao: `backend/finance.db`.
- `DATABASE_MIGRATIONS_DIR`: pasta das migrations SQL. Padrao: `database/migrations`.
- `DATABASE_BACKUP_DIR`: pasta dos backups locais. Padrao: `backend/backups`.
- `SQLITE_BUSY_TIMEOUT_MS`: tempo maximo de espera quando o SQLite estiver ocupado. Padrao: `5000`.
- `JWT_SECRET`: chave de assinatura dos tokens.
- `JWT_EXP_DAYS`: validade do token em dias.
- `CORS_ORIGINS`: origens liberadas para acessar a API.
- `FLASK_DEBUG`: use `1` apenas em desenvolvimento local quando precisar do modo debug.
- `PRICE_CACHE_TTL_SECONDS`: tempo de cache das cotacoes do yfinance, em segundos.
- `PRICE_FETCH_TIMEOUT_SECONDS`: limite de espera da API antes de usar cache ou valor salvo.
- `PRICE_DOWNLOAD_TIMEOUT_SECONDS`: timeout repassado para a chamada ao yfinance.
- `PRICE_FETCH_WORKERS`: quantidade maxima de consultas de cotacao em paralelo.
- `PRICE_QUOTE_STALE_HOURS`: idade maxima da cotacao antes de marcar como stale. Padrao: `36`.

### Frontend

- `VITE_API_BASE_URL`: URL base da API Flask.

## Observacoes

- `backend/finance.db` e dados locais nao devem ser versionados.
- Para producao, troque `JWT_SECRET` por um valor forte e privado.
- SQLite atende bem ao uso local/MVP. Para uso multiusuario real em servidor, o proximo passo natural e migrar a camada de persistencia para PostgreSQL proprio, mantendo a mesma API Flask.
