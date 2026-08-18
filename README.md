# iplanrio-agent-toolkit

Infraestrutura genérica e reutilizável para pipelines que chamam agentes de IA
(LLMs de visão/extração, principalmente Google Gemini) sobre documentos.

## O que este pacote é

Um conjunto de blocos de infraestrutura **sem nenhum conhecimento de domínio de
negócio**: como autenticar e chamar um modelo Gemini, como cachear respostas de
API, como limitar taxa de requisições, como rodar um motor de regras genérico
por prioridade, como baixar/ler/escrever arquivos no Google Cloud Storage, como
versionar prompts de texto.

Módulos oferecidos (ver `src/iplanrio_agent_toolkit/`):

- `credentials` — injeta credenciais GCP a partir de uma env var base64 (ex.: Infisical/Kubernetes secrets).
- `rate_limiter` — rate limiter thread-safe global (concorrência + requisições/minuto).
- `metrics_tracker` — tracker de métricas de chamadas de API (latência, taxa, erros).
- `cache.sqlite_cache` — cache SQLite de duas tabelas (input/output) com deduplicação por hash de conteúdo.
- `gcs` — download paralelo, leitura de CSV com filtros, escrita de resultados particionados por data.
- `bigquery` — wrapper fino de client BigQuery (load job, query, insert de linha).
- `gemini` — autenticação em cascata, chamada de API com retry, parsing de resposta JSON, extração de página de PDF como bytes.
- `prompts` — registro/versionamento de prompts de texto (hash, listagem, carregamento da versão mais recente).
- `rules` — motor de regras genérico ordenado por prioridade (Chain of Responsibility).
- `matching` — similaridade de texto (Levenshtein) para fuzzy matching genérico.
- `base` — `Protocol`/`ABC` de classificador e extrator de documentos (o `BasePipeline` do código original não foi portado; ver `MIGRATION_PLAN.md`).
- `ocr` *(extra opcional `ocr`)* — wrapper de OCR (EasyOCR/PaddleOCR) sobre páginas de PDF.

## O que este pacote NÃO é

Não há aqui nenhuma lógica específica de Nota Fiscal, CNPJ, regras de
compliance fiscal, taxonomia de documentos, ou schema de dados de despesa. Essa
lógica de negócio vive em quem consome este pacote — por exemplo, a pipeline
`rj_iplanrio__nf_agent` no repositório
[`prefect_rj_iplanrio`](https://github.com/prefeitura-rio/prefect_rj_iplanrio).

Se você encontrar uma referência a "nota fiscal", "CNPJ" ou qualquer regra de
compliance específica dentro deste pacote, é um bug de escopo — abra uma issue.

## Instalação

Ainda não publicado no PyPI. Use como dependência git pinada:

```toml
[project]
dependencies = ["iplanrio-agent-toolkit"]

[tool.uv.sources]
iplanrio-agent-toolkit = { git = "https://github.com/prefeitura-rio/iplanrio-agent-toolkit.git", rev = "<commit-hash>" }
```

## Desenvolvimento

```bash
uv sync --all-extras
uv run pytest
uv run ruff check .
uv run ruff format .
```

## Histórico

Este pacote nasceu da extração da parte genérica de infraestrutura do projeto
[`agent-nf-validator`](https://github.com/prefeitura-rio/agent-nf-validator),
que hoje é mantido como sandbox de pesquisa/experimentação. Veja
`MIGRATION_PLAN.md` para o histórico completo da migração.
