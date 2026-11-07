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

CREATE TABLE IF NOT EXISTS encounters (
    id                  INTEGER PRIMARY KEY,
    patient_id          INTEGER NOT NULL 
                        REFERENCES patients(id) ON DELETE RESTRICT,
    encounter_type      TEXT NOT NULL 
                        CHECK(encounter_type IN ('outpatient', 'inpatient', 'emergency')),
    reason              TEXT NOT NULL 
                        CHECK(length(reason) BETWEEN 1 AND 200),
    status              TEXT NOT NULL DEFAULT 'open'
                        CHECK(status in ('open', 'closed')),
    started_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at            TEXT,
    CHECK (
        (status = 'open' AND ended_at IS NULL)
        OR (status = 'closed' AND ended_at IS NOT NULL)),
    CHECK (ended_at IS NULL OR ended_at >= started_at)
);

CREATE UNIQUE INDEX IF NOT EXISTS one_open_encounter_per_patient
    ON encounters (patient_id)
    WHERE status = 'open';

CREATE TABLE IF NOT EXISTS vitals (
    id                  INTEGER PRIMARY KEY,
    encounter_id        INTEGER NOT NULL
                        REFERENCES encounters(id) ON DELETE RESTRICT,
    systolic            INTEGER CHECK (systolic BETWEEN 50 AND 300),
    diastolic           INTEGER CHECK (diastolic BETWEEN 20 AND 200),
    heart_rate          INTEGER CHECK (heart_rate BETWEEN 20 AND 300),
    temperature_f       REAL    CHECK (temperature_f BETWEEN 85 AND 115),
    resp_rate           INTEGER CHECK (resp_rate BETWEEN 4 AND 80),
    spo2                INTEGER CHECK (spo2 BETWEEN 50 AND 100),
    recorded_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((systolic IS NULL) = (diastolic IS NULL)),
    CHECK (systolic IS NULL OR systolic > diastolic),
    CHECK (COALESCE(systolic, heart_rate, temperature_f, resp_rate, spo2) IS NOT NULL)
) STRICT;

CREATE TABLE IF NOT EXISTS conditions (
    id              INTEGER PRIMARY KEY,
    patient_id      INTEGER NOT NULL 
                    REFERENCES patients(id) ON DELETE RESTRICT,
    icd10_code      TEXT NOT NULL       
                    CHECK(icd10_code = upper(icd10_code) AND length(icd10_code) BETWEEN 3 AND 8),
    description     TEXT NOT NULL 
                    CHECK (length(description) BETWEEN 1 AND 200),
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK ( status in ('active', 'resolved')),
    onset_date      TEXT CHECK (onset_date is NULL OR date(onset_date) = onset_date),
    resolved_date   TEXT CHECK (resolved_date IS NULL OR date(resolved_date) = resolved_date),
    recorded_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        (status = 'active' AND resolved_date IS NULL )
        OR (status = 'resolved' AND resolved_date IS NOT NULL )
    ),
    CHECK (onset_date IS NULL OR resolved_date IS NULL OR resolved_date >= onset_date)
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS one_active_condition_per_code
    ON conditions (patient_id, icd10_code)
    WHERE status = 'active';