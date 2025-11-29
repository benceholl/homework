CREATE TABLE IF NOT EXISTS pipeline_runs (
    id SERIAL PRIMARY KEY,
    build_id TEXT NOT NULL,
    branch TEXT NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('success','failed','canceled','running')),
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    repo_name TEXT NULL,
    commit_sha TEXT NULL,
    runner TEXT NULL,
    workflow TEXT NULL,
    UNIQUE (build_id, branch),
    CHECK (end_time IS NULL OR end_time >= start_time)
);
