import itertools
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone

import pytest

import db
from conditions import (
    ICD10_PATTERN,
    MAX_DESCRIPTION_LENGTH,
    add_condition,
    list_conditions,
    resolve_condition,
)
from patients import register_patient

# Schema value, pinned independently of conditions.MAX_DESCRIPTION_LENGTH.
SCHEMA_MAX_DESCRIPTION = 200

UNKNOWN_MRN = "999999"
NO_SUCH_PATIENT_ID = 999999

CODE_MSG = "ICD-10 code must look like E11.9 or I10."
CODE_TYPE_MSG = "ICD-10 code must be text."
DESC_MSG = f"Description must be 1 to {SCHEMA_MAX_DESCRIPTION} characters."
DESC_TYPE_MSG = "Description must be text."
ID_MSG = "Condition id must be a positive whole number."
ONSET_FORMAT_MSG = "Onset date must be a real date in YYYY-MM-DD format."
ONSET_FUTURE_MSG = "Onset date can't be in the future."
RESOLVED_FORMAT_MSG = "Resolved date must be a real date in YYYY-MM-DD format."
RESOLVED_FUTURE_MSG = "Resolved date can't be in the future."
RESOLVED_BEFORE_ONSET_MSG = "Resolved date can't be before the onset date."

VALID_DATES = ["2020-01-01", "2020-02-29", "1815-12-10", "0001-01-01", "9999-12-31"]

# Everything here should be refused by `date(x) = x`.
INVALID_DATES = [
    "2020-02-30",
    "2021-02-29",
    "2020-04-31",
    "2020-13-01",
    "2020-01-32",
    "2020/01/01",
    "20200101",
    "2020-1-1",
    "not-a-date",
    "",
    "2020-01-01 12:00:00",
]

# Rejected by the API whatever the Python version. Compact ISO forms are
# covered separately because date.fromisoformat accepts them from 3.11 on.
MALFORMED_API_DATES = [
    "2020-02-30",
    "2020-13-01",
    "2020/01/01",
    "01-02-2020",
    "2020-1-1",
    "not-a-date",
    "",
    "   ",
    20200101,
    date(2020, 1, 1),
    ["2020-01-01"],
]

COMPACT_ISO_DATES = ["20200101", "2020-W01-1"]


# ---------------------------------------------------------------- helpers

def valid_row(patient_id, **overrides):
    """Column values for a minimal valid conditions row."""
    row = {
        "patient_id": patient_id,
        "icd10_code": "E11.9",
        "description": "Type 2 diabetes",
    }
    row.update(overrides)
    return row


def insert_raw(**cols):
    """Insert a conditions row with raw SQL. Returns the new id."""
    names = ", ".join(cols)
    marks = ", ".join("?" for _ in cols)
    with db.get_connection() as conn:
        cur = conn.execute(
            f"INSERT INTO conditions ({names}) VALUES ({marks})", list(cols.values())
        )
    return cur.lastrowid


def fetch_row(condition_id):
    with db.get_connection() as conn:
        row = conn.execute("SELECT * FROM conditions WHERE id = ?", [condition_id]).fetchone()
    return dict(row) if row else None


def count_rows():
    with db.get_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM conditions").fetchone()[0]


def get_patient_id(mrn):
    with db.get_connection() as conn:
        return conn.execute("SELECT id FROM patients WHERE mrn = ?", [mrn]).fetchone()["id"]


def codes(rows):
    return [row["icd10_code"] for row in rows]


@pytest.fixture
def pid(patient):
    """Internal patients.id for the `patient` fixture."""
    return get_patient_id(patient)


@pytest.fixture
def other_patient():
    """A second patient's MRN."""
    return register_patient("Grace", "Hopper", "1906-12-09", "F")


@pytest.fixture
def other_pid(other_patient):
    return get_patient_id(other_patient)


def tomorrow():
    return (date.today() + timedelta(days=1)).isoformat()


# ---------------------------------------------------------------- schema: basics

def test_valid_minimal_row_accepted(pid):
    row = fetch_row(insert_raw(**valid_row(pid)))
    assert row["patient_id"] == pid
    assert row["icd10_code"] == "E11.9"
    assert row["description"] == "Type 2 diabetes"


