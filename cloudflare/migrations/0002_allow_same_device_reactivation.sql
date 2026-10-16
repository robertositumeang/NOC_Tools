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
