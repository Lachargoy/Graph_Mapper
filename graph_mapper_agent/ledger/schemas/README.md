# Schemas

`001_agent_memory.sql` define el esquema base objetivo del ledger SQLite del agente.

El writer actual puede poblar solo una parte del esquema al inicio. Eso es intencional.

El orden de adopción previsto es:

1. `runs`
2. `llm_calls`
3. `run_steps`
4. `evidence_records`
5. `sessions`
6. `messages`
7. `evaluations`
