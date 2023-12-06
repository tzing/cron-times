DROP TABLE IF EXISTS job;

CREATE TABLE job (
    "group" TEXT,
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    schedule TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    description TEXT,
    labels TEXT,
    metadata TEXT,
    enabled BOOLEAN NOT NULL DEFAULT 1,
    use_markdown BOOLEAN NOT NULL DEFAULT 1,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