def test_valid_full_row_accepted(pid):
    row = fetch_row(insert_raw(**valid_row(
        pid,
        status="resolved",
        onset_date="2020-01-01",
        resolved_date="2020-06-01",
        recorded_at="2020-06-02 09:00:00",
    )))
    assert row["status"] == "resolved"
    assert row["onset_date"] == "2020-01-01"
    assert row["resolved_date"] == "2020-06-01"
    assert row["recorded_at"] == "2020-06-02 09:00:00"


@pytest.mark.parametrize("column", ["patient_id", "icd10_code", "description"])
def test_omitting_required_column_rejected(pid, column):
    row = valid_row(pid)
    del row[column]
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(**row)


@pytest.mark.parametrize(
    "column", ["patient_id", "icd10_code", "description", "status", "recorded_at"]
)
def test_explicit_null_in_not_null_column_rejected(pid, column):
    row = valid_row(pid)
    row[column] = None
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(**row)


def test_defaults_applied_when_columns_omitted(pid):
    row = fetch_row(insert_raw(**valid_row(pid)))
    assert row["status"] == "active"
    assert row["onset_date"] is None
    assert row["resolved_date"] is None


def test_default_recorded_at_is_current_utc_timestamp(pid):
    row = fetch_row(insert_raw(**valid_row(pid)))
    recorded = datetime.strptime(row["recorded_at"], "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=timezone.utc
    )
    assert abs(datetime.now(timezone.utc) - recorded) < timedelta(minutes=1)


# ---------------------------------------------------------------- schema: icd10_code

@pytest.mark.parametrize(
    "code",
    ["E11.9", "I10", "S72.001A", "A00", "Z99", "A0Z", "E11.90", "E11.900", "E11.9000"],
)
def test_icd10_code_valid_format_accepted(pid, code):
    assert fetch_row(insert_raw(**valid_row(pid, icd10_code=code)))["icd10_code"] == code


@pytest.mark.parametrize(
    "code",
    [
        "",
        "E",
        "E1",            # length 2, one below the minimum
        "E11.90000",     # length 9, one above the maximum
        "S72.001AB",
        "123",
        "!!!",
        "e11.9",
        "e11",
        "E1a",
        "E11.9a",
        "EE1.9",
        "E11 9",
        "E11-9",
        "E11_9",
        " E11",
        "E11 ",
        "E11\n",
        ".E11",
        "1E1",
        "É11",
    ],
)
def test_icd10_code_invalid_format_rejected(pid, code):
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(**valid_row(pid, icd10_code=code))
    assert count_rows() == 0


# ---------------------------------------------------------------- schema: description

@pytest.mark.parametrize("length", [1, SCHEMA_MAX_DESCRIPTION])
def test_description_length_boundary_accepted(pid, length):
    text = "x" * length
    assert fetch_row(insert_raw(**valid_row(pid, description=text)))["description"] == text


@pytest.mark.parametrize("length", [0, SCHEMA_MAX_DESCRIPTION + 1])
def test_description_length_out_of_range_rejected(pid, length):
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(**valid_row(pid, description="x" * length))


def test_description_length_counts_characters_not_bytes(pid):
    text = "é" * SCHEMA_MAX_DESCRIPTION
    assert fetch_row(insert_raw(**valid_row(pid, description=text)))["description"] == text


# ---------------------------------------------------------------- schema: status

def test_status_active_accepted(pid):
    row = fetch_row(insert_raw(**valid_row(pid, status="active")))
    assert row["status"] == "active"


def test_status_resolved_accepted(pid):
    row = fetch_row(insert_raw(**valid_row(pid, status="resolved", resolved_date="2020-01-01")))
    assert row["status"] == "resolved"


@pytest.mark.parametrize("status", ["inactive", "", "Active", "ACTIVE"])
def test_status_unlisted_or_wrong_case_rejected_without_resolved_date(pid, status):
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(**valid_row(pid, status=status))


@pytest.mark.parametrize("status", ["inactive", "Resolved", "RESOLVED"])
def test_status_unlisted_or_wrong_case_rejected_with_resolved_date(pid, status):
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(**valid_row(pid, status=status, resolved_date="2020-01-01"))


# ---------------------------------------------------------------- schema: dates

@pytest.mark.parametrize("value", VALID_DATES)
def test_onset_date_valid_accepted(pid, value):
    assert fetch_row(insert_raw(**valid_row(pid, onset_date=value)))["onset_date"] == value


