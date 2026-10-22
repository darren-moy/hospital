from db import get_connection

# NOT REAL RANGES for demonstration purposes
VITALS = {
    "systolic":      ("Systolic pressure",  50, 300),
    "diastolic":     ("Diastolic pressure", 20, 200),
    "heart_rate":    ("Heart rate",         20, 300),
    "temperature_f": ("Temperature (°F)",   85, 115),
    "resp_rate":     ("Breathing rate",      4,  80),
    "spo2":          ("Oxygen saturation",  50, 100),
}

def _check_number(field, value, allow_decimal=False):
    label, low, high = VITALS[field]
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a number.")
    allowed = (int, float) if allow_decimal else (int,)
    if not isinstance(value, allowed):
        raise ValueError(f"{label} must be a {'number' if allow_decimal else 'whole number'}.")
    if not low <= value <= high:
        raise ValueError(f"{label} must be between {low} and {high}.")
    return value

def _require_open_encounter(conn, encounter_id):
    row = conn.execute(
        "SELECT status FROM encounters WHERE id = ?",
        [encounter_id],
    ).fetchone()
    if row is None:
        raise ValueError(f"No such encounter with id {encounter_id}.")
    if row["status"] != "open":
        raise ValueError("Vitals can only be recorded during an open encounter.")

def record_vitals(encounter_id, systolic=None, diastolic=None, heart_rate=None, temperature_f=None, resp_rate=None, spo2=None):
    systolic = _check_number("systolic", systolic)
    diastolic = _check_number("diastolic", diastolic)
    heart_rate = _check_number("heart_rate", heart_rate)
    temperature_f = _check_number("temperature_f", temperature_f, allow_decimal=True)
    resp_rate = _check_number("resp_rate", resp_rate)
    spo2 = _check_number("spo2", spo2)

    if (systolic is None) != (diastolic is None):
        raise ValueError("Blood pressure needs both systolic and diastolic.")
    if systolic is not None and systolic <= diastolic:
        raise ValueError("Systolic pressure must be higher than diastolic pressure.")
    if all( v is None for v in [systolic, heart_rate, temperature_f, resp_rate, spo2]):
        raise ValueError("Enter at least one vital sign.")

    with get_connection() as conn:
        _require_open_encounter(conn, encounter_id)
        cursor = conn.execute(
            "INSERT INTO vitals (encounter_id, systolic, diastolic, heart_rate, temperature_f, resp_rate, spo2) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [encounter_id, systolic, diastolic, heart_rate, temperature_f, resp_rate, spo2], 
        )
    return cursor.lastrowid

def abnormal_flags(v):
    flags = []
    if v["systolic"] is not None:
        if v["systolic"] >= 140 or v["diastolic"] >= 90:
            flags.append("High blood pressure")
        elif v["systolic"] < 90:
            flags.append("Low blood pressure")
    if v["heart_rate"] is not None:
        if v["heart_rate"] > 100:
            flags.append("High heart rate")
        elif v["heart_rate"] < 60:
            flags.append("Low heart rate")
    if v["temperature_f"] is not None:
        if v["temperature_f"] >= 100.4:
            flags.append("Fever")
        elif v["temperature_f"] < 95:
            flags.append("Low temperature")
    if v["resp_rate"] is not None and not 12 <= v["resp_rate"] <= 20:
        flags.append("Abnormal breathing rate")
    if v["spo2"] is not None and v["spo2"] < 95:
        flags.append("Low oxygen")
    return flags


def list_vitals(encounter_id):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM vitals WHERE encounter_id = ? "
            "ORDER BY recorded_at DESC, id DESC",
            [encounter_id],
        ).fetchall()
    results = []
    for row in rows:
        record = dict(row)
        record["flags"] = abnormal_flags(record)
        results.append(record)
    return results