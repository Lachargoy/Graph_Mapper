CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    session_kind TEXT NOT NULL DEFAULT 'runtime',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    context_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    session_id TEXT,
    workflow_name TEXT NOT NULL,
    thread_id TEXT,
    attempt INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'running',
    started_at TEXT NOT NULL,
    finished_at TEXT,
    input_json TEXT NOT NULL DEFAULT '{}',
    final_output_json TEXT NOT NULL DEFAULT '{}',
    context_json TEXT NOT NULL DEFAULT '{}',
    quality_score REAL,
    quality_label TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS run_steps (
    step_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    step_index INTEGER,
    node_name TEXT,
    branch_name TEXT,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_calls (
    call_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    session_id TEXT,
    operation_name TEXT NOT NULL,
    provider_name TEXT,
    model_name TEXT,
    prompt_version TEXT,
    structured_output_name TEXT,
    request_kind TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    success INTEGER NOT NULL DEFAULT 0,
    response_format_valid INTEGER,
    finish_reason TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    reasoning_tokens INTEGER,
    cached_tokens INTEGER,
    total_tokens INTEGER,
    latency_ms INTEGER,
    messages_json TEXT NOT NULL DEFAULT '{}',
    expected_output_json TEXT NOT NULL DEFAULT '{}',
    response_json TEXT NOT NULL DEFAULT '{}',
    validation_json TEXT NOT NULL DEFAULT '{}',
    raw_response_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS evidence_records (
    evidence_id TEXT PRIMARY KEY,
    run_id TEXT,
    step_id INTEGER,
    evidence_kind TEXT NOT NULL,
    source_kind TEXT,
    source_url TEXT,
    local_path TEXT,
    mime_type TEXT,
    title TEXT,
    content_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluations (
    evaluation_id TEXT PRIMARY KEY,
    session_id TEXT,
    run_id TEXT,
    step_id INTEGER,
    target_kind TEXT NOT NULL,
    evaluator_kind TEXT NOT NULL,
    score REAL,
    label TEXT,
    usable_for_training INTEGER NOT NULL DEFAULT 0,
    feedback_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at);
CREATE INDEX IF NOT EXISTS idx_run_steps_run_id ON run_steps(run_id, created_at);
CREATE INDEX IF NOT EXISTS idx_llm_calls_run_id ON llm_calls(run_id, started_at);
CREATE INDEX IF NOT EXISTS idx_evidence_records_run_id ON evidence_records(run_id, created_at);
CREATE INDEX IF NOT EXISTS idx_evaluations_run_id ON evaluations(run_id, created_at);
