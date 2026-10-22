import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import db


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


@pytest.fixture
def patient():
    """Register one patient and return their MRN."""
    from patients import register_patient

    return register_patient("Ada", "Lovelace", "1815-12-10", "F")


@pytest.fixture
def open_encounter(patient):
    """Start an open encounter for `patient` and return its id."""
    from encounters import start_encounter

    return start_encounter(patient, "outpatient", "Checkup")


@pytest.fixture
def closed_encounter(patient):
    """Start and close an encounter for `patient`; return its id."""
    from encounters import close_encounter, start_encounter

    encounter_id = start_encounter(patient, "outpatient", "Checkup")
    close_encounter(encounter_id)
    return encounter_id
