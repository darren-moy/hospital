"""Unit tests: vitals.abnormal_flags thresholds, tested without a database."""
import pytest

from vitals import abnormal_flags

NORMAL = {
    "systolic": 120, "diastolic": 80, "heart_rate": 72,
    "temperature_f": 98.6, "resp_rate": 16, "spo2": 98,
}


def flags(**changes):
    return abnormal_flags({**NORMAL, **changes})


def test_normal_vitals_have_no_flags():
    assert flags() == []


def test_missing_values_are_skipped():
    assert abnormal_flags({k: None for k in NORMAL}) == []


@pytest.mark.parametrize("changes,expected", [
    ({"systolic": 139, "diastolic": 89}, []),
    ({"systolic": 140}, ["High blood pressure"]),
    ({"diastolic": 90}, ["High blood pressure"]),
    ({"systolic": 90, "diastolic": 60}, []),
    ({"systolic": 89, "diastolic": 60}, ["Low blood pressure"]),
    ({"heart_rate": 100}, []),
    ({"heart_rate": 101}, ["High heart rate"]),
    ({"heart_rate": 60}, []),
    ({"heart_rate": 59}, ["Low heart rate"]),
    ({"temperature_f": 100.3}, []),
    ({"temperature_f": 100.4}, ["Fever"]),
    ({"temperature_f": 95.0}, []),
    ({"temperature_f": 94.9}, ["Low temperature"]),
    ({"resp_rate": 12}, []),
    ({"resp_rate": 20}, []),
    ({"resp_rate": 11}, ["Abnormal breathing rate"]),
    ({"resp_rate": 21}, ["Abnormal breathing rate"]),
    ({"spo2": 95}, []),
    ({"spo2": 94}, ["Low oxygen"]),
], ids=str)
def test_threshold_boundaries(changes, expected):
    assert flags(**changes) == expected


def test_several_flags_at_once():
    assert flags(systolic=150, diastolic=95, heart_rate=110, temperature_f=101, spo2=90) == [
        "High blood pressure", "High heart rate", "Fever", "Low oxygen",
    ]
