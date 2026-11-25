"""Unit tests: encounters.py."""

import pytest

from hospital.domain.encounters import (
    close_encounter,
    list_encounters,
    open_encounters,
    start_encounter,
)
from hospital.domain.patients import register_patient


def test_start_returns_id_and_encounter_is_open(patient):
    encounter_id = start_encounter(patient, "outpatient", "Checkup")
    [e] = list_encounters(patient)
    assert e["id"] == encounter_id
    assert (e["encounter_type"], e["reason"], e["status"]) == ("outpatient", "Checkup", "open")
    assert e["started_at"] and e["ended_at"] is None


def test_inputs_are_cleaned_up(patient):
    start_encounter(patient, "  EMERGENCY ", "  Fall  ")
    [e] = list_encounters(patient)
    assert (e["encounter_type"], e["reason"]) == ("emergency", "Fall")


@pytest.mark.parametrize("kind", ["outpatient", "inpatient", "emergency"])
def test_each_valid_type_is_accepted(patient, kind):
    assert start_encounter(patient, kind, "Reason")


@pytest.mark.parametrize("kind", ["", "visit", "out patient"])
def test_invalid_type_rejected(patient, kind):
    with pytest.raises(ValueError, match="Type must be"):
        start_encounter(patient, kind, "Reason")


@pytest.mark.parametrize("length,ok", [(1, True), (200, True), (201, False), (0, False)])
def test_reason_length_limits(patient, length, ok):
    if ok:
        assert start_encounter(patient, "outpatient", "a" * length)
    else:
        with pytest.raises(ValueError, match="1 to 200"):
            start_encounter(patient, "outpatient", "a" * length)


def test_blank_reason_rejected(patient):
    with pytest.raises(ValueError, match="1 to 200"):
        start_encounter(patient, "outpatient", "   ")


def test_second_open_encounter_rejected(patient, open_encounter):
    with pytest.raises(ValueError, match="already has an open encounter"):
        start_encounter(patient, "emergency", "Fall")
    assert len(list_encounters(patient)) == 1


def test_different_patients_can_each_have_an_open_encounter(patient, open_encounter):
    other = register_patient("Alan", "Turing", "1912-06-23", "M")
    assert start_encounter(other, "outpatient", "Checkup")


def test_new_encounter_allowed_after_closing(patient, closed_encounter):
    assert start_encounter(patient, "emergency", "Fall") != closed_encounter


def test_close_sets_status_and_end_time(patient, open_encounter):
    close_encounter(open_encounter)
    [e] = list_encounters(patient)
    assert e["status"] == "closed" and e["ended_at"]


def test_closing_twice_rejected(closed_encounter):
    with pytest.raises(ValueError, match="No open encounter"):
        close_encounter(closed_encounter)


def test_closing_unknown_id_rejected():
    with pytest.raises(ValueError, match="No open encounter with id 999"):
        close_encounter(999)


@pytest.mark.parametrize("bad", [0, -1, "1", None, 1.0, [1]])
def test_close_rejects_invalid_ids(bad):
    with pytest.raises(ValueError, match="positive whole number"):
        close_encounter(bad)


def test_list_is_newest_first(patient):
    first = start_encounter(patient, "outpatient", "One")
    close_encounter(first)
    second = start_encounter(patient, "outpatient", "Two")
    close_encounter(second)
    third = start_encounter(patient, "outpatient", "Three")
    assert [e["id"] for e in list_encounters(patient)] == [third, second, first]


def test_list_for_patient_with_none_is_empty(patient):
    assert list_encounters(patient) == []


def test_lists_are_separate_per_patient(patient, open_encounter):
    other = register_patient("Alan", "Turing", "1912-06-23", "M")
    assert list_encounters(other) == []


def test_unknown_mrn_rejected():
    with pytest.raises(ValueError, match="No patient with MRN 999999"):
        start_encounter("999999", "outpatient", "Checkup")
    with pytest.raises(ValueError, match="No patient with MRN 999999"):
        list_encounters("999999")


def test_open_encounters_shows_only_open_ones_with_patient_names(patient, open_encounter):
    other = register_patient("Alan", "Turing", "1912-06-23", "M")
    done = start_encounter(other, "outpatient", "Checkup")
    close_encounter(done)
    [row] = open_encounters()
    assert (row["id"], row["mrn"], row["last_name"], row["first_name"]) == (
        open_encounter,
        patient,
        "Lovelace",
        "Ada",
    )


def test_open_encounters_empty_when_none_open(closed_encounter):
    assert open_encounters() == []