def test_onset_date_null_accepted(pid):
    assert fetch_row(insert_raw(**valid_row(pid, onset_date=None)))["onset_date"] is None


@pytest.mark.parametrize("value", INVALID_DATES)
def test_onset_date_invalid_rejected(pid, value):
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(**valid_row(pid, onset_date=value))


@pytest.mark.parametrize("value", VALID_DATES)
def test_resolved_date_valid_accepted(pid, value):
    row = fetch_row(insert_raw(**valid_row(pid, status="resolved", resolved_date=value)))
    assert row["resolved_date"] == value


@pytest.mark.parametrize("value", INVALID_DATES)
def test_resolved_date_invalid_rejected(pid, value):
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(**valid_row(pid, status="resolved", resolved_date=value))


# ---------------------------------------------------------------- schema: status/resolved_date

def test_active_without_resolved_date_accepted(pid):
    row = fetch_row(insert_raw(**valid_row(pid, status="active", resolved_date=None)))
    assert (row["status"], row["resolved_date"]) == ("active", None)


def test_active_with_resolved_date_rejected(pid):
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(**valid_row(pid, status="active", resolved_date="2020-01-01"))


def test_default_status_with_resolved_date_rejected(pid):
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(**valid_row(pid, resolved_date="2020-01-01"))


def test_resolved_with_resolved_date_accepted(pid):
    row = fetch_row(insert_raw(**valid_row(pid, status="resolved", resolved_date="2020-01-01")))
    assert (row["status"], row["resolved_date"]) == ("resolved", "2020-01-01")


def test_resolved_without_resolved_date_rejected(pid):
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(**valid_row(pid, status="resolved", resolved_date=None))


# ---------------------------------------------------------------- schema: resolved >= onset

@pytest.mark.parametrize(
    "onset, resolved",
    [
        ("2020-01-01", "2020-01-02"),  # after
        ("2020-01-01", "2020-01-01"),  # equal
        (None, "2020-01-01"),          # no onset to compare against
    ],
)
def test_resolved_date_on_or_after_onset_accepted(pid, onset, resolved):
    row = fetch_row(insert_raw(**valid_row(
        pid, status="resolved", onset_date=onset, resolved_date=resolved
    )))
    assert (row["onset_date"], row["resolved_date"]) == (onset, resolved)


def test_resolved_date_before_onset_rejected(pid):
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(**valid_row(
            pid, status="resolved", onset_date="2020-01-02", resolved_date="2020-01-01"
        ))


def test_active_with_onset_and_no_resolved_date_accepted(pid):
    row = fetch_row(insert_raw(**valid_row(pid, onset_date="2020-01-01")))
    assert (row["onset_date"], row["resolved_date"]) == ("2020-01-01", None)


# ---------------------------------------------------------------- schema: partial unique index

def test_duplicate_active_code_same_patient_rejected(pid):
    insert_raw(**valid_row(pid))
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(**valid_row(pid))
    assert count_rows() == 1


def test_active_and_resolved_same_code_accepted(pid):
    insert_raw(**valid_row(pid))
    insert_raw(**valid_row(pid, status="resolved", resolved_date="2020-01-01"))
    assert count_rows() == 2


def test_two_resolved_same_code_accepted(pid):
    insert_raw(**valid_row(pid, status="resolved", resolved_date="2020-01-01"))
    insert_raw(**valid_row(pid, status="resolved", resolved_date="2020-01-01"))
    assert count_rows() == 2


def test_same_active_code_different_patients_accepted(pid, other_pid):
    insert_raw(**valid_row(pid))
    insert_raw(**valid_row(other_pid))
    assert count_rows() == 2


def test_different_active_codes_same_patient_accepted(pid):
    insert_raw(**valid_row(pid, icd10_code="E11.9"))
    insert_raw(**valid_row(pid, icd10_code="I10"))
    assert count_rows() == 2


def test_reactivating_resolved_duplicate_of_active_code_rejected(pid):
    insert_raw(**valid_row(pid))
    resolved_id = insert_raw(**valid_row(pid, status="resolved", resolved_date="2020-01-01"))
    with pytest.raises(sqlite3.IntegrityError):
        with db.get_connection() as conn:
            conn.execute(
                "UPDATE conditions SET status = 'active', resolved_date = NULL WHERE id = ?",
                [resolved_id],
            )


