# FinanceMVP

Aplicação full-stack para **gestão de finanças pessoais** e **acompanhamento de carteira de investimentos**, construída com uma arquitetura híbrida entre **frontend SPA**, **BaaS com Supabase** e **backend Flask** para regras de negócio e integrações externas.

## Visão geral

O objetivo do projeto é centralizar, em um único sistema:

- controle de saldo em conta;
- registro de receitas e despesas;
- gestão de cartões de crédito e faturas;
- compras parceladas;
- acompanhamento de investimentos;
- atualização de preços de ativos;
- visualização de métricas e gráficos do patrimônio.

A aplicação foi desenhada para resolver um problema real de uso diário: transformar dados financeiros dispersos em uma visão operacional única, com foco em clareza, rapidez de uso e capacidade de evoluir.

---

## O que a aplicação faz

### 1) Autenticação e controle de acesso
O usuário cria conta e faz login via **Supabase Auth**. A aplicação mantém a sessão no frontend e protege as rotas privadas, redirecionando usuários não autenticados para a tela de acesso.

### 2) Dashboard financeiro
A página inicial reúne os principais indicadores do sistema:

- patrimônio total;
- saldo em conta;
- total investido;
- valor disponível por dia até o fim do mês;
- despesas do mês por categoria;
- compras parceladas em aberto;
- fatura do mês com opção de pagamento direto.

### 3) Gestão de transações
O módulo de transações permite:

- registrar receitas e despesas;
- calcular saldo atual;
- cadastrar cartões de crédito;
- registrar compras no cartão;
- dividir compras em parcelas;
- gerar e organizar faturas por cartão e competência;
- marcar faturas como pagas;
- excluir lançamentos e compras parceladas.

### 4) Gestão de investimentos
O módulo de investimentos permite registrar ativos de diferentes classes, como:

- ações (`STOCKS`);
- renda fixa (`FIXED_INCOME`);
- fundos imobiliários (`REIT`);
- gado de corte (`CATTLE`);
- outros (`OTHER`).

Também existe suporte a:

- cálculo de preço médio;
- valor atual da posição;
- rentabilidade;
- valor líquido após imposto em renda fixa;
- histórico de movimentações;
- atualização de preços diretamente pela interface.

### 5) Visão analítica da carteira
A página de carteira consolida os ativos e apresenta:

- resumo investido x valor atual x valor líquido;
- distribuição por classe;
- gráficos de composição;
- evolução do capital investido ao longo do tempo;
- agrupamento de ativos por tipo.

---

## Arquitetura da solução

## Visão arquitetural

A arquitetura segue um modelo **híbrido**, com separação clara de responsabilidades:

### Frontend
Uma **Single Page Application (SPA)** em React/Vite é responsável pela interface, navegação, formulários, gráficos e interação do usuário.

### Backend
Uma API em Flask concentra regras que não devem ficar no cliente, especialmente:

- cálculo consolidado da carteira;
- cálculo de imposto para renda fixa;
- atualização de preços de ativos;
- integração com fontes externas de mercado.

### Banco de dados e autenticação
O Supabase funciona como camada de:

- autenticação;
- persistência transacional;
- políticas de segurança por usuário;
- acesso simplificado ao PostgreSQL.

---

## Principais decisões arquiteturais

### 1) Arquitetura híbrida: Supabase para CRUD + Flask para lógica de negócio

Em vez de colocar toda a aplicação apenas no banco/BaaS ou apenas no backend tradicional, o projeto adota uma composição entre os dois modelos:

- **Supabase** para operações diretas de leitura e escrita;
- **Flask** para agregações complexas, processamento e integrações externas.

#### Por que essa decisão?
Porque nem todo problema da aplicação tem o mesmo perfil.

Operações simples, como:

- inserir transações;
- listar investimentos;
- cadastrar cartões;
- atualizar status de faturas;

podem ser feitas diretamente do frontend com baixo atrito.

Já operações mais sensíveis ou mais “inteligentes”, como:

- consolidar carteira;
- calcular imposto regressivo da renda fixa;
- consultar preço de ação;
- recalcular valor atualizado de títulos indexados ao CDI;

ficam melhores no backend.

