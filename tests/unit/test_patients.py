"""Unit tests: patients.py behaves as documented for normal and edge-case input."""
import pytest

from patients import find_patient_by_mrn, register_patient, search_by_last_name


def test_first_mrn_is_100001():
    assert register_patient("Ada", "Lovelace", "1815-12-10", "F") == "100001"


def test_mrns_count_up():
    first = register_patient("Ada", "Lovelace", "1815-12-10", "F")
    second = register_patient("Alan", "Turing", "1912-06-23", "M")
    assert (first, second) == ("100001", "100002")


def test_registered_patient_is_stored_cleaned_up():
    mrn = register_patient("  Ada ", " Lovelace  ", " 1815-12-10 ", " f ")
    p = find_patient_by_mrn(mrn)
    assert (p["first_name"], p["last_name"], p["date_of_birth"], p["sex"]) == (
        "Ada", "Lovelace", "1815-12-10", "F",
    )


def test_find_returns_plain_dict(patient):
    assert type(find_patient_by_mrn(patient)) is dict


@pytest.mark.parametrize("length,ok", [(1, True), (50, True), (51, False)])
def test_name_length_limits(length, ok):
    name = "a" * length
    if ok:
        assert register_patient(name, name, "2000-01-01", "U")
    else:
        with pytest.raises(ValueError, match="1 to 50"):
            register_patient(name, "Lovelace", "2000-01-01", "U")
        with pytest.raises(ValueError, match="1 to 50"):
            register_patient("Ada", name, "2000-01-01", "U")


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_names_rejected(blank):
    with pytest.raises(ValueError, match="First name"):
        register_patient(blank, "Lovelace", "2000-01-01", "F")
    with pytest.raises(ValueError, match="Last name"):
        register_patient("Ada", blank, "2000-01-01", "F")


@pytest.mark.parametrize("bad", [None, 5, ["Ada"]])
def test_non_text_names_rejected(bad):
    with pytest.raises(ValueError, match="must be text"):
        register_patient(bad, "Lovelace", "2000-01-01", "F")


@pytest.mark.parametrize("sex", ["F", "M", "O", "U", "m", " o "])
def test_valid_sex_values(sex):
    assert register_patient("Ada", "Lovelace", "2000-01-01", sex)


@pytest.mark.parametrize("sex", ["", "X", "Female", None, 1])
def test_invalid_sex_values(sex):
    with pytest.raises(ValueError, match="Sex must be"):
        register_patient("Ada", "Lovelace", "2000-01-01", sex)


def test_today_is_a_valid_birth_date():
    from datetime import date

    assert register_patient("Ada", "Lovelace", date.today().isoformat(), "F")


def test_search_matches_start_of_last_name_ignoring_case(patient):
    assert [p["mrn"] for p in search_by_last_name("love")] == [patient]
    assert search_by_last_name("ace") == []   # prefix only, not "contains"


def test_search_sorts_by_last_then_first_name():
    register_patient("Zed", "Smith", "2000-01-01", "M")
    register_patient("Amy", "Smith", "2000-01-01", "F")
    register_patient("Bob", "Smyth", "2000-01-01", "M")
    names = [(p["last_name"], p["first_name"]) for p in search_by_last_name("sm")]
    assert names == [("Smith", "Amy"), ("Smith", "Zed"), ("Smyth", "Bob")]


def test_search_with_no_matches_returns_empty_list(patient):
    assert search_by_last_name("zz") == []


@pytest.mark.parametrize("short", ["", " ", "a", " a "])
def test_search_needs_two_letters(short):
    with pytest.raises(ValueError, match="at least 2"):
        search_by_last_name(short)