# ---------------------------------------------------------------- schema: foreign key

def test_nonexistent_patient_rejected():
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(**valid_row(NO_SUCH_PATIENT_ID))


def test_deleting_patient_with_condition_rejected(pid):
    insert_raw(**valid_row(pid))
    with pytest.raises(sqlite3.IntegrityError):
        with db.get_connection() as conn:
            conn.execute("DELETE FROM patients WHERE id = ?", [pid])
    with db.get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM patients WHERE id = ?", [pid]).fetchone()[0] == 1


def test_deleting_patient_with_resolved_condition_rejected(pid):
    insert_raw(**valid_row(pid, status="resolved", resolved_date="2020-01-01"))
    with pytest.raises(sqlite3.IntegrityError):
        with db.get_connection() as conn:
            conn.execute("DELETE FROM patients WHERE id = ?", [pid])


def test_deleting_patient_without_conditions_accepted(pid):
    with db.get_connection() as conn:
        conn.execute("DELETE FROM patients WHERE id = ?", [pid])
        assert conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 0


# ---------------------------------------------------------------- schema: STRICT

def test_table_is_strict():
    with db.get_connection() as conn:
        row = conn.execute("SELECT strict FROM pragma_table_list('conditions')").fetchone()
    assert row["strict"] == 1


@pytest.mark.parametrize("value", ["abc", 1.5, b"\x01"])
def test_patient_id_wrong_type_rejected(pid, value):
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(**valid_row(value))


@pytest.mark.parametrize("value", ["abc", 1.5])
def test_id_wrong_type_rejected(pid, value):
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(id=value, **valid_row(pid))


@pytest.mark.parametrize(
    "convert", [str, float], ids=["text_digits", "whole_float"]
)
def test_patient_id_lossless_conversion_stored_as_integer(pid, convert):
    row = fetch_row(insert_raw(**valid_row(convert(pid))))
    assert row["patient_id"] == pid
    assert isinstance(row["patient_id"], int)


@pytest.mark.parametrize(
    "column", ["icd10_code", "description", "status", "onset_date", "resolved_date", "recorded_at"]
)
def test_blob_in_text_column_rejected(pid, column):
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(**valid_row(pid, **{column: b"E11.9"}))


@pytest.mark.parametrize("value, stored", [(123, "123"), (1.5, "1.5")])
def test_number_in_text_description_stored_as_text(pid, value, stored):
    assert fetch_row(insert_raw(**valid_row(pid, description=value)))["description"] == stored


@pytest.mark.parametrize("value", [123, 1.5])
def test_number_in_text_icd10_code_rejected_by_format_check(pid, value):
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(**valid_row(pid, icd10_code=value))


# ---------------------------------------------------------------- add_condition

def test_add_condition_returns_id_and_stores_row(patient, pid):
    condition_id = add_condition(patient, "E11.9", "Type 2 diabetes", "2020-01-15")
    assert isinstance(condition_id, int)
    row = fetch_row(condition_id)
    assert row["id"] == condition_id
    assert row["patient_id"] == pid
    assert row["icd10_code"] == "E11.9"
    assert row["description"] == "Type 2 diabetes"
    assert row["status"] == "active"
    assert row["onset_date"] == "2020-01-15"
    assert row["resolved_date"] is None
    assert row["recorded_at"]


def test_add_condition_onset_date_optional(patient):
    assert fetch_row(add_condition(patient, "I10", "Hypertension"))["onset_date"] is None


def test_add_condition_explicit_none_onset_stored_null(patient):
    assert fetch_row(add_condition(patient, "I10", "Hypertension", None))["onset_date"] is None


@pytest.mark.parametrize(
    "raw, stored",
    [("e11.9", "E11.9"), ("  I10  ", "I10"), ("\ts72.001a\n", "S72.001A")],
)
def test_add_condition_code_stripped_and_uppercased(patient, raw, stored):
    assert fetch_row(add_condition(patient, raw, "Something"))["icd10_code"] == stored


def test_add_condition_description_stripped_case_preserved(patient):
    row = fetch_row(add_condition(patient, "I10", "  Essential Hypertension\n"))
    assert row["description"] == "Essential Hypertension"


