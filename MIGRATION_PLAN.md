# MIGRATION_PLAN.md

Plano de migração da infraestrutura de agentes de IA de nota fiscal
(originalmente em `agent-nf-validator`) para um pacote genérico
(`iplanrio-agent-toolkit`), com a lógica de negócio indo para a pipeline
`rj_iplanrio__nf_agent` em `prefect_rj_iplanrio`.

Referenciado por `src/iplanrio_agent_toolkit/base/__init__.py` e `README.md`.

---

## Arquitetura de três repositórios

| Repositório | Papel |
|---|---|
| `iplanrio-agent-toolkit` (este) | Infraestrutura genérica de chamada de agentes de IA: clientes Gemini, cache, rate limiting, rule engine, GCS, versionamento de prompts. Sem vocabulário de negócio. |
| `prefect_rj_iplanrio` | Lógica de negócio CGM/NF na pipeline `rj_iplanrio__nf_agent`: regras de compliance, taxonomia, conteúdo de prompts, SQL, orquestração. |
| `agent-nf-validator` | Sandbox de pesquisa/experimentação. Consome o toolkit em vez de duplicar infraestrutura. |

**Regra de corte** (o que vai para o toolkit): se, removendo comentários e
docstrings, o código não revela ser sobre nota fiscal, ele é genérico e vai para
o toolkit. Se revela (`cnpj`, `id_documento`, `controle_processamento`, nomes
de regra de compliance), fica na pipeline.

---

## Fases (cada fase = 1 PR, sequencial)

### Fase 0 — Criar o repositório `iplanrio-agent-toolkit` ✅ (concluída)

- [x] Criar repositório GitHub `prefeitura-rio/iplanrio-agent-toolkit` (público)
- [x] `pyproject.toml` (hatchling, py310+, extras `gemini`/`pdf`/`ocr`, ruff igual ao prefect_rj_iplanrio)
- [x] `README.md`, `.gitignore`, `LICENSE` (MIT)
- [x] Estrutura `src/iplanrio_agent_toolkit/` + `tests/`
- [x] Dependência distribuída via git pinada (`[tool.uv.sources]`); PyPI fica como evolução futura

### Fase 1 — Extrair módulos genéricos para o toolkit ✅ (concluída)

Módulos extraídos (com correções de bugs encontrados na origem):

- [x] `logging.py` — `get_logger`, sem `print()`
- [x] `credentials.py` — `inject_credentials_from_env` (env var base64 → arquivo → `GOOGLE_APPLICATION_CREDENTIALS`)
- [x] `rate_limiter.py` — `GlobalRateLimiter` + `get/initialize/reset_rate_limiter`
- [x] `metrics_tracker.py` — `APIMetricsTracker` com `api_type`s dinâmicos; peak RPS O(n) (two-pointer)
- [x] `cache/sqlite_cache.py` — `SQLiteCache`; `get_statistics` **corrigido** para `cache_hit_rate: float` (na origem retornava `StringIO`)
- [x] `gcs/` — downloader (batch paralelo), csv_reader (filtros `_gte/_lte/_gt/_lt/_in/_not`), results_writer (partição Hive)
- [x] `bigquery/` — `BigQueryClient` sem vocabulário de domínio; `is_rate_limit_error` só com marcadores de string
- [x] `gemini/` — auth em cascata, `GeminiClient` (rate limiter + métricas), `parse_json_response` (dedup de 3 cópias), pricing, vision
- [x] `prompts/registry.py` — `PromptRegistry` genérico; ordenação de versões **corrigida** (numérica, suporta `v10+`)
- [x] `rules/` — `Rule[TContext]`/`RuleEngine[TContext]` genéricos, fallback configurável
- [x] `matching/text_similarity.py` — `levenshtein_distance`, `jaccard_length_similarity`
- [x] `base/` — `PageClassifier` + `DocumentExtractor` genéricos (sem vocabulário NF)
- [x] `ocr.py` — `OCRProcessor` (EasyOCR/PaddleOCR) sem globals de módulo
- [x] Tests unitários (84) + ruff check/format limpos

**Não migrado (código morto / fora de escopo):**
`bigquery_loader.py`, `postprocess_cross_envio_duplicates.py`,
`compare_results.py`, `generate_report_from_cache.py`,
`generate_metadata_from_cache.py`, `analyze_api_costs.py`, `clear_cache.py`,
`tools/*`, `DRAFT_investigation/*`, `nf_fatura_merger.py`,
`compliance_validator.py.old`, Protocol `BasePipeline` (contrato fictício, sem
implementação real).

**Bugs corrigidos durante a extração (Fase 1):**
- `get_statistics()` retornava `StringIO` — agora retorna `cache_hit_rate: float` (0.0–1.0)
- Ordenação de versões de prompt lexicográfica (`v10` antes de `v2`) — agora numérica
- 3 cópias de parsing de JSON — agora um único `parse_json_response`
- `reset_rate_limiter()` não zerava o singleton da classe — corrigido

**Bugs catalogados que ficam para a Fase 2 (negócio):**
- Prioridades duplicadas entre `OverpaymentRule` e `EmissionDateMismatchRule` (80)
- `EmissionDateMismatchRule` documentada como disabled mas ativa
- Nome de modelo hardcoded em 3 lugares
- `inspect.getsource()` de debug em `processor.py`

### Fase 2 — Migrar a lógica de negócio para `prefect_rj_iplanrio` ✅ (concluída — move mecânico)

