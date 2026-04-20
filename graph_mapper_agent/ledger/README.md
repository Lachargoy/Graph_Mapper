# Ledger del Agente

## Visión

Este ledger ya no se piensa como logging técnico del runtime.

Se piensa como memoria operativa del agente completo para:

- observabilidad
- reproducibilidad
- evaluación
- dataset para fine-tuning
- soporte para modo chat/deep-research
- soporte para invocación por MCP del runtime completo

## Capas que debe cubrir

1. Conversación
- sesiones
- mensajes
- respuestas finales

2. Ejecución
- runs
- steps del runtime
- eventos operativos

3. Evidencia
- páginas
- artifacts
- snippets
- screenshots
- OCR / visión
- evidencia estructurada reusable

4. Evaluación
- score de corrida
- label buena/mala
- feedback humano o automático
- elegibilidad para entrenamiento

## Estado actual

Hoy existe un bridge operativo a SQLite en:

- [sqlite_ledger_writer.py](./ledger/adapters/sqlite_ledger_writer.py)

Ese bridge ya sirve para:

- quitar dependencia a `aither.ledger`
- registrar eventos append-only
- registrar llamadas LLM
- dejar base local en SQLite

Pero no es todavía el diseño final.

## Diseño objetivo

El ledger final del agente debe girar alrededor de estas entidades:

- `sessions`
- `messages`
- `runs`
- `run_steps`
- `llm_calls`
- `evidence_records`
- `evaluations`

## Principios

- No depender de `jurisdiction_code` ni `document_key` como campos núcleo.
- Todo contexto específico debe entrar en `context_json` o metadata.
- `goal_validation` debe consumir evidencia; no ser dueña del parsing.
- `evidence_extraction` debe ser una subrutina separada.
- El modo chat y el modo MCP deben escribir al mismo ledger.

## Orden de implementación recomendado

1. Mantener el bridge actual estable.
2. Consolidar tablas `runs` y `llm_calls`.
3. Agregar `sessions` y `messages`.
4. Agregar `run_steps`.
5. Agregar `evidence_records`.
6. Agregar `evaluations`.
7. Hacer que chat/MCP usen el mismo store.
