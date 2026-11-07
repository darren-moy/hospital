import re
import sqlite3
from datetime import date

from db import get_connection
from patients import _get_patient_id

ICD10_PATTERN = re.compile(r"[A-Z][0-9][0-9A-Z](\.[0-9A-Z]{1,4})?")
MAX_DESCRIPTION_LENGTH = 200


def _clean_code(code):
    if not isinstance(code, str):
        raise ValueError("ICD-10 code must be text.")
    code = code.strip().upper()
    if not ICD10_PATTERN.fullmatch(code):
        raise ValueError("ICD-10 code must look like E11.9 or I10.")
    return code


def _clean_description(text):
    if not isinstance(text, str):
        raise ValueError("Description must be text.")
    text = text.strip()
    if not 1 <= len(text) <= MAX_DESCRIPTION_LENGTH:
        raise ValueError(f"Description must be 1 to {MAX_DESCRIPTION_LENGTH} characters.")
    return text


def _clean_date(value, field):
    if value is None:
        return None
    try:
        parsed = date.fromisoformat(value.strip())
    except (ValueError, AttributeError):
        raise ValueError(f"{field} must be a real date in YYYY-MM-DD format.")
    if parsed > date.today():
        raise ValueError(f"{field} can't be in the future.")
    return parsed.isoformat()


def add_condition(mrn, icd10_code, description, onset_date=None):
    icd10_code = _clean_code(icd10_code)
    description = _clean_description(description)
    onset_date = _clean_date(onset_date, "Onset date")

    with get_connection() as conn:
        patient_id = _get_patient_id(conn, mrn)
        try:
            cursor = conn.execute(
                "INSERT INTO conditions (patient_id, icd10_code, description, onset_date) "
                "VALUES (?, ?, ?, ?)",
                [patient_id, icd10_code, description, onset_date],
            )
        except sqlite3.IntegrityError:
            raise ValueError(f"{icd10_code} is already an active problem for this patient.")
        return cursor.lastrowid


def resolve_condition(condition_id, resolved_date=None):
    if isinstance(condition_id, bool) or not isinstance(condition_id, int) or condition_id < 1:
        raise ValueError("Condition id must be a positive whole number.")
    resolved_date = _clean_date(resolved_date, "Resolved date") or date.today().isoformat()

    with get_connection() as conn:
        try:
            cursor = conn.execute(
                "UPDATE conditions SET status = 'resolved', resolved_date = ? "
                "WHERE id = ? AND status = 'active'",
                [resolved_date, condition_id],
            )
        except sqlite3.IntegrityError:
            raise ValueError("Resolved date can't be before the onset date.")
        if cursor.rowcount == 0:
            raise ValueError(f"No active condition with id {condition_id}.")


def list_conditions(mrn, include_resolved=False):
    sql = (
        "SELECT id, icd10_code, description, status, onset_date, resolved_date "
        "FROM conditions WHERE patient_id = ? "
    )
    if not include_resolved:
        sql += "AND status = 'active' "
    sql += "ORDER BY status, onset_date DESC, icd10_code"

    with get_connection() as conn:
        patient_id = _get_patient_id(conn, mrn)
        rows = conn.execute(sql, [patient_id]).fetchall()
    return [dict(row) for row in rows]