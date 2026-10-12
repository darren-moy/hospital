from datetime import date
from db import get_connection

VALID_SEX = {"F", "M", "O", "U"}
MAX_NAME_LENGTH = 50 
FIRST_MRN = 100001

def _clean_name(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text.")
    value = value.strip()
    if not 1 <= len(value) <= MAX_NAME_LENGTH:
        raise ValueError(f"{field} must be 1 to {MAX_NAME_LENGTH} characters.")
    return  value 

def _clean_dob(value):
    try: 
        dob = date.fromisoformat(value.strip())
    except:
        raise ValueError("Date of birth must be a real date in YYYY-MM-DD format.")
    if dob > date.today():
        raise ValueError("Date of birth cannot be in the future.")
    return dob.isoformat()

def _clean_sex(value):
    if not isinstance(value, str) or value.strip().upper() not in VALID_SEX:
        raise ValueError("Sex must be F, M, O, U.")
    return value.strip().upper()

# MRN Generator 
# Query for a row, if no row then start at 100001, otherwise one more than highest stored as a text 
def _next_mrn(conn):
    row = conn.execute(
        "SELECT MAX(CAST(mrn AS INTEGER)) AS last FROM patients"
    ).fetchone()
    if row["last"] is None:
        return str(FIRST_MRN)
    return str(row["last"] + 1 )

# PUBLIC FUNCS
def register_patient(first_name, last_name, date_of_birth, sex):
    first_name = _clean_name(first_name, "First name")
    last_name = _clean_name(last_name, "Last name")
    date_of_birth = _clean_dob(date_of_birth)
    sex = _clean_sex(sex)

    with get_connection() as conn:
        mrn = _next_mrn(conn)
        conn.execute(
            "INSERT INTO patients (mrn, first_name, last_name, date_of_birth, sex)"
            "VALUES (?, ?, ?, ?, ?)"
            [mrn, first_name, last_name, date_of_birth, sex],
        )
    return mrn 

def find_patient_by_mrn(mrn):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM patients WHERE mrn = ?",
            [mrn.strip()],
        ).fetchone()
    return dict(row) if row else None

def search_by_last_name(text):
    text = text.strip()
    if len(text) < 2:
        raise ValueError("Type at least 2 letters to search.")
    pattern = (
        text.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        + "%"
    )

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM patients"
            "WHERE last_name LIKE ? ESCAPE '\\' "
            "ORDER BY last_name, first_name",
            [pattern],
        ).fetchall()
    return [dict(row) for row in rows]