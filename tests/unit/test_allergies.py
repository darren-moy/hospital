"""Unit tests: allergies.py."""
import pytest

from allergies import add_allergy, list_allergies, patients_without_allergies
from patients import register_patient


def test_added_allergy_is_listed(patient):
    add_allergy(patient, "Penicillin", "severe", reaction="Hives")
    [a] = list_allergies(patient)
    assert (a["substance"], a["severity"], a["reaction"]) == ("Penicillin", "severe", "Hives")
    assert a["recorded_at"]


def test_list_for_patient_with_none_is_empty(patient):
    assert list_allergies(patient) == []


def test_inputs_are_cleaned_up(patient):
    add_allergy(patient, "  Latex ", " MILD ", reaction="  Itchy  ")
    [a] = list_allergies(patient)
    assert (a["substance"], a["severity"], a["reaction"]) == ("Latex", "mild", "Itchy")


@pytest.mark.parametrize("reaction", [None, "", "   "])
def test_empty_reaction_is_stored_as_none(patient, reaction):
    add_allergy(patient, "Latex", "mild", reaction=reaction)
    assert list_allergies(patient)[0]["reaction"] is None


def test_list_is_severe_first_then_alphabetical(patient):
    add_allergy(patient, "Latex", "mild")
    add_allergy(patient, "Peanuts", "moderate")
    add_allergy(patient, "Penicillin", "severe")
    add_allergy(patient, "Aspirin", "mild")
    assert [a["substance"] for a in list_allergies(patient)] == [
        "Penicillin", "Peanuts", "Aspirin", "Latex",
    ]


@pytest.mark.parametrize("again", ["penicillin", "PENICILLIN", " Penicillin "])
def test_duplicate_substance_rejected_ignoring_case(patient, again):
    add_allergy(patient, "Penicillin", "severe")
    with pytest.raises(ValueError, match="already on this patient's allergy list"):
        add_allergy(patient, again, "mild")
    assert len(list_allergies(patient)) == 1


def test_same_substance_allowed_for_different_patients(patient):
    other = register_patient("Alan", "Turing", "1912-06-23", "M")
    add_allergy(patient, "Penicillin", "severe")
    add_allergy(other, "Penicillin", "mild")
    assert len(list_allergies(patient)) == len(list_allergies(other)) == 1


def test_lists_are_separate_per_patient(patient):
    other = register_patient("Alan", "Turing", "1912-06-23", "M")
    add_allergy(patient, "Penicillin", "severe")
    assert list_allergies(other) == []


@pytest.mark.parametrize("length,ok", [(1, True), (100, True), (101, False)])
def test_substance_length_limits(patient, length, ok):
    if ok:
        add_allergy(patient, "a" * length, "mild")
    else:
        with pytest.raises(ValueError, match="1 to 100"):
            add_allergy(patient, "a" * length, "mild")


def test_blank_substance_rejected(patient):
    with pytest.raises(ValueError, match="1 to 100"):
        add_allergy(patient, "   ", "mild")


@pytest.mark.parametrize("length,ok", [(200, True), (201, False)])
def test_reaction_length_limits(patient, length, ok):
    if ok:
        add_allergy(patient, "Latex", "mild", reaction="a" * length)
    else:
        with pytest.raises(ValueError, match="200 characters or less"):
            add_allergy(patient, "Latex", "mild", reaction="a" * length)


@pytest.mark.parametrize("severity", ["", "bad", "critical", "mild moderate"])
def test_invalid_severity_rejected(patient, severity):
    with pytest.raises(ValueError, match="Severity must be"):
        add_allergy(patient, "Latex", severity)


def test_unknown_mrn_rejected():
    with pytest.raises(ValueError, match="No patient with MRN 999999"):
        add_allergy("999999", "Latex", "mild")
    with pytest.raises(ValueError, match="No patient with MRN 999999"):
        list_allergies("999999")


def test_patients_without_allergies_lists_only_those_with_none(patient):
    other = register_patient("Alan", "Turing", "1912-06-23", "M")
    add_allergy(patient, "Latex", "mild")
    assert patients_without_allergies() == [
        {"mrn": other, "last_name": "Turing", "first_name": "Alan"},
    ]


def test_patient_with_several_allergies_is_not_listed_twice(patient):
    add_allergy(patient, "Latex", "mild")
    add_allergy(patient, "Peanuts", "moderate")
    assert patients_without_allergies() == []


def test_patients_without_allergies_is_sorted_by_name():
    register_patient("Zed", "Smith", "2000-01-01", "M")
    register_patient("Amy", "Smith", "2000-01-01", "F")
    register_patient("Bob", "Adams", "2000-01-01", "M")
    assert [(p["last_name"], p["first_name"]) for p in patients_without_allergies()] == [
        ("Adams", "Bob"), ("Smith", "Amy"), ("Smith", "Zed"),
    ]