#### Benefícios
- reduz complexidade do frontend;
- evita duplicar regras de negócio no cliente;
- mantém o fluxo simples para CRUD;
- permite evoluir cálculos sem quebrar a interface;
- facilita futuras integrações com outros provedores de dados.

#### Trade-off
A arquitetura fica um pouco mais complexa que um sistema 100% frontend ou 100% backend, porque exige coordenação entre três camadas:
frontend, backend e banco/autenticação.

---

### 2) Supabase como BaaS principal

O projeto usa o Supabase como base central por três motivos:

1. **Auth nativo** para cadastro, login e sessão;
2. **PostgreSQL gerenciado** para persistência;
3. **SDK simples** no frontend para acelerar desenvolvimento.

#### Por que essa decisão?
Para um produto pessoal/MVP com potencial de crescimento, Supabase reduz muito o custo de infraestrutura inicial sem sacrificar controle arquitetural.

#### Benefícios
- acelera desenvolvimento;
- reduz boilerplate de autenticação;
- elimina necessidade de construir um backend completo para CRUD básico;
- usa PostgreSQL, o que facilita migração futura se necessário.

#### Trade-off
Parte da lógica de acesso a dados fica acoplada ao Supabase SDK no frontend. Se no futuro houver migração para outra stack, parte dessa camada precisará ser refatorada.

---

### 3) Row Level Security (RLS) como barreira principal de isolamento por usuário

A segurança de dados foi desenhada para que cada usuário veja apenas os próprios registros.

#### Por que essa decisão?
Em sistemas financeiros, isolamento de dados por usuário não é opcional.

No repositório atual, as tabelas documentadas em `schema.sql` habilitam **Row Level Security** e criam políticas por usuário para perfis, transações e investimentos.

#### Benefícios
- segurança no nível do banco;
- proteção mesmo que alguma consulta do frontend seja mal construída;
- menor dependência de filtros exclusivamente no cliente.

#### Trade-off
RLS aumenta a responsabilidade de manter o schema bem documentado e alinhado com todas as tabelas realmente usadas pelo app.

---

### 4) Backend com `service_role` apenas no servidor

O backend Flask usa credenciais privilegiadas do Supabase (`service_role`) e valida o usuário com base no token JWT recebido do frontend.

#### Por que essa decisão?
Porque rotinas de backend precisam executar operações de forma confiável e segura, enquanto a chave privilegiada nunca deve ficar exposta no cliente.

#### Benefícios
- separa permissões do cliente e do servidor;
- preserva segredos fora do frontend;
- permite centralizar operações mais críticas.

#### Trade-off
Exige cuidado extra com variáveis de ambiente e ambientes de deploy.

---

### 5) React + Vite para produtividade e experiência de desenvolvimento

O frontend foi construído com React e Vite para oferecer:

- inicialização rápida;
- hot reload ágil;
- estrutura simples;
- facilidade para escalar a interface por páginas e componentes.

#### Por que essa decisão?
Para uma aplicação com múltiplos módulos, dashboards, formulários e gráficos, React oferece um bom equilíbrio entre produtividade, reutilização e manutenção.

#### Benefícios
- boa componentização;
- fácil expansão de módulos;
- integração natural com bibliotecas de gráfico e roteamento.

#### Trade-off
A aplicação depende de boa disciplina de organização para não crescer de forma desordenada.

---

### 6) React Router e layout protegido

A navegação foi estruturada com rotas protegidas e um `Layout` compartilhado para páginas autenticadas.

#### Por que essa decisão?
Porque a aplicação tem uma separação natural entre:

- área pública: autenticação;
- área privada: dashboard, transações, carteira e investimentos.

#### Benefícios
- melhora a organização;
- reduz duplicação de estrutura visual;
- simplifica proteção de páginas privadas.

---

### 7) Cálculos agregados no backend, não no banco e não no cliente

O endpoint `/api/investments/portfolio` centraliza o processamento da carteira.

Ele:
- agrupa ativos;
- calcula valor investido;
- calcula valor atual;
- calcula rentabilidade;
- calcula valor líquido;
- distribui a carteira por classe;
- aplica regras específicas para renda fixa e pecuária.

#### Por que essa decisão?
Essas regras mudam com frequência e pertencem mais ao domínio da aplicação do que ao armazenamento puro.

