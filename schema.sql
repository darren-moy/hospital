CREATE TABLE IF NOT EXISTS patients (
    id            INTEGER PRIMARY KEY,
    mrn           TEXT NOT NULL UNIQUE,
    first_name    TEXT NOT NULL CHECK (length(first_name) BETWEEN 1 AND 50),
    last_name     TEXT NOT NULL CHECK (length(last_name) BETWEEN 1 AND 50),
    date_of_birth TEXT NOT NULL CHECK (date(date_of_birth) = date_of_birth),
    sex           TEXT NOT NULL CHECK (sex IN ('F', 'M', 'O', 'U')),
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);