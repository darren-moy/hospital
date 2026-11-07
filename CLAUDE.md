# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A small patient-records backend: plain Python (stdlib `sqlite3` only, no third-party dependencies) over a single SQLite file. There is no CLI, web layer, linter config, or requirements file yet. The modules expose plain functions meant to be called from a REPL or a future frontend.

**Use only fake patient data.** Never put real patient information in `hospital.db`, test fixtures, seed scripts, examples, or commit messages, even for debugging. Use obviously fictional names (e.g. Ada Lovelace) and made-up dates.

## Commands

```bash
# Create / update the database (runs schema.sql against hospital.db)
python db.py

# Exercise the functions interactively (run from the repo root)
python -c "from patients import register_patient; print(register_patient('Ada', 'Lovelace', '1815-12-10', 'F'))"
```

This project is worked on from both Windows and macOS. `venv/` lives at the repo root and is gitignored, so each machine needs its own, and nothing is installed in it beyond the standard library. Activate it first so that `python` resolves on both systems:

| | Create | Activate | Interpreter path |
| --- | --- | --- | --- |
| **Windows** | `python -m venv venv` | `venv\Scripts\activate` | `venv/Scripts/python.exe` |
| **macOS** | `/usr/bin/python3 -m venv venv` | `source venv/bin/activate` | `venv/bin/python` |

`STRICT` tables need SQLite 3.37+, and Python uses its own bundled SQLite. On macOS, the default `python3` (3.10.2) has 3.35.5 and fails with `near "STRICT": syntax error`, so build the venv from `/usr/bin/python3`. Rerunning `venv` over an existing one doesn't replace its Python, so delete `venv/` first. Check the version with `python -c "import sqlite3; print(sqlite3.sqlite_version)"`.

```bash
# Tests on Windows (pytest is not in the venv there yet: pip install fails with an SSL certificate error, so use the system Python 3.11)
py -3.11 -m pytest tests
py -3.11 -m pytest tests/schema/test_vitals.py::test_name   # single test
```

`tests/conftest.py` has an autouse fixture that points `db.DB_PATH` at a temporary file, so tests never touch `hospital.db`. It also provides `patient`, `open_encounter`, and `closed_encounter` fixtures. `tests/schema/` is generated and maintained by the `schema-test-writer` agent (`.claude/agents/`); put hand-written tests elsewhere under `tests/`.

`DB_PATH` in [db.py](db.py) is the relative path `"hospital.db"`, so it resolves against the **current working directory**. Run scripts from the repo root, or you'll silently create a new, empty database somewhere else. `*.db` files are gitignored.

## Architecture

- **[schema.sql](schema.sql)** is the source of truth for data rules. Every table uses `CREATE TABLE IF NOT EXISTS`, so running `init_db()` again will **not** change a table that already exists in `hospital.db`. When you change an existing table's definition, delete and rebuild the database (or write a migration).
- **[db.py](db.py)**: `get_connection()` turns on `PRAGMA foreign_keys = ON` (SQLite leaves foreign keys off by default) and sets `row_factory = sqlite3.Row`. Always get connections through this function. Each public function opens its own connection with `with get_connection() as conn:`, which commits on success and rolls back on exception. It does not close the connection.
- **Domain modules** ([patients.py](patients.py), [allergies.py](allergies.py), [encounters.py](encounters.py), [vitals.py](vitals.py), [conditions.py](conditions.py)) each have one table and follow the same pattern:
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
- **`vitals`** is a `STRICT` table linked to `encounters`, not to patients, so `vitals.py` functions take an `encounter_id` instead of an MRN. Its Python ranges and display labels live in one `VITALS` dict; keep it in sync with the schema's CHECKs. Only `record_vitals` (not the schema) enforces that the encounter is open. Because it is `STRICT`, a value that can't be converted to its column type without loss is rejected. For example, the INTEGER vitals reject `72.5` (though SQLite still accepts `'72'` and `72.0`, which Python rejects first), while `temperature_f` is REAL so it can hold `98.6`. Blood pressure has to be recorded as a pair (systolic and diastolic both present or both null), and each row needs at least one vital sign.