#### Benefícios
- regra de negócio concentrada;
- menor risco de inconsistência entre telas;
- possibilidade de testar e evoluir o domínio de forma isolada.

#### Trade-off
O backend passa a ser um ponto crítico para a consistência das análises.

---

### 8) Integrações externas no backend

O backend integra com:

- **Yahoo Finance**, para atualização de preços de ações;
- **API do Banco Central**, para cálculo de valorização de ativos de renda fixa indexados ao CDI.

#### Por que essa decisão?
Chamadas a provedores externos devem ficar fora do cliente por motivos de:
- segurança;
- controle de erro;
- encapsulamento da lógica de cálculo.

#### Benefícios
- interface mais limpa;
- regras externas encapsuladas;
- possibilidade de trocar fornecedores no futuro.

#### Trade-off
O sistema passa a depender da disponibilidade dessas APIs para atualização automática.

---

### 9) Uso de `metadata` em JSONB para flexibilidade do domínio

A tabela `investments` usa um campo `metadata` em JSONB para armazenar informações específicas de determinados tipos de ativos, como:

- percentual do CDI;
- data de compra;
- isenção de imposto;
- taxa de mortalidade, no caso de pecuária.

#### Por que essa decisão?
Nem toda classe de ativo compartilha os mesmos atributos. JSONB permite flexibilidade sem explodir o schema com colunas demais ou tabelas muito especializadas cedo demais.

#### Benefícios
- maior flexibilidade;
- acelera evolução do domínio;
- evita schema excessivamente rígido no MVP.

#### Trade-off
Menor padronização estrutural e maior necessidade de validação na aplicação.

---

### 10) Cache de interface com `localStorage`

Alguns módulos armazenam dados em `localStorage` para melhorar a experiência após recarregamentos e tornar a interface mais responsiva.

#### Por que essa decisão?
Para um sistema de uso recorrente, faz sentido reduzir sensação de “tela vazia” e preservar dados recentes da sessão local.

#### Benefícios
- melhor percepção de desempenho;
- menor atrito em recarregamentos;
- preservação temporária de estado.

#### Trade-off
`localStorage` não é fonte de verdade. O dado correto continua sendo o banco.

---

## Estrutura do projeto

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
│   │   │   └── Layout.jsx
│   │   ├── lib/
│   │   │   └── supabaseClient.js
│   │   ├── pages/
│   │   │   ├── Auth.jsx
│   │   │   ├── Dashboard.jsx
│   │   │   ├── Transactions.jsx
│   │   │   ├── Investments.jsx
│   │   │   └── Carteira.jsx
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── index.css
│   ├── package.json
│   └── .env.example
└── README.md
```

---

## Fluxo de dados

### Fluxo 1: autenticação
1. Usuário faz login/cadastro no frontend.
2. Supabase Auth cria ou valida a sessão.
3. O frontend recebe o token da sessão.
4. Rotas protegidas passam a ser liberadas.

### Fluxo 2: CRUD simples
1. O frontend lê ou grava dados diretamente no Supabase.
2. O banco persiste os dados.
3. RLS garante que o usuário só enxergue o que é dele.

### Fluxo 3: análise de carteira
1. O frontend obtém o token da sessão.
2. Chama o backend Flask com `Authorization: Bearer <token>`.
3. O backend valida o usuário.
4. O backend busca investimentos no Supabase.
5. O backend calcula métricas consolidadas.
6. O frontend exibe o resultado em cards e gráficos.

### Fluxo 4: atualização de preços
1. O frontend chama o endpoint de atualização.
2. O backend consulta APIs externas.
3. O backend atualiza os preços no Supabase.
4. O frontend recarrega a carteira já com os valores atualizados.

---

## Modelagem de domínio

## Tabelas documentadas no repositório

### `profiles`
Armazena dados básicos do perfil do usuário autenticado.

### `transactions`
Armazena entradas e saídas de dinheiro:
- valor;
- data;
- categoria;
- descrição;
- tipo (`INCOME` ou `EXPENSE`).

### `investments`
Armazena movimentos e posições de investimento:
- classe do ativo;
- ticker ou nome;
- quantidade;
- preço médio;
- preço atual;
- metadados específicos;
- data de criação.

## Observação importante
O frontend também utiliza as entidades `credit_cards` e `cc_expenses`, que são parte do comportamento real da aplicação, mas não aparecem no `schema.sql` atualmente publicado no repositório. O ideal é incluir essas tabelas e respectivas políticas de segurança em uma próxima revisão da documentação e das migrations.

---

## Tecnologias utilizadas

### Frontend
- React 18
- Vite
- React Router DOM
- Tailwind CSS
- Recharts
- Lucide React
- Supabase JS

### Backend
- Python 3
- Flask
- Flask-CORS
- PyJWT
- Supabase Python Client
- yfinance

### Banco e autenticação
- Supabase
- PostgreSQL
- Row Level Security (RLS)

### Fontes externas de dados
- Yahoo Finance
- API do Banco Central do Brasil (série do CDI)

---

## Segurança

As decisões de segurança mais importantes do projeto são:

- autenticação centralizada via Supabase Auth;
- rotas privadas protegidas no frontend;
- validação do token antes de acessar endpoints protegidos do backend;
- `service_role` mantida apenas no servidor;
- RLS no banco para isolar dados por usuário;
- segredos fora do versionamento, via `.env`.

---

## Como rodar localmente

## Pré-requisitos

- Node.js
- Python 3
- conta no Supabase

## 1. Banco de dados

1. Crie um projeto no Supabase.
2. Execute `database/schema.sql`.
3. Crie também as tabelas complementares usadas pelo frontend (`credit_cards` e `cc_expenses`) caso ainda não estejam no seu ambiente.
4. Ative as políticas de segurança necessárias.
5. Copie URL e chaves do projeto.

## 2. Backend

Crie um arquivo `.env` em `backend/` com base em `.env.example`:

```env
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_JWT_SECRET=...
```

Instale as dependências e rode o servidor:

```bash
cd backend
python -m venv venv

