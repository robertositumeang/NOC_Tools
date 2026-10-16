CREATE TABLE IF NOT EXISTS license_activations (
    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    license_id TEXT NOT NULL UNIQUE,
    machine_id TEXT NOT NULL,
    activated_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    activation_token TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS license_activation_history (
    license_id TEXT PRIMARY KEY,
    email TEXT NOT NULL COLLATE NOCASE,
    machine_id TEXT NOT NULL,
    activated_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    activation_token TEXT NOT NULL
);

INSERT OR IGNORE INTO license_activation_history (
    license_id, email, machine_id, activated_at, expires_at, activation_token
)
SELECT
    license_id, email, machine_id, activated_at, expires_at, activation_token
FROM license_activations;

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'operator')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS admin_sessions_expiry
    ON admin_sessions (expires_at);

CREATE TABLE IF NOT EXISTS auth_rate_limits (
    scope_hash TEXT PRIMARY KEY,
    window_started_at INTEGER NOT NULL,
    attempt_count INTEGER NOT NULL,
    blocked_until INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS license_issues (
    license_id TEXT PRIMARY KEY,
    email TEXT NOT NULL COLLATE NOCASE,
    machine_id TEXT NOT NULL,
    days_valid INTEGER NOT NULL,
    license_type TEXT NOT NULL,
    operator TEXT NOT NULL,
    issued_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS license_issues_email
    ON license_issues (email);
