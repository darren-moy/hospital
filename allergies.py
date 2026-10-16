import sqlite3

from db import get_connection

VALID_SEVERITIY = {"mild", "moderate", "severe"}
MAX_SUBSTANCE_LENGTH = 100 
MAX_REACTION_LENGTH = 200 

def _get_patient_id(conn, mrn):
    row = conn.execute(
        "SELECT id FROM patients WHERE mrn = ?",
        [mrn.strip()],
    ).fetchone()
    if row is None:
        raise ValueError(f"No patient with MRN {mrn}.")
    return row["id"]

def add_allergy(mrn, substance, severity, reaction=None):
    substance = substance.strip()
    if not 1 <= len(substance) <= MAX_SUBSTANCE_LENGTH:
        raise ValueError(f"Substance must be 1 to {MAX_SUBSTANCE_LENGTH} characters.")
    
    severity = severity.strip().lower()
    if severity not in VALID_SEVERITIY:
        raise ValueError("Severity must be: mild, moderate, severe.")
    
    if reaction is not None:
        reaction = reaction.strip()
        if reaction == "":
            reaction = None
        elif len(reaction) > MAX_REACTION_LENGTH:
            raise ValueError(f"Reaction must be {MAX_REACTION_LENGTH} characters or less.")

    with get_connection() as conn:
        patient_id = _get_patient_id(conn, mrn)
        try:
            conn.execute(
                "INSERT INTO allergies (patient_id, substance, reaction, severity) "
                "VALUES (?, ?, ?, ?)",
                [patient_id, substance, reaction, severity],
            )
        except sqlite3.IntegrityError:
            raise ValueError(f"{substance} is already on this patient's allergy list.")

def list_allergies(mrn):
    with get_connection() as conn:
        patient_id = _get_patient_id(conn, mrn)
        rows = conn.execute(
            "SELECT substance, reaction, severity, recorded_at FROM allergies WHERE patient_id = ? "
            "ORDER BY CASE severity WHEN 'severe' THEN 1 WHEN 'moderate' THEN 2 ELSE 3 END, substance",[patient_id]
        ).fetchall()
    return [dict(row) for row in rows]

def patients_without_allergies():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT p.mrn, p.last_name, p.first_name FROM patients p LEFT JOIN allergies a ON a.patient_id = p.id "
            "WHERE a.id IS NULL ORDER BY p.last_name, p.first_name"
        ).fetchall()
    return [dict(row) for row in rows]