**Decisão de layout:** Fase 2 executada como *move mecânico* preservando o layout
e o entrypoint `nf_processing_flow`. O achatamento por domínio (que era o plano
original desta fase) fica para a Fase 3. Código vivo de `agent-nf-validator`
mora agora em `pipelines/rj_iplanrio__nf_agent/utils/`:
`utils/__init__.py` (orquestração, antigo `utils.py`), `utils/core/` (antigo
`core/`) e `utils/run_poc/` (9 módulos vivos de `run_poc/`).

- [x] Remover a entrada de `agent-nf-validator` do `pyproject.toml` (rev `1b427b4`); declarar deps transitivas diretamente
- [x] Migrar `core/` → `utils/core/` (imports relativos internos preservados; mortos excluídos: `nf_fatura_merger.py`, `.old`)
- [x] Migrar módulos vivos de `run_poc/` → `utils/run_poc/` (imports normalizados para relativos; hacks `sys.path.insert` removidos)
- [x] Corrigir os 4 seams (`flow.py` credentials_helper; `utils` bigquery_writer/bq_input_reader/run_pipeline)
- [x] Migrar SQL para `queries/*.sql` (despesa_classificada.sql — sem SQL inline em `.py`)
- [x] Ajustar Dockerfile: remover instalação de `agent-nf-validator`; extra `gemini` continua isolado (conflito protobuf, ver TROUBLESHOOTING.md #4)
- [x] Regenerar `uv.lock` (231 linhas de deps transitivas removidas)
- [x] `ruff --fix` (183 auto-fixes seguros aplicados; restante é estilo legado — Fase 4)
- [ ] Adicionar `iplanrio-agent-toolkit` como dependência git pinada — **aguardando**: o código migrado ainda não o importa (integração ocorre na Fase 5); evita dep órfã
- [ ] Portar/adicionar testes da pipeline
- [ ] Smoke test em staging (branch `staging/rj-iplanrio-cgm-nf-agent`)

### Fase 3 — Quebrar os arquivos grandes da pipeline ✅ (concluída)

**3a — Relocações ✅ (commitada no branch staging):** movidos `utils/core/extractor.py`
→ `utils/extraction/`, `utils/core/compliance_validator/` → `utils/compliance/`,
`utils/run_poc/processor.py` → `utils/pipeline/`; `bigquery_loader.py` recriado em
`utils/run_poc/`.

**3b — Splits por mixins ✅ (commitada no branch staging):** as três classes grandes
foram desmembradas em submódulos coesos, compondo a classe original (API pública e
re-exports preservados):

- [x] `processor.py` (2821 linhas → 42) → `utils/pipeline/` com mixins
  `POCProcessorSetupMixin` (setup.py), `POCProcessorCacheMixin` (cache.py),
  `POCProcessorProcessMixin` (process.py), `POCProcessorMetadataMixin` (metadata.py),
  `POCProcessorDatabaseMixin` (database.py); `ExecutionMode` extraído para
  `modes.py` (sem dependências).
- [x] `validator.py` (1203) → `utils/compliance/` com mixins
  `ComplianceValidatorCoreMixin` (core.py), `ComplianceValidatorMatchingMixin`
  (matching.py), `ComplianceValidatorValidateMixin` (validate.py),
  `ComplianceValidatorReportMixin` (report.py); `validator.py` (153 linhas) mantém
  `compute_classification`, `load_expected_nfs_from_excel` e `validate_against_expected`.
- [x] `extractor.py` (1001) → `utils/extraction/` com mixins
  `NFExtractorAuthMixin` (auth.py), `NFExtractorPromptMixin` (prompt.py),
  `NFExtractorPdfMixin` (pdf.py), `NFExtractorCoalesceMixin` (coalesce.py),
  `NFExtractorApiMixin` (api.py); `extractor.py` (46 linhas) compõe a classe e
  mantém `extract_nf_data`.
- [x] Quebra de ciclo de import: fachada `utils/core/__init__.py` re-exporta
  compliance/extraction de forma **lazy** (PEP 562 `__getattr__`); `core/pipeline.py`
  importa `NFExtractor` lazy via `TYPE_CHECKING`/property.
- [x] Manter contrato público de `flow.py`/`tasks.py` intacto (smoke test via
  `load_script` com `__package__` + identidade de objetos confirmadas).
- [x] `ruff check` sem novos erros introduzidos pelo split (F821 do split resolvidos;
  restantes são pré-existentes, ex. `pd` em `run_pipeline.py`).

### Fase 4 — Conformidade com o STYLEGUIDE de `prefect_rj_iplanrio`

- [ ] Três camadas (client/execution/orchestration) respeitadas
- [ ] Sem `print()`; usar logging do toolkit
- [ ] Dataclasses para funções com 5+ parâmetros
- [ ] Sem SQL em `.py`; sem nomes de tabela/coluna espalhados em código
- [ ] `ruff check`/`format` passando com a mesma config

### Fase 5 — Migrar `agent-nf-validator` para consumir o toolkit

- [ ] Substituir módulos duplicados por imports do `iplanrio-agent-toolkit`
- [ ] Manter apenas pesquisa/experimentação (notebooks, evaluations, scripts)
- [ ] Remover código morto (listado na Fase 1) do repositório
- [ ] Atualizar `README.md` do sandbox apontando para o plano

### Fase 6 (futura) — Publicação PyPI

- [ ] Escolher nome final (`ai-agent-toolkit` ocupado; confirmar disponibilidade)
- [ ] Publicar `iplanrio-agent-toolkit` no PyPI
- [ ] Migrar consumo de git pinado para versão do PyPI
