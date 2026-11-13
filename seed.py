"""Fill hospital.db with fictional demo patients. Safe to run more than once."""

from allergies import add_allergy
from conditions import add_condition, resolve_condition
from db import init_db
from encounters import close_encounter, start_encounter
from patients import register_patient, search_by_last_name
from vitals import record_vitals


def already_seeded(first_name, last_name, date_of_birth):
    return any(
        p["first_name"] == first_name and p["date_of_birth"] == date_of_birth
        for p in search_by_last_name(last_name)
    )


def seed_lovelace():
    mrn = register_patient("Ada", "Lovelace", "1815-12-10", "F")
    add_allergy(mrn, "Penicillin", "severe", reaction="Hives")
    add_allergy(mrn, "Latex", "mild", reaction="Itchy skin")
    add_condition(mrn, "E11.9", "Type 2 diabetes", onset_date="2019-03-14")
    add_condition(mrn, "I10", "High blood pressure", onset_date="2021-07-02")

    visit = start_encounter(mrn, "outpatient", "Annual checkup")
    record_vitals(visit, systolic=148, diastolic=94, heart_rate=76, temperature_f=98.4, resp_rate=16, spo2=98)
    close_encounter(visit)
    return mrn


def seed_turing():
    mrn = register_patient("Alan", "Turing", "1912-06-23", "M")
    add_allergy(mrn, "Peanuts", "moderate", reaction="Swelling")
    flu = add_condition(mrn, "J10.1", "Influenza", onset_date="2026-01-05")
    resolve_condition(flu, "2026-01-19")

    visit = start_encounter(mrn, "emergency", "Fever and cough")
    record_vitals(visit, systolic=118, diastolic=76, heart_rate=112, temperature_f=101.8, resp_rate=24, spo2=93)
    close_encounter(visit)

    # Left open so the chart shows a visit in progress
    visit = start_encounter(mrn, "outpatient", "Follow-up")
    record_vitals(visit, systolic=120, diastolic=78, heart_rate=68, temperature_f=98.6, resp_rate=14, spo2=99)
    return mrn


def seed_hopper():
    mrn = register_patient("Grace", "Hopper", "1906-12-09", "F")
    add_condition(mrn, "J45.909", "Asthma", onset_date="1990-05-20")
    visit = start_encounter(mrn, "inpatient", "Asthma flare")
    record_vitals(visit, heart_rate=104, resp_rate=26, spo2=91)
    close_encounter(visit)
    return mrn


def seed_curie():
    # No allergies, conditions or visits: shows the chart's empty states
    return register_patient("Marie", "Curie", "1867-11-07", "F")


DEMO_PATIENTS = [
    ("Ada", "Lovelace", "1815-12-10", seed_lovelace),
    ("Alan", "Turing", "1912-06-23", seed_turing),
    ("Grace", "Hopper", "1906-12-09", seed_hopper),
    ("Marie", "Curie", "1867-11-07", seed_curie),
]


if __name__ == "__main__":
    init_db()
    for first, last, dob, seed in DEMO_PATIENTS:
        if already_seeded(first, last, dob):
            print(f"Skipped {first} {last} (already there)")
        else:
            print(f"Added {first} {last}, MRN {seed()}")
