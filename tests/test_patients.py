import pytest

from db import get_connection
from patients import find_patient_by_mrn, register_patient, search_by_last_name
from allergies import list_allergies

NOT_TEXT = [None, 100001, 1.5, ["100001"], b"100001", True]


@pytest.mark.parametrize("bad", NOT_TEXT)
def test_find_patient_rejects_non_text_mrn(bad):
    with pytest.raises(ValueError, match="MRN must be text"):
        find_patient_by_mrn(bad)


@pytest.mark.parametrize("bad", NOT_TEXT)
def test_domain_functions_reject_non_text_mrn(bad):
    # list_allergies goes through _get_patient_id, which every module shares
    with pytest.raises(ValueError, match="MRN must be text"):
        list_allergies(bad)


def test_mrn_with_spaces_is_trimmed(patient):
    assert find_patient_by_mrn(f"  {patient}  ")["mrn"] == patient


def test_unknown_mrn_still_returns_none():
    assert find_patient_by_mrn("999999") is None


@pytest.mark.parametrize("dob", [
    "20200101",       # compact ISO, accepted by date.fromisoformat on Python 3.11+
    "2020-W01-1",     # ISO week date
    "2020-1-1",
    "2020/01/01",
    "٢٠٢٠-٠١-٠١",     # non-ASCII digits
    "2020-01-01\n",   # only whitespace is stripped, so this one is actually fine
])
def test_dob_shape_is_strict(dob):
    if dob.strip() == "2020-01-01":
        assert register_patient("Ada", "Lovelace", dob, "F")
    else:
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            register_patient("Ada", "Lovelace", dob, "F")


@pytest.mark.parametrize("dob", [None, 20200101, 1.5, ["2020-01-01"], b"2020-01-01"])
def test_dob_must_be_text(dob):
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        register_patient("Ada", "Lovelace", dob, "F")


@pytest.mark.parametrize("dob", ["2023-02-29", "2020-13-01", "2020-00-10", "0000-01-01"])
def test_dob_must_be_a_real_date(dob):
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        register_patient("Ada", "Lovelace", dob, "F")


def test_dob_in_future_rejected():
    with pytest.raises(ValueError, match="future"):
        register_patient("Ada", "Lovelace", "9999-12-31", "F")


def test_rejected_patient_is_not_saved():
    with pytest.raises(ValueError):
        register_patient("Ada", "Lovelace", "20200101", "F")
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 0


@pytest.mark.parametrize("bad", [None, 5, ["Lo"]])
def test_search_rejects_non_text(bad):
    with pytest.raises(ValueError, match="must be text"):
        search_by_last_name(bad)
