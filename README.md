# FinanceMVP

Um aplicativo web *full-stack* para gestão de finanças pessoais e acompanhamento de carteira de investimentos. Este MVP (Produto Mínimo Viável) permite aos utilizadores gerir as suas contas correntes, despesas de cartões de crédito (com faturas e prestações) e monitorizar os seus ativos financeiros, incluindo ações, fundos imobiliários, renda fixa e até gado de corte.

## Funcionalidades

* **Autenticação Segura:** Registo e início de sessão de utilizadores com Supabase Auth e JWT.
* **Visão Geral (Dashboard):** * Cálculo do património total e saldo em conta real.
    * Projeções de saldo (Global e para o Próximo Mês) considerando faturas de cartões de crédito.
    * Gráficos visuais (Recharts) para despesas mensais por categoria e distribuição da carteira de investimentos.
* **Gestão de Movimentações:**
    * Registo de entradas e saídas bancárias com categorização.
    * Gestão de Cartões de Crédito (criação de cartões, registo de compras parceladas, acompanhamento de faturas abertas/pagas/em atraso).
* **Carteira de Investimentos:**
    * Registo de ativos (`STOCKS`, `FIXED_INCOME`, `REIT`, `CATTLE`, `OTHER`).
    * Cálculo dinâmico (no backend) de preço médio, valorização atual e rentabilidade.
    * Métricas específicas, como taxa de mortalidade para investimentos em pecuária (Gado de Corte).
    * Atualização rápida da cotação atual diretamente na interface.

## Tecnologias Utilizadas

**Frontend:**
* [React](https://reactjs.org/) (com [Vite](https://vitejs.dev/))
* [Tailwind CSS](https://tailwindcss.com/) para estilização
* [Recharts](https://recharts.org/) para gráficos de dados
* [Lucide React](https://lucide.dev/) para ícones
* [React Router](https://reactrouter.com/) para navegação

**Backend:**
* [Python](https://www.python.org/) 3
* [Flask](https://flask.palletsprojects.com/) (API REST)
* [PyJWT](https://pyjwt.readthedocs.io/) para middleware de autenticação

**Base de Dados & Autenticação:**
* [Supabase](https://supabase.com/) (PostgreSQL) com *Row Level Security* (RLS) habilitado para garantir a privacidade dos dados de cada utilizador.

---

## Como Executar o Projeto Localmente

### Pré-requisitos
* [Node.js](https://nodejs.org/) instalado
* [Python](https://www.python.org/) instalado
* Conta no [Supabase](https://supabase.com/)

### 1. Configuração da Base de Dados (Supabase)
1. Crie um novo projeto no Supabase.
2. Vá ao separador "SQL Editor" e execute o conteúdo do ficheiro `database/schema.sql`. Isso irá criar as tabelas `profiles`, `transactions`, `investments` e as políticas de segurança (RLS).
3. Vá ao separador "Project Settings" -> "API" para obter o seu `Project URL` e as chaves `anon` e `service_role`.

### 2. Configuração do Backend (Python/Flask)
Abra o terminal na pasta raiz do projeto:

```bash
cd backend

# Crie um ambiente virtual
python -m venv venv

# Ative o ambiente virtual
# No Windows:
venv\Scripts\activate
# No macOS/Linux:
source venv/bin/activate

# Instale as dependências
pip install -r requirements.txt

Crie um ficheiro .env na pasta backend/ baseado no .env.example

Inicie o servidor backend

Crie um ficheiro .env na pasta frontend/ baseado no .env.example

Inicie o servidor de desenvolvimento frontend

Estrutura do Projeto
/backend: Contém a API em Flask (app.py), ficheiros de requisitos e lógicas complexas de cálculo de investimentos.

/frontend: Contém a aplicação React, componentes, páginas (Auth, Dashboard, Investments, Transactions) e configurações do Tailwind.

/database: Contém o script SQL (schema.sql) para gerar a estrutura da base de dados PostgreSQL no Supabase.

Segurança
As credenciais do .env nunca devem ser "commitadas" no repositório.

A base de dados utiliza Row Level Security (RLS), garantindo que um utilizador autenticado apenas consiga ler, editar ou apagar as suas próprias transações e investimentos. A API Flask valida o token JWT do frontend em cada pedido protegido.

