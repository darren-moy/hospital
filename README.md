# Mini EHR
![Tests](https://github.com/darren-moy/hospital/actions/workflows/tests.yml/badge.svg)

A small patient-records app I'm building to learn backend development. Python and SQLite underneath, with a Flask site for looking patients up.

It tracks patients, allergies, visits (encounters), vital signs and diagnoses (ICD-10 conditions).

> All data is synthetic. This is a practice project, not a clinical system, and the vital-sign thresholds are simplified. Fake patients name: Ada Lovelace, Alan Turing, Grace Hopper, Marie Curie

## What it does

- Registers patients and gives each one an MRN, starting at 100001
- Search by last name, look up by MRN
- Allergies with severity and reaction; no duplicate substances per patient
- Encounters that open and close, one open at a time per patient
- Vitals recorded during an open encounter, with flags like "High blood pressure" or "Fever"
- A problem list using ICD-10 codes (`I10`, `E11.9`), active or resolved
- Web pages for patient search and a basic chart
- Shows vitals from synthetic patients on their chart

Validation happens in Python first, then again in the database through `CHECK` constraints, foreign keys and unique indexes in `schema.sql`. So bad data gets rejected even if something skips the Python functions.

## Setup

You need Python 3.11+ and SQLite 3.37+ (the `vitals` and `conditions` tables use `STRICT`). Python ships with its own SQLite, so check that one:

```bash
python -c "import sqlite3; print(sqlite3.sqlite_version)"
```

Windows:

```powershell
git clone https://github.com/darren-moy/hospital.git
cd hospital
python -m venv venv
venv\Scripts\activate
pip install -r requirements-dev.txt
```

macOS:

```bash
git clone https://github.com/darren-moy/hospital.git
cd hospital
/usr/bin/python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
```

On my Mac the default `python3` had an old SQLite and failed with `near "STRICT": syntax error`. Using `/usr/bin/python3` fixed it.

Then create the database:

```bash
python -m hospital.db
```

To fill it with a few fictional patients so there's something to look at:

```bash
python -m hospital.seed
```

Run these from the repo root, which is where `hospital.db` gets created.

## Running it

```bash
python -m hospital.web.app
```

Go to http://127.0.0.1:5000. Search a last name (2+ letters) and click an MRN to open the chart.

The site is read-only right now. To add data, use the Python functions:

```python
from hospital.domain.patients import register_patient
from hospital.domain.allergies import add_allergy
from hospital.domain.encounters import start_encounter, close_encounter
from hospital.domain.vitals import record_vitals, list_vitals
from hospital.domain.conditions import add_condition

mrn = register_patient("Ada", "Lovelace", "1815-12-10", "F")   # "100001"
add_allergy(mrn, "Penicillin", "severe", reaction="Rash")
add_condition(mrn, "E11.9", "Type 2 diabetes", onset_date="2020-01-01")

visit = start_encounter(mrn, "outpatient", "Annual checkup")
record_vitals(visit, systolic=150, diastolic=95, heart_rate=72, temperature_f=98.6)
list_vitals(visit)[0]["flags"]   # ["High blood pressure"]
close_encounter(visit)
```

Bad input raises a `ValueError` with a plain-English message, e.g. starting a second encounter while one is open.

For debug mode, set `FLASK_DEBUG=1` before running (`$env:FLASK_DEBUG = "1"` in PowerShell). Don't use it anywhere public.

## Tests

```bash
python -m pytest tests
```

There are three groups. Each test gets its own temporary database, so `hospital.db` is never touched.

- `tests/unit/`: each module's functions and the web routes
- `tests/regression/`: one test for every bug I've fixed, so it can't come back
- `tests/schema/`: the vitals and conditions tables, tested at their limits. These were generated with a Claude Code agent (`.claude/agents/schema-test-writer.md`) and then reviewed.

Run one group with `python -m pytest tests/unit`.

## Layout

```
hospital/
  db.py           connection + setup
  schema.sql      tables and constraints
  seed.py         fictional demo patients
  domain/         patients, allergies, encounters, vitals, conditions
  web/            Flask routes (app.py) and Jinja templates
tests/            pytest: unit/, regression/, schema/ (generated)
```

## Known gaps / todo

- Can't add or edit records from the website yet
- No login
- No migrations: if `schema.sql` changes, delete `hospital.db` and run `python -m hospital.db` again
