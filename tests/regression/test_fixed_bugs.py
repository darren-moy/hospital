"""Regression tests: one test per bug we already fixed, so it can't quietly come back.

When you fix a bug, add a test here that fails without the fix. Name it after the
bug and say in the docstring what went wrong. (The conditions and vitals fixes are
pinned down in tests/schema/, which covers them in more depth.)
"""

import sqlite3

import pytest

from hospital.db import get_connection
from hospital.domain.allergies import add_allergy, list_allergies
from hospital.domain.encounters import (
    close_encounter,
    list_encounters,
    open_encounters,
    start_encounter,
)
from hospital.domain.patients import find_patient_by_mrn, register_patient, search_by_last_name
from hospital.web.app import app, utc_iso

# --- patients.py ---------------------------------------------------------------


@pytest.mark.parametrize("bad", [None, 100001, 1.5, ["100001"], b"100001"])
def test_non_text_mrn_gives_value_error_not_attribute_error(bad):
    """A non-string MRN used to crash with AttributeError on .strip()."""
    with pytest.raises(ValueError, match="MRN must be text"):
        find_patient_by_mrn(bad)
    with pytest.raises(ValueError, match="MRN must be text"):
        list_allergies(bad)


@pytest.mark.parametrize("dob", ["20200101", "2020-W01-1", "2020-1-1", "2020/01/01", "٢٠٢٠-٠١-٠١"])
def test_birth_date_must_be_strict_yyyy_mm_dd(dob):
    """Python 3.11+ date.fromisoformat accepts compact forms the schema CHECK rejects."""
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        register_patient("Ada", "Lovelace", dob, "F")
    assert search_by_last_name("Lo") == []


@pytest.mark.parametrize("bad", [None, 20200101, b"2020-01-01"])
def test_non_text_birth_date_gives_value_error(bad):
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        register_patient("Ada", "Lovelace", bad, "F")


@pytest.mark.parametrize("bad", [None, 5, ["Lo"]])
def test_non_text_search_gives_value_error(bad):
    with pytest.raises(ValueError, match="must be text"):
        search_by_last_name(bad)


def test_search_treats_percent_and_underscore_literally(patient):
    """Wildcards in the search box must not match every patient."""
    assert search_by_last_name("%%") == []
    assert search_by_last_name("L_") == []
    assert search_by_last_name("\\\\") == []


# --- allergies.py / encounters.py ----------------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        (None, "mild"),
        ("Latex", None),
        (5, "mild"),
        ("Latex", ["mild"]),
    ],
)
def test_add_allergy_non_text_input_gives_value_error(patient, args):
    """Non-text substance or severity used to crash with AttributeError on .strip()."""
    with pytest.raises(ValueError, match="must be text"):
        add_allergy(patient, *args)


def test_add_allergy_non_text_reaction_gives_value_error(patient):
    with pytest.raises(ValueError, match="Reaction must be text"):
        add_allergy(patient, "Latex", "mild", reaction=5)
    assert list_allergies(patient) == []


@pytest.mark.parametrize(
    "args", [(None, "Reason"), ("outpatient", None), (5, "Reason"), ("outpatient", 5)]
)
def test_start_encounter_non_text_input_gives_value_error(patient, args):
    """Non-text type or reason used to crash with AttributeError on .strip()."""
    with pytest.raises(ValueError, match="must be text"):
        start_encounter(patient, *args)
    assert list_encounters(patient) == []


def test_close_encounter_rejects_booleans(open_encounter):
    """True == 1 and passed the isinstance(int) check, so close_encounter(True) closed encounter 1."""
    assert open_encounter == 1
    with pytest.raises(ValueError, match="positive whole number"):
        close_encounter(True)
    assert open_encounters()[0]["id"] == open_encounter  # still open


@pytest.mark.parametrize("huge", [2**63, 2**70])
def test_close_encounter_huge_id_gives_value_error(huge):
    """Ints beyond SQLite's range used to raise OverflowError."""
    with pytest.raises(ValueError, match="positive whole number"):
        close_encounter(huge)


# --- schema.sql ----------------------------------------------------------------


@pytest.mark.parametrize("dob", ["2023-02-29", "2020-13-01", "2020-04-31", "not a date"])
def test_database_rejects_impossible_birth_dates_even_without_python(dob):
    """date(x) = x is NULL for invalid dates and a CHECK passes on NULL; it must use IS."""
    with pytest.raises(sqlite3.IntegrityError):
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO patients (mrn, first_name, last_name, date_of_birth, sex) "
                "VALUES ('1', 'Ada', 'Lovelace', ?, 'F')",
                [dob],
            )


def test_database_allows_only_one_open_encounter_even_without_python(patient, open_encounter):
    with pytest.raises(sqlite3.IntegrityError):
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO encounters (patient_id, encounter_type, reason) "
                "SELECT id, 'outpatient', 'Again' FROM patients WHERE mrn = ?",
                [patient],
            )


def test_patient_with_records_cannot_be_deleted(patient):
    """Foreign keys are off in SQLite unless PRAGMA foreign_keys = ON is set per connection."""
    add_allergy(patient, "Latex", "mild")
    with pytest.raises(sqlite3.IntegrityError):
        with get_connection() as conn:
            conn.execute("DELETE FROM patients WHERE mrn = ?", [patient])


# --- app.py --------------------------------------------------------------------


def test_stored_html_is_escaped_on_the_chart(patient):
    """Anything typed into a record must show as text, never run as HTML."""
    payload = "<script>alert(1)</script>"
    add_allergy(patient, payload, "mild", reaction=payload)
    start_encounter(patient, "outpatient", payload)
    page = app.test_client().get(f"/patients/{patient}").data.decode()
    assert payload not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_search_text_is_escaped_on_the_search_page():
    payload = "<script>alert(1)</script>"
    page = app.test_client().get("/", query_string={"q": payload}).data.decode()
    assert payload not in page


def test_timestamps_are_marked_as_utc_for_the_browser():
    """SQLite timestamps have no zone; without the Z, browsers read them as local time."""
    assert utc_iso("2026-11-09 03:12:00") == "2026-11-09T03:12:00Z"


def test_chart_timestamps_carry_the_utc_marker(patient, open_encounter):
    page = app.test_client().get(f"/patients/{patient}").data.decode()
    assert '<time datetime="' in page and 'Z">' in page


def test_flask_debug_is_off_by_default():
    """Debug mode exposes a console that can run code, so only FLASK_DEBUG=1 may enable it."""
    import pathlib

    source = pathlib.Path(__file__).parents[2].joinpath("hospital", "web", "app.py").read_text()
    assert 'debug=os.environ.get("FLASK_DEBUG") == "1"' in source
    assert "debug=True" not in source
