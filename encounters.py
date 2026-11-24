import sqlite3

from db import MAX_SQLITE_INT, get_connection
from patients import _clean_text, _get_patient_id

VALID_TYPES = {"outpatient", "emergency", "inpatient"}
MAX_REASON_LENGTH = 200


def start_encounter(mrn, encounter_type, reason):
    encounter_type = _clean_text(encounter_type, "Type").lower()
    if encounter_type not in VALID_TYPES:
        raise ValueError("Type must be outpatient, emergency, or inpatient.")
    reason = _clean_text(reason, "Reason")
    if not 1 <= len(reason) <= 200:
        raise ValueError(f"Reason must be 1 to {MAX_REASON_LENGTH} characters.")

    with get_connection() as conn:
        patient_id = _get_patient_id(conn, mrn)
        try:
            cursor = conn.execute(
                "INSERT INTO encounters (patient_id, encounter_type, reason) VALUES (?, ?, ?)",
                [patient_id, encounter_type, reason],
            )
        except sqlite3.IntegrityError:
            raise ValueError(
                "This patient already has an open encounter. Close it first to continue. "
            ) from None
        return cursor.lastrowid


def close_encounter(encounter_id):
    # bool is a subclass of int, so True would otherwise close encounter 1
    if (
        isinstance(encounter_id, bool)
        or not isinstance(encounter_id, int)
        or not 1 <= encounter_id <= MAX_SQLITE_INT
    ):
        raise ValueError("Encounter id must be a positive whole number.")

    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE encounters "
            "SET status = 'closed', ended_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND status = 'open'",
            [encounter_id],
        )
    if cursor.rowcount == 0:
        raise ValueError(f"No open encounter with id {encounter_id}. ")


def list_encounters(mrn):
    with get_connection() as conn:
        patient_id = _get_patient_id(conn, mrn)
        rows = conn.execute(
            "SELECT id, encounter_type, reason, status, started_at, ended_at "
            "FROM encounters "
            "WHERE patient_id = ? "
            "ORDER BY started_at DESC, id DESC",
            [patient_id],
        ).fetchall()
    return [dict(row) for row in rows]


# Everyone being seen currently
def open_encounters():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT e.id, p.mrn, p.last_name, p.first_name, "
            "e.encounter_type, e.reason, e.started_at "
            "FROM encounters e "
            "JOIN patients p ON p.id = e.patient_id "
            "WHERE e.status = 'open' "
            "ORDER BY e.started_at",
        ).fetchall()
    return [dict(row) for row in rows]