def test_add_condition_onset_date_stripped(patient):
    assert fetch_row(add_condition(patient, "I10", "Hypertension", " 2020-01-15 "))[
        "onset_date"
    ] == "2020-01-15"


def test_add_condition_mrn_stripped(patient, pid):
    assert fetch_row(add_condition(f"  {patient} ", "I10", "Hypertension"))["patient_id"] == pid


@pytest.mark.parametrize(
    "code",
    [
        "",
        "   ",
        "123",
        "!!!",
        "E1",
        "E11 9",
        "EE1.9",
        "E11.90000",
        "E119",
        "E11.",
        "E11.9.9",
    ],
)
def test_add_condition_invalid_code_rejected(patient, code):
    with pytest.raises(ValueError, match=re.escape(CODE_MSG)):
        add_condition(patient, code, "Something")
    assert count_rows() == 0


@pytest.mark.parametrize("code", [None, 123, 1.5, True, b"E11.9", ["E11.9"]])
def test_add_condition_non_string_code_rejected(patient, code):
    with pytest.raises(ValueError, match=re.escape(CODE_TYPE_MSG)):
        add_condition(patient, code, "Something")


@pytest.mark.parametrize("text", ["", "   ", "\n\t", "x" * (SCHEMA_MAX_DESCRIPTION + 1)])
def test_add_condition_invalid_description_length_rejected(patient, text):
    with pytest.raises(ValueError, match=re.escape(DESC_MSG)):
        add_condition(patient, "I10", text)
    assert count_rows() == 0


@pytest.mark.parametrize("length", [1, SCHEMA_MAX_DESCRIPTION])
def test_add_condition_description_length_boundary_accepted(patient, length):
    text = "x" * length
    assert fetch_row(add_condition(patient, "I10", text))["description"] == text


def test_add_condition_description_length_measured_after_strip(patient):
    text = "x" * SCHEMA_MAX_DESCRIPTION
    assert fetch_row(add_condition(patient, "I10", f"  {text}  "))["description"] == text


@pytest.mark.parametrize("text", [None, 123, 1.5, True, b"text", ["text"]])
def test_add_condition_non_string_description_rejected(patient, text):
    with pytest.raises(ValueError, match=re.escape(DESC_TYPE_MSG)):
        add_condition(patient, "I10", text)


@pytest.mark.parametrize("value", MALFORMED_API_DATES, ids=repr)
def test_add_condition_malformed_onset_rejected(patient, value):
    with pytest.raises(ValueError, match=re.escape(ONSET_FORMAT_MSG)):
        add_condition(patient, "I10", "Hypertension", value)
    assert count_rows() == 0


@pytest.mark.parametrize("value", COMPACT_ISO_DATES)
def test_add_condition_non_yyyy_mm_dd_onset_rejected(patient, value):
    with pytest.raises(ValueError, match=re.escape(ONSET_FORMAT_MSG)):
        add_condition(patient, "I10", "Hypertension", value)


def test_add_condition_future_onset_rejected(patient):
    with pytest.raises(ValueError, match=re.escape(ONSET_FUTURE_MSG)):
        add_condition(patient, "I10", "Hypertension", tomorrow())
    assert count_rows() == 0


def test_add_condition_today_onset_accepted(patient):
    today = date.today().isoformat()
    assert fetch_row(add_condition(patient, "I10", "Hypertension", today))["onset_date"] == today


def test_add_condition_unknown_mrn_rejected():
    with pytest.raises(ValueError, match=f"No patient with MRN {UNKNOWN_MRN}"):
        add_condition(UNKNOWN_MRN, "I10", "Hypertension")
    assert count_rows() == 0


def test_add_condition_duplicate_active_raises_value_error(patient):
    add_condition(patient, "E11.9", "Type 2 diabetes")
    with pytest.raises(ValueError, match=r"E11\.9 is already an active problem"):
        add_condition(patient, "E11.9", "Type 2 diabetes again")
    assert count_rows() == 1


def test_add_condition_duplicate_active_after_normalization_raises_value_error(patient):
    add_condition(patient, "E11.9", "Type 2 diabetes")
    with pytest.raises(ValueError, match=r"E11\.9 is already an active problem"):
        add_condition(patient, " e11.9 ", "Type 2 diabetes again")
    assert count_rows() == 1