# Linux/macOS
source venv/bin/activate

# Windows
venv\Scripts\activate

pip install -r requirements.txt
python app.py
```

O backend será iniciado em `http://localhost:5000`.

## 3. Frontend

Crie um arquivo `.env` em `frontend/` com base em `.env.example`:

```env
VITE_SUPABASE_URL=...
VITE_SUPABASE_ANON_KEY=...
```

Instale as dependências e rode o frontend:

```bash
cd frontend
npm install
npm run dev
```

O frontend será iniciado normalmente em `http://localhost:5173`.

---

## Limitações atuais

Como MVP, o projeto ainda apresenta alguns pontos naturais de evolução:

- documentação de schema ainda incompleta em relação a cartões e faturas;
- backend concentrado em um único arquivo (`app.py`);
- ausência de testes automatizados documentados no repositório;
- endpoints e URLs locais ainda fixos em alguns pontos;
- regras de domínio ainda podem ser extraídas para camadas de serviço;
- falta de Docker/CI para padronização de ambiente.

---

## Próximos passos recomendados

### Curto prazo
- separar o backend em módulos (`routes`, `services`, `repositories`);
- incluir migrations completas do banco;
- documentar todas as tabelas usadas pelo frontend;
- remover URLs hardcoded e usar variáveis de ambiente;
- padronizar tratamento de erros.

### Médio prazo
- adicionar testes unitários e de integração;
- criar camada de DTO/validação para payloads;
- adicionar observabilidade básica (logs estruturados);
- criar processo de deploy com containers.

### Longo prazo
- suporte multiinstituição;
- importação automática de extratos;
- metas financeiras e orçamento;
- alertas e automações;
- suporte a múltiplos usuários/contas compartilhadas.

---

## Por que este projeto é interessante tecnicamente

Este projeto é interessante porque combina, em um caso real:

- SPA moderna com React;
- BaaS com autenticação e banco gerenciado;
- backend customizado para cálculos financeiros;
- integração com APIs externas;
- visualização analítica com gráficos;
- preocupação com segurança e isolamento por usuário.

Ele mostra não apenas capacidade de construir telas, mas também de tomar decisões de arquitetura, modelar domínio financeiro e integrar camadas diferentes de forma pragmática.

---

## Licença

Defina aqui a licença do projeto, se desejar publicar formalmente como open source.
