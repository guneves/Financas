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
JWT_SECRET=troque-esta-chave-em-producao
JWT_EXP_DAYS=30
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
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

O schema SQLite fica em `database/schema.sql` e tambem esta embutido no backend para inicializacao automatica.

As principais tabelas sao:

- `users`
- `transactions`
- `credit_cards`
- `cc_expenses`
- `investments`

Todos os registros financeiros possuem `user_id` e sao filtrados pelo backend com base no JWT do usuario autenticado.

## Variaveis importantes

### Backend

- `DATABASE_PATH`: caminho do arquivo SQLite. Padrao: `backend/finance.db`.
- `JWT_SECRET`: chave de assinatura dos tokens.
- `JWT_EXP_DAYS`: validade do token em dias.
- `CORS_ORIGINS`: origens liberadas para acessar a API.

### Frontend

- `VITE_API_BASE_URL`: URL base da API Flask.

## Observacoes

- `backend/finance.db` e dados locais nao devem ser versionados.
- Para producao, troque `JWT_SECRET` por um valor forte e privado.
- SQLite atende bem ao uso local/MVP. Para uso multiusuario real em servidor, o proximo passo natural e migrar a camada de persistencia para PostgreSQL proprio, mantendo a mesma API Flask.