def test_add_condition_same_code_different_patients_accepted(patient, other_patient):
    first = add_condition(patient, "E11.9", "Type 2 diabetes")
    second = add_condition(other_patient, "E11.9", "Type 2 diabetes")
    assert first != second
    assert count_rows() == 2


def test_add_condition_after_resolve_creates_new_active_row(patient):
    first = add_condition(patient, "E11.9", "Type 2 diabetes")
    resolve_condition(first)
    second = add_condition(patient, "E11.9", "Type 2 diabetes, recurred")
    assert second != first
    assert fetch_row(first)["status"] == "resolved"
    assert fetch_row(second)["status"] == "active"


def test_add_condition_rejected_description_error_does_not_claim_duplicate(patient):
    # A leading NUL passes the Python length check, but SQLite's length() stops
    # at the NUL and sees 0 characters, so the CHECK fails in the database.
    with pytest.raises(ValueError) as excinfo:
        add_condition(patient, "I10", "\x00Hypertension")
    assert "already an active problem" not in str(excinfo.value)


# ---------------------------------------------------------------- resolve_condition

def test_resolve_condition_explicit_date_stored(patient):
    condition_id = add_condition(patient, "I10", "Hypertension", "2020-01-01")
    assert resolve_condition(condition_id, "2020-06-01") is None
    row = fetch_row(condition_id)
    assert row["status"] == "resolved"
    assert row["resolved_date"] == "2020-06-01"


def test_resolve_condition_default_date_is_today(patient):
    condition_id = add_condition(patient, "I10", "Hypertension")
    before = date.today().isoformat()
    resolve_condition(condition_id)
    after = date.today().isoformat()
    row = fetch_row(condition_id)
    assert row["status"] == "resolved"
    assert before <= row["resolved_date"] <= after


def test_resolve_condition_date_stripped(patient):
    condition_id = add_condition(patient, "I10", "Hypertension")
    resolve_condition(condition_id, " 2020-06-01 ")
    assert fetch_row(condition_id)["resolved_date"] == "2020-06-01"


def test_resolve_condition_only_changes_target_row(patient):
    target = add_condition(patient, "I10", "Hypertension")
    other = add_condition(patient, "E11.9", "Type 2 diabetes")
    before = fetch_row(other)
    resolve_condition(target)
    assert fetch_row(other) == before


@pytest.mark.parametrize(
    "bad_id", [True, False, 1.0, 1.5, "1", "abc", None, 0, -1, [1]], ids=repr
)
def test_resolve_condition_invalid_id_rejected(patient, bad_id):
    condition_id = add_condition(patient, "I10", "Hypertension")
    before = fetch_row(condition_id)
    with pytest.raises(ValueError, match=re.escape(ID_MSG)):
        resolve_condition(bad_id)
    assert fetch_row(condition_id) == before


def test_resolve_condition_nonexistent_id_rejected():
    with pytest.raises(ValueError, match="No active condition with id 999999"):
        resolve_condition(999999)


@pytest.mark.parametrize("huge_id", [2**63 - 1, 2**63], ids=["int64_max", "int64_max_plus_1"])
def test_resolve_condition_id_beyond_any_row_rejected(huge_id):
    with pytest.raises(ValueError):
        resolve_condition(huge_id)


def test_resolve_condition_already_resolved_rejected(patient):
    condition_id = add_condition(patient, "I10", "Hypertension")
    resolve_condition(condition_id, "2020-06-01")
    with pytest.raises(ValueError, match=f"No active condition with id {condition_id}"):
        resolve_condition(condition_id, "2020-07-01")
    assert fetch_row(condition_id)["resolved_date"] == "2020-06-01"


def test_resolve_condition_before_onset_rejected_and_row_unchanged(patient):
    condition_id = add_condition(patient, "I10", "Hypertension", "2020-06-01")
    before = fetch_row(condition_id)
    with pytest.raises(ValueError, match=re.escape(RESOLVED_BEFORE_ONSET_MSG)):
        resolve_condition(condition_id, "2020-05-31")
    assert fetch_row(condition_id) == before


def test_resolve_condition_same_day_as_onset_accepted(patient):
    condition_id = add_condition(patient, "I10", "Hypertension", "2020-06-01")
    resolve_condition(condition_id, "2020-06-01")
    row = fetch_row(condition_id)
    assert row["status"] == "resolved"
    assert row["resolved_date"] == "2020-06-01"


