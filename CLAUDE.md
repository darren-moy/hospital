# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A small patient-records backend: plain Python (stdlib `sqlite3` only, no third-party dependencies) over a single SQLite file. There is no CLI, web layer, test suite, linter config, or requirements file yet. The modules expose plain functions meant to be called from a REPL or a future frontend.

## Commands

```bash
# Create / update the database (runs schema.sql against hospital.db)
python db.py

# Exercise the functions interactively (run from the repo root)
python -c "from patients import register_patient; print(register_patient('Ada', 'Lovelace', '1815-12-10', 'F'))"
```

A `venv/` exists at the repo root (activate with `venv\Scripts\activate` on Windows), but nothing is installed in it beyond the standard library.

`DB_PATH` in [db.py](db.py) is the relative path `"hospital.db"`, so it resolves against the **current working directory**. Run scripts from the repo root, or you'll silently create a new, empty database somewhere else. `*.db` files are gitignored.

## Architecture

- **[schema.sql](schema.sql)** is the source of truth for data rules. Every table uses `CREATE TABLE IF NOT EXISTS`, so running `init_db()` again will **not** change a table that already exists in `hospital.db`. When you change an existing table's definition, delete and rebuild the database (or write a migration).
- **[db.py](db.py)**: `get_connection()` turns on `PRAGMA foreign_keys = ON` (SQLite leaves foreign keys off by default) and sets `row_factory = sqlite3.Row`. Always get connections through this function. Each public function opens its own connection with `with get_connection() as conn:`, which commits on success and rolls back on exception. It does not close the connection.
- **Domain modules** ([patients.py](patients.py), [allergies.py](allergies.py), [encounters.py](encounters.py)) each have one table and follow the same pattern:
  1. Validate and normalize the inputs in Python (strip, lowercase/uppercase, length checks), raising `ValueError` with a message the user can read.
  2. Turn the patient's MRN into the internal `patients.id` with `patients._get_patient_id(conn, mrn)`, which raises `ValueError` if no patient has that MRN. Public APIs take the **MRN**, never the internal id.
  3. Run parameterized SQL, and translate `sqlite3.IntegrityError` into a `ValueError` with a domain-specific message.
  4. Return `dict(row)` or `[dict(row) ...]`, never raw `sqlite3.Row` objects.
- **Validation is duplicated on purpose**: Python constants (`VALID_SEX`, `MAX_NAME_LENGTH`, `VALID_TYPES`, etc.) mirror the `CHECK` constraints in `schema.sql`. When you change one, change the other.
- **MRNs** are stored as TEXT. They are generated sequentially, starting at `100001`, by `_next_mrn()` using `MAX(CAST(mrn AS INTEGER)) + 1` inside the same transaction as the insert.
- **Invariants enforced in the database**:
  - Allergies are unique per `(patient_id, substance)`, and `substance` uses `COLLATE NOCASE`.
  - A patient can have at most one open encounter (partial unique index `one_open_encounter_per_patient`). `status`/`ended_at` must agree: an open encounter has no `ended_at`, and a closed one must have it.
  - All foreign keys are `ON DELETE RESTRICT`. You cannot delete a patient who has related rows.
  - Timestamps are SQLite `CURRENT_TIMESTAMP` text (UTC). Dates are ISO `YYYY-MM-DD` text.
- **`vitals`** (in `schema.sql`, no Python module yet) is a `STRICT` table linked to `encounters`, not to patients. Because it is `STRICT`, every value must match its column type exactly. For example, the INTEGER vitals reject a value like `72.5`, while `temperature_f` is REAL so it can hold `98.6`. Blood pressure has to be recorded as a pair (systolic and diastolic both present or both null), and each row needs at least one vital sign.
