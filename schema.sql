CREATE TABLE IF NOT EXISTS patients (
    id            INTEGER PRIMARY KEY,
    mrn           TEXT NOT NULL UNIQUE,
    first_name    TEXT NOT NULL CHECK (length(first_name) BETWEEN 1 AND 50),
    last_name     TEXT NOT NULL CHECK (length(last_name) BETWEEN 1 AND 50),
    date_of_birth TEXT NOT NULL CHECK (date(date_of_birth) = date_of_birth),
    sex           TEXT NOT NULL CHECK (sex IN ('F', 'M', 'O', 'U')),
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS allergies (
    id          INTEGER PRIMARY KEY,
    patient_id  INTEGER NOT NULL
                REFERENCES patients(id) ON DELETE RESTRICT, -- confirm real patient, blocks deleting patient who has allergies 
    substance   TEXT NOT NULL COLLATE NOCASE                -- alleries, not case sensitive 
                CHECK (length(substance) BETWEEN 1 AND 100),
    reaction    TEXT                                        -- reaction to allergies, can be null 
                CHECK (reaction IS NULL OR length(reaction) BETWEEN 1 AND 200),
    severity    TEXT NOT NULL 
                CHECK (severity IN ('mild', 'moderate', 'severe')),
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (patient_id, substance)                          -- same allergy can't be listed for same patient 
);