def test_resolve_condition_future_date_rejected_and_row_unchanged(patient):
    condition_id = add_condition(patient, "I10", "Hypertension")
    before = fetch_row(condition_id)
    with pytest.raises(ValueError, match=re.escape(RESOLVED_FUTURE_MSG)):
        resolve_condition(condition_id, tomorrow())
    assert fetch_row(condition_id) == before


def test_resolve_condition_today_accepted(patient):
    condition_id = add_condition(patient, "I10", "Hypertension")
    today = date.today().isoformat()
    resolve_condition(condition_id, today)
    assert fetch_row(condition_id)["resolved_date"] == today


@pytest.mark.parametrize("value", MALFORMED_API_DATES, ids=repr)
def test_resolve_condition_malformed_date_rejected_and_row_unchanged(patient, value):
    condition_id = add_condition(patient, "I10", "Hypertension")
    before = fetch_row(condition_id)
    with pytest.raises(ValueError, match=re.escape(RESOLVED_FORMAT_MSG)):
        resolve_condition(condition_id, value)
    assert fetch_row(condition_id) == before


@pytest.mark.parametrize("value", COMPACT_ISO_DATES)
def test_resolve_condition_non_yyyy_mm_dd_date_rejected(patient, value):
    condition_id = add_condition(patient, "I10", "Hypertension")
    with pytest.raises(ValueError, match=re.escape(RESOLVED_FORMAT_MSG)):
        resolve_condition(condition_id, value)


# ---------------------------------------------------------------- list_conditions

def test_list_conditions_default_returns_active_only(patient):
    active = add_condition(patient, "I10", "Hypertension")
    resolved = add_condition(patient, "E11.9", "Type 2 diabetes")
    resolve_condition(resolved)
    assert [row["id"] for row in list_conditions(patient)] == [active]


def test_list_conditions_include_resolved_returns_both(patient):
    active = add_condition(patient, "I10", "Hypertension")
    resolved = add_condition(patient, "E11.9", "Type 2 diabetes")
    resolve_condition(resolved)
    rows = list_conditions(patient, include_resolved=True)
    assert {row["id"] for row in rows} == {active, resolved}


def test_list_conditions_returns_dicts_with_expected_keys_and_values(patient):
    condition_id = add_condition(patient, "I10", "Hypertension", "2020-01-01")
    resolve_condition(condition_id, "2020-06-01")
    assert list_conditions(patient, include_resolved=True) == [
        {
            "id": condition_id,
            "icd10_code": "I10",
            "description": "Hypertension",
            "status": "resolved",
            "onset_date": "2020-01-01",
            "resolved_date": "2020-06-01",
        }
    ]


def test_list_conditions_row_is_plain_dict(patient):
    add_condition(patient, "I10", "Hypertension")
    assert type(list_conditions(patient)[0]) is dict


def test_list_conditions_orders_by_onset_newest_first(patient):
    add_condition(patient, "A00", "Oldest", "2010-01-01")
    add_condition(patient, "B00", "Newest", "2020-01-01")
    add_condition(patient, "C00", "Middle", "2015-01-01")
    assert codes(list_conditions(patient)) == ["B00", "C00", "A00"]


def test_list_conditions_null_onset_sorts_last(patient):
    # SQLite treats NULL as smaller than any other value, so DESC puts it last.
    add_condition(patient, "A00", "No onset")
    add_condition(patient, "B00", "Dated", "2010-01-01")
    add_condition(patient, "C00", "Dated later", "2020-01-01")
    rows = list_conditions(patient)
    assert codes(rows) == ["C00", "B00", "A00"]
    assert rows[-1]["onset_date"] is None


def test_list_conditions_same_onset_ties_broken_by_code(patient):
    for code in ["Z99", "A00", "M54.5"]:
        add_condition(patient, code, "Tie", "2020-01-01")
    assert codes(list_conditions(patient)) == ["A00", "M54.5", "Z99"]


def test_list_conditions_null_onset_ties_broken_by_code(patient):
    for code in ["Z99", "A00", "M54.5"]:
        add_condition(patient, code, "Tie")
    assert codes(list_conditions(patient)) == ["A00", "M54.5", "Z99"]


def test_list_conditions_active_sorted_before_resolved(patient):
    resolved_recent = add_condition(patient, "A00", "Resolved recent onset", "2024-01-01")
    resolve_condition(resolved_recent, "2024-02-01")
    add_condition(patient, "B00", "Active old onset", "2000-01-01")
    add_condition(patient, "C00", "Active no onset")
    resolved_old = add_condition(patient, "D00", "Resolved old onset", "1999-01-01")
    resolve_condition(resolved_old, "1999-02-01")
    resolved_none = add_condition(patient, "E00", "Resolved no onset")
    resolve_condition(resolved_none, "2024-03-01")

    rows = list_conditions(patient, include_resolved=True)
    assert codes(rows) == ["B00", "C00", "A00", "D00", "E00"]
    assert [row["status"] for row in rows] == ["active"] * 2 + ["resolved"] * 3


@pytest.mark.parametrize("include_resolved", [False, True])
def test_list_conditions_unknown_mrn_rejected(include_resolved):
    with pytest.raises(ValueError, match=f"No patient with MRN {UNKNOWN_MRN}"):
        list_conditions(UNKNOWN_MRN, include_resolved=include_resolved)


@pytest.mark.parametrize("include_resolved", [False, True])
def test_list_conditions_patient_with_none_returns_empty_list(patient, include_resolved):
    assert list_conditions(patient, include_resolved=include_resolved) == []


def test_list_conditions_only_returns_that_patients_rows(patient, other_patient):
    mine = add_condition(patient, "I10", "Hypertension")
    theirs = add_condition(other_patient, "E11.9", "Type 2 diabetes")
    resolved_theirs = add_condition(other_patient, "A00", "Cholera")
    resolve_condition(resolved_theirs)
    assert [row["id"] for row in list_conditions(patient, include_resolved=True)] == [mine]
    assert {row["id"] for row in list_conditions(other_patient, include_resolved=True)} == {
        theirs,
        resolved_theirs,
    }


def test_list_conditions_mrn_stripped(patient):
    condition_id = add_condition(patient, "I10", "Hypertension")
    assert [row["id"] for row in list_conditions(f" {patient} ")] == [condition_id]


# ---------------------------------------------------------------- drift

def test_max_description_length_matches_schema(pid):
    assert MAX_DESCRIPTION_LENGTH == SCHEMA_MAX_DESCRIPTION
    insert_raw(**valid_row(pid, description="x" * MAX_DESCRIPTION_LENGTH))
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(**valid_row(pid, description="x" * (MAX_DESCRIPTION_LENGTH + 1)))


def test_every_python_valid_code_shape_accepted_by_schema(pid):
    """Every suffix length from the pattern, using each character class's extremes."""
    letters = "AZ"
    digits = "09"
    alnum = "09AZ"
    generated = []
    for head in itertools.product(letters, digits, alnum):
        generated.append("".join(head))
        for size in range(1, 5):
            for tail in itertools.product(alnum, repeat=size):
                generated.append("".join(head) + "." + "".join(tail))

    assert all(ICD10_PATTERN.fullmatch(code) for code in generated)
    assert max(len(code) for code in generated) == 8

    rejected = []
    with db.get_connection() as conn:
        for code in generated:
            try:
                conn.execute(
                    "INSERT INTO conditions (patient_id, icd10_code, description) "
                    "VALUES (?, ?, 'x')",
                    [pid, code],
                )
            except sqlite3.IntegrityError:
                rejected.append(code)
    assert rejected == []


@pytest.mark.parametrize(
    "code",
    [
        "E119",        # no dot
        "A00000",
        "E11.",        # trailing dot
        "E11..",
        "E11.9.9",     # second dot
        "E1A.B.C",
        "E11.9A.B",
        "E11\x00!!!",  # GLOB and length() stop at the NUL
    ],
    ids=repr,
)
def test_schema_accepts_code_that_python_rejects(patient, pid, code):
    """Pins known drift: the schema's code check is looser than ICD10_PATTERN.

    This is safe, since Python is the stricter side. Update this list if the
    schema is tightened to match.
    """
    assert ICD10_PATTERN.fullmatch(code) is None
    with pytest.raises(ValueError, match=re.escape(CODE_MSG)):
        add_condition(patient, code, "Something")
    assert fetch_row(insert_raw(**valid_row(pid, icd10_code=code)))["icd10_code"] == code
