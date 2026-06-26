# Arquitetura

> Projeto de demonstração. Empresa **Mar** fictícia, dados **simulados**.

## Dois planos

**1. Plano de dados (data product), `transform/`.**
Projeto dbt sobre DuckDB em camadas: `staging` (limpeza 1:1) → `intermediate`
(regras de negócio: status de receita, flags de qualidade) → `marts/mart_metrics`
(a camada de KPIs, *single source of truth*, com **contrato de dados habilitado**).
Cada métrica tem definição única; nada é recalculado em planilha. É o "chão de
fábrica" que o agente observa.

**2. Plano de agentes (LangGraph + Claude), `agents/`.**
Sobre a camada de métricas operam três papéis distintos, por isso multi-agente, e
não um único prompt:

- **Perfilador**, dada uma fonte nova, infere o *data contract* e gera o YAML de
  testes do dbt (saída validada como `DataContract`).
- **Sentinela**, recebe os sinais do **detector estatístico** e decide o que
  escalar; redige o alerta.
- **RCA**, em modo `live`, o **Claude usa tool-use** (`get_upstream`) para
  percorrer a **linhagem do dbt** a partir de `mart_metrics` e identificar o nó a
  montante mais provável; conclui emitindo um `RootCauseHypothesis` validado.

O **orquestrador** é um `StateGraph` do LangGraph:
`diagnose → propose_fix → [interrupt] → open_pr`. O grafo **pausa antes de abrir o
PR** (human-in-the-loop nativo, com estado no checkpointer); só após aprovação o
PR é aberto. Guardrails: `recursion_limit` do grafo e teto de custo no cliente.

## O ciclo (fechado, com humano no meio)

```
mart_metrics → detector estatístico → sentinela → RCA (Claude+linhagem) → PROPOR → APROVAÇÃO HUMANA → PR → mart_metrics
```

O agente **propõe**; o humano **aprova**. Nada altera produção sozinho.

## Modos de execução

- **offline** (padrão): o grafo inteiro roda de forma determinística, sem chave nem
  rede. É a *duble de teste* do modelo, usada por testes e CI, exercita toda a
  estrutura agêntica (nós, interrupt, guardrails) sem custo.
- **live**: o mesmo grafo chama o Claude (tool-calling + saída estruturada).

## Confiabilidade (eixo 4)

- **Evals** (`evals/`), o gerador injeta anomalias e grava o *ground truth*. A
  avaliação mede precisão/recall da detecção e a acurácia do nó de causa raiz, e
  roda como **gate** no CI: regressão a cada mudança de prompt/modelo/baseline.
- **Observabilidade** (`observability/`), cada execução emite um trace com a
  latência por nó, número de chamadas ao LLM e custo (`AGENT_TRACE_FILE` grava em
  JSON).

## Separação de responsabilidades que importa

A **detecção é estatística** (z-score robusto sobre resíduo dessazonalizado),
determinística e barata. O **Claude** entra para **raciocinar** sobre a causa
(navegando a linhagem) e redigir a correção, onde linguagem natural agrega. Assim
a existência da anomalia é auditável e o LLM faz engenharia, não chat.

## Custo (FinOps)

Rodar LLM sobre dados pode ficar caro, entao tres alavancas seguram o custo:

- **A deteccao e estatistica, nao LLM.** O passo que roda o tempo todo (varrer
  todas as series de KPI) custa zero de API. O modelo so e chamado quando ja existe
  uma anomalia para explicar, ou seja, em poucos eventos.
- **Modelo certo para cada tarefa.** Tarefa simples (inferir o contrato de uma
  fonte) vai num modelo barato e rapido (`LLM_MODEL_FAST`, ex.: Haiku); o raciocinio
  dificil de causa raiz vai num modelo forte (`LLM_MODEL_SMART`, ex.: Sonnet).
- **Teto de custo e medicao.** Cada execucao contabiliza tokens e custo (no trace),
  e o teto `AGENT_MAX_USD` aborta a execucao se estourar. O modo offline roda tudo
  a custo zero (CI e testes). O cliente de LLM e o unico ponto de integracao: trocar
  por um modelo local (ex.: via Ollama) para zerar o custo de API mexe so ali.
