"""Unit tests: Flask routes in app.py (read-only pages)."""

import pytest

from allergies import add_allergy
from app import app
from conditions import add_condition
from encounters import start_encounter
from vitals import record_vitals


@pytest.fixture
def client():
    return app.test_client()


def test_search_page_loads_with_no_query(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"No patients found" not in r.data


def test_search_finds_patient_and_links_to_chart(client, patient):
    r = client.get("/?q=love")
    assert r.status_code == 200
    assert b"Lovelace, Ada" in r.data
    assert f'href="/patients/{patient}"'.encode() in r.data


def test_search_with_no_match_says_so(client, patient):
    assert b"No patients found" in client.get("/?q=zz").data


def test_search_too_short_shows_message_not_error(client):
    r = client.get("/?q=a")
    assert r.status_code == 200
    assert b"at least 2 letters" in r.data


def test_chart_shows_patient_details(client, patient):
    r = client.get(f"/patients/{patient}")
    assert r.status_code == 200
    assert b"Lovelace, Ada" in r.data
    assert f"MRN {patient}".encode() in r.data
    assert b"1815-12-10" in r.data


def test_empty_chart_shows_empty_messages(client, patient):
    page = client.get(f"/patients/{patient}").data
    assert b"No allergies recorded." in page
    assert b"No active problems recorded." in page
    assert b"No encounters recorded." in page
    assert b"No vitals recorded." in page


def test_chart_shows_allergies_problems_and_encounters(client, patient):
    add_allergy(patient, "Penicillin", "severe", reaction="Hives")
    add_condition(patient, "E11.9", "Type 2 diabetes", onset_date="2020-01-01")
    start_encounter(patient, "outpatient", "Annual checkup")
    page = client.get(f"/patients/{patient}").data
    for text in [
        b"Penicillin",
        b"Hives",
        b"E11.9",
        b"Type 2 diabetes",
        b"2020-01-01",
        b"Annual checkup",
    ]:
        assert text in page


def test_chart_hides_resolved_conditions(client, patient):
    from conditions import resolve_condition

    resolve_condition(add_condition(patient, "J10.1", "Influenza"))
    assert b"Influenza" not in client.get(f"/patients/{patient}").data


def test_chart_shows_vitals_and_flags(client, patient, open_encounter):
    record_vitals(open_encounter, systolic=150, diastolic=95, heart_rate=72, temperature_f=98.6)
    page = client.get(f"/patients/{patient}").data
    assert b"150/95" in page
    assert b"98.6" in page
    assert b"High blood pressure" in page


def test_chart_without_vitals_says_so(client, patient, open_encounter):
    assert b"No vitals recorded." in client.get(f"/patients/{patient}").data


def test_chart_shows_dash_for_missing_vitals_not_none(client, patient, open_encounter):
    """A vital that wasn't recorded is None in Python; the page must not print that word."""
    record_vitals(open_encounter, heart_rate=72)
    page = client.get(f"/patients/{patient}").data
    assert b"None" not in page
    assert "—".encode() in page


def test_unknown_mrn_is_404(client):
    assert client.get("/patients/999999").status_code == 404


def test_web_pages_do_not_accept_writes(client, patient):
    assert client.post("/").status_code == 405
    assert client.post(f"/patients/{patient}").status_code == 405
