import re
import sqlite3
from pathlib import Path

import pytest

import db
import vitals
from vitals import VITALS, abnormal_flags, list_vitals, record_vitals

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema.sql"

VITAL_COLUMNS = ["systolic", "diastolic", "heart_rate", "temperature_f", "resp_rate", "spo2"]
INTEGER_VITALS = ["systolic", "diastolic", "heart_rate", "resp_rate", "spo2"]

# Schema values, pinned independently of vitals.VITALS.
SCHEMA_RANGES = {
    "systolic": (50, 300),
    "diastolic": (20, 200),
    "heart_rate": (20, 300),
    "temperature_f": (85, 115),
    "resp_rate": (4, 80),
    "spo2": (50, 100),
}


# ---------------------------------------------------------------- helpers

def insert_raw(**cols):
    """Insert a vitals row with raw SQL. Returns the new id."""
    names = ", ".join(cols)
    marks = ", ".join("?" for _ in cols)
    with db.get_connection() as conn:
        cur = conn.execute(f"INSERT INTO vitals ({names}) VALUES ({marks})", list(cols.values()))
    return cur.lastrowid


def fetch_row(vitals_id):
    with db.get_connection() as conn:
        row = conn.execute("SELECT * FROM vitals WHERE id = ?", [vitals_id]).fetchone()
    return dict(row) if row else None


def count_rows():
    with db.get_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM vitals").fetchone()[0]


def set_recorded_at(vitals_id, ts):
    with db.get_connection() as conn:
        conn.execute("UPDATE vitals SET recorded_at = ? WHERE id = ?", [ts, vitals_id])


def row_with(column, value):
    """Kwargs for a row where `column` = `value`, plus whatever partner is
    needed to satisfy the BP pairing and systolic > diastolic checks."""
    if column == "systolic":
        return {"systolic": value, "diastolic": 20}
    if column == "diastolic":
        return {"systolic": 250 if value < 250 else 300, "diastolic": value}
    return {column: value}


def vitals_dict(**overrides):
    v = {c: None for c in VITAL_COLUMNS}
    v.update(overrides)
    return v


def boundary_value(column, bound, delta):
    if column == "temperature_f":
        return bound + delta * 0.1
    return bound + delta


# ================================================================ SCHEMA LAYER

def test_valid_full_row_accepted(open_encounter):
    vid = insert_raw(
        encounter_id=open_encounter, systolic=120, diastolic=80, heart_rate=72,
        temperature_f=98.6, resp_rate=16, spo2=98,
    )
    row = fetch_row(vid)
    assert row["systolic"] == 120
    assert row["diastolic"] == 80
    assert row["heart_rate"] == 72
    assert row["temperature_f"] == pytest.approx(98.6)
    assert row["resp_rate"] == 16
    assert row["spo2"] == 98


def test_encounter_id_not_null_rejected():
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(heart_rate=72)


def test_recorded_at_defaults_to_current_timestamp(open_encounter):
    vid = insert_raw(encounter_id=open_encounter, heart_rate=72)
    recorded_at = fetch_row(vid)["recorded_at"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", recorded_at)
    with db.get_connection() as conn:
        now = conn.execute("SELECT CURRENT_TIMESTAMP").fetchone()[0]
    assert recorded_at[:10] == now[:10]


def test_recorded_at_explicit_null_rejected(open_encounter):
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(encounter_id=open_encounter, heart_rate=72, recorded_at=None)


@pytest.mark.parametrize("column", VITAL_COLUMNS)
@pytest.mark.parametrize("which", ["low", "high"])
def test_schema_range_boundary_accepted(open_encounter, column, which):
    low, high = SCHEMA_RANGES[column]
    value = low if which == "low" else high
    if column == "temperature_f":
        value = float(value)
    vid = insert_raw(encounter_id=open_encounter, **row_with(column, value))
    assert fetch_row(vid)[column] == value


@pytest.mark.parametrize("column", VITAL_COLUMNS)
@pytest.mark.parametrize("which", ["below_low", "above_high"])
def test_schema_range_out_of_bounds_rejected(open_encounter, column, which):
    low, high = SCHEMA_RANGES[column]
    value = boundary_value(column, low, -1) if which == "below_low" else boundary_value(column, high, 1)
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(encounter_id=open_encounter, **row_with(column, value))


# ---- STRICT typing

@pytest.mark.parametrize("column", INTEGER_VITALS)
def test_strict_integer_column_rejects_float(open_encounter, column):
    # 72.5 is in range for every INTEGER vital as far as the type check is concerned;
    # STRICT must reject it before any CHECK runs.
    value = 72.5 if column != "diastolic" else 60.5
    kwargs = row_with(column, value)
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(encounter_id=open_encounter, **kwargs)


@pytest.mark.parametrize("column", INTEGER_VITALS)
def test_strict_integer_column_rejects_text(open_encounter, column):
    kwargs = row_with(column, 60)
    kwargs[column] = "abc"
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(encounter_id=open_encounter, **kwargs)


def test_strict_real_column_rejects_text(open_encounter):
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(encounter_id=open_encounter, temperature_f="hot")


def test_strict_real_column_accepts_float(open_encounter):
    vid = insert_raw(encounter_id=open_encounter, temperature_f=98.6)
    value = fetch_row(vid)["temperature_f"]
    assert isinstance(value, float)
    assert value == pytest.approx(98.6)


def test_strict_real_column_stores_integer_as_real(open_encounter):
    vid = insert_raw(encounter_id=open_encounter, temperature_f=98)
    value = fetch_row(vid)["temperature_f"]
    assert isinstance(value, float)
    assert value == 98.0


def test_strict_encounter_id_rejects_text():
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(encounter_id="abc", heart_rate=72)


# ---- blood pressure pairing and ordering

def test_systolic_without_diastolic_rejected(open_encounter):
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(encounter_id=open_encounter, systolic=120)


def test_diastolic_without_systolic_rejected(open_encounter):
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(encounter_id=open_encounter, diastolic=80, heart_rate=72)


def test_both_bp_null_accepted(open_encounter):
    vid = insert_raw(encounter_id=open_encounter, heart_rate=72)
    row = fetch_row(vid)
    assert row["systolic"] is None and row["diastolic"] is None


@pytest.mark.parametrize("systolic, diastolic", [(100, 100), (80, 100)])
def test_systolic_not_above_diastolic_rejected(open_encounter, systolic, diastolic):
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(encounter_id=open_encounter, systolic=systolic, diastolic=diastolic)


def test_systolic_one_above_diastolic_accepted(open_encounter):
    vid = insert_raw(encounter_id=open_encounter, systolic=101, diastolic=100)
    assert fetch_row(vid)["systolic"] == 101


# ---- at least one vital

def test_row_with_no_vitals_rejected(open_encounter):
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(encounter_id=open_encounter)


@pytest.mark.parametrize("kwargs", [
    {"systolic": 120, "diastolic": 80},
    {"heart_rate": 72},
    {"temperature_f": 98.6},
    {"resp_rate": 16},
    {"spo2": 98},
], ids=["bp", "heart_rate", "temperature_f", "resp_rate", "spo2"])
def test_row_with_single_vital_accepted(open_encounter, kwargs):
    vid = insert_raw(encounter_id=open_encounter, **kwargs)
    assert fetch_row(vid) is not None


# ---- foreign key

def test_nonexistent_encounter_fk_rejected():
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(encounter_id=9999, heart_rate=72)


def test_schema_allows_vitals_on_closed_encounter(closed_encounter):
    # The open-encounter rule lives only in Python; the schema permits it.
    vid = insert_raw(encounter_id=closed_encounter, heart_rate=72)
    assert fetch_row(vid)["encounter_id"] == closed_encounter


def test_delete_encounter_with_vitals_restricted(open_encounter):
    insert_raw(encounter_id=open_encounter, heart_rate=72)
    with pytest.raises(sqlite3.IntegrityError):
        with db.get_connection() as conn:
            conn.execute("DELETE FROM encounters WHERE id = ?", [open_encounter])


def test_delete_encounter_without_vitals_allowed(open_encounter):
    with db.get_connection() as conn:
        conn.execute("DELETE FROM encounters WHERE id = ?", [open_encounter])
        remaining = conn.execute("SELECT COUNT(*) FROM encounters").fetchone()[0]
    assert remaining == 0


def test_delete_vitals_then_encounter_allowed(open_encounter):
    vid = insert_raw(encounter_id=open_encounter, heart_rate=72)
    with db.get_connection() as conn:
        conn.execute("DELETE FROM vitals WHERE id = ?", [vid])
        conn.execute("DELETE FROM encounters WHERE id = ?", [open_encounter])


# ================================================================ DRIFT CHECKS

def _schema_vitals_checks():
    sql = SCHEMA_PATH.read_text()
    block = re.search(r"CREATE TABLE IF NOT EXISTS vitals\s*\((.*?)\)\s*STRICT;", sql, re.S).group(1)
    return {
        col: (int(lo), int(hi))
        for col, lo, hi in re.findall(r"CHECK\s*\(\s*(\w+)\s+BETWEEN\s+(\d+)\s+AND\s+(\d+)\s*\)", block)
    }


def test_schema_ranges_match_pinned_values():
    assert _schema_vitals_checks() == SCHEMA_RANGES


@pytest.mark.parametrize("column", VITAL_COLUMNS)
def test_python_range_matches_schema_check(column):
    _, low, high = VITALS[column]
    assert (low, high) == _schema_vitals_checks()[column]


def test_every_vitals_key_is_a_real_column():
    with db.get_connection() as conn:
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(vitals)")}
    assert set(VITALS) <= columns


def test_every_vital_column_has_python_range():
    with db.get_connection() as conn:
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(vitals)")}
    assert columns - {"id", "encounter_id", "recorded_at"} == set(VITALS)


def test_decimal_policy_matches_column_types():
    with db.get_connection() as conn:
        types = {r["name"]: r["type"] for r in conn.execute("PRAGMA table_info(vitals)")}
    for column in VITALS:
        if types[column] == "REAL":
            assert vitals._check_number(column, float(VITALS[column][1]) + 0.5, allow_decimal=True)
        else:
            assert types[column] == "INTEGER"
            assert column in INTEGER_VITALS


# ================================================================ API: record_vitals

def test_record_vitals_full_returns_id_and_stores_row(open_encounter):
    vid = record_vitals(open_encounter, systolic=120, diastolic=80, heart_rate=72,
                        temperature_f=98.6, resp_rate=16, spo2=98)
    assert isinstance(vid, int)
    row = fetch_row(vid)
    assert row["encounter_id"] == open_encounter
    assert (row["systolic"], row["diastolic"], row["heart_rate"], row["resp_rate"], row["spo2"]) == (120, 80, 72, 16, 98)
    assert row["temperature_f"] == pytest.approx(98.6)
    assert row["recorded_at"]


@pytest.mark.parametrize("kwargs", [
    {"systolic": 120, "diastolic": 80},
    {"heart_rate": 72},
    {"temperature_f": 98.6},
    {"resp_rate": 16},
    {"spo2": 98},
], ids=["bp", "heart_rate", "temperature_f", "resp_rate", "spo2"])
def test_record_vitals_single_vital_leaves_others_null(open_encounter, kwargs):
    vid = record_vitals(open_encounter, **kwargs)
    row = fetch_row(vid)
    for column in VITAL_COLUMNS:
        if column in kwargs:
            assert row[column] == pytest.approx(kwargs[column])
        else:
            assert row[column] is None


def test_record_vitals_temperature_decimal_accepted(open_encounter):
    vid = record_vitals(open_encounter, temperature_f=99.9)
    assert fetch_row(vid)["temperature_f"] == pytest.approx(99.9)


def test_record_vitals_temperature_integer_accepted(open_encounter):
    vid = record_vitals(open_encounter, temperature_f=98)
    value = fetch_row(vid)["temperature_f"]
    assert value == 98.0
    assert isinstance(value, float)


@pytest.mark.parametrize("column", VITAL_COLUMNS)
@pytest.mark.parametrize("which", ["low", "high"])
def test_record_vitals_range_boundary_accepted(open_encounter, column, which):
    low, high = SCHEMA_RANGES[column]
    value = low if which == "low" else high
    vid = record_vitals(open_encounter, **row_with(column, value))
    assert fetch_row(vid)[column] == value


@pytest.mark.parametrize("column", VITAL_COLUMNS)
@pytest.mark.parametrize("which", ["below_low", "above_high"])
def test_record_vitals_out_of_range_rejected_with_label(open_encounter, column, which):
    label, low, high = VITALS[column]
    s_low, s_high = SCHEMA_RANGES[column]
    value = boundary_value(column, s_low, -1) if which == "below_low" else boundary_value(column, s_high, 1)
    with pytest.raises(ValueError) as exc:
        record_vitals(open_encounter, **row_with(column, value))
    assert str(exc.value) == f"{label} must be between {low} and {high}."
    assert count_rows() == 0


@pytest.mark.parametrize("column", VITAL_COLUMNS)
def test_record_vitals_bool_rejected(open_encounter, column):
    label = VITALS[column][0]
    kwargs = row_with(column, 60)
    kwargs[column] = True
    with pytest.raises(ValueError) as exc:
        record_vitals(open_encounter, **kwargs)
    assert str(exc.value) == f"{label} must be a number."
    assert count_rows() == 0


@pytest.mark.parametrize("column", INTEGER_VITALS)
def test_record_vitals_string_rejected_for_integer_vital(open_encounter, column):
    label = VITALS[column][0]
    kwargs = row_with(column, 60)
    kwargs[column] = "72"
    with pytest.raises(ValueError) as exc:
        record_vitals(open_encounter, **kwargs)
    assert str(exc.value) == f"{label} must be a whole number."


def test_record_vitals_string_rejected_for_temperature(open_encounter):
    with pytest.raises(ValueError) as exc:
        record_vitals(open_encounter, temperature_f="98.6")
    assert str(exc.value) == "Temperature (°F) must be a number."


@pytest.mark.parametrize("column", INTEGER_VITALS)
@pytest.mark.parametrize("value", [72.5, 72.0], ids=["fractional", "integral_float"])
def test_record_vitals_decimal_rejected_for_integer_vital(open_encounter, column, value):
    label = VITALS[column][0]
    kwargs = row_with(column, 60)
    kwargs[column] = value
    with pytest.raises(ValueError) as exc:
        record_vitals(open_encounter, **kwargs)
    assert str(exc.value) == f"{label} must be a whole number."


def test_record_vitals_heart_rate_decimal_message():
    with pytest.raises(ValueError, match=r"^Heart rate must be a whole number\.$"):
        record_vitals(1, heart_rate=72.5)


def test_record_vitals_spo2_range_message():
    with pytest.raises(ValueError, match=r"^Oxygen saturation must be between 50 and 100\.$"):
        record_vitals(1, spo2=101)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_record_vitals_nonfinite_temperature_rejected(open_encounter, value):
    with pytest.raises(ValueError, match="Temperature"):
        record_vitals(open_encounter, temperature_f=value)


def test_record_vitals_no_vitals_rejected(open_encounter):
    with pytest.raises(ValueError, match=r"^Enter at least one vital sign\.$"):
        record_vitals(open_encounter)


@pytest.mark.parametrize("kwargs", [
    {"systolic": 120},
    {"diastolic": 80},
    {"systolic": 120, "heart_rate": 72},
    {"diastolic": 80, "heart_rate": 72},
])
def test_record_vitals_unpaired_bp_rejected(open_encounter, kwargs):
    with pytest.raises(ValueError, match=r"^Blood pressure needs both systolic and diastolic\.$"):
        record_vitals(open_encounter, **kwargs)
    assert count_rows() == 0


@pytest.mark.parametrize("systolic, diastolic", [(100, 100), (80, 100)])
def test_record_vitals_systolic_not_above_diastolic_rejected(open_encounter, systolic, diastolic):
    with pytest.raises(ValueError, match=r"^Systolic pressure must be higher than diastolic pressure\.$"):
        record_vitals(open_encounter, systolic=systolic, diastolic=diastolic)
    assert count_rows() == 0


def test_record_vitals_systolic_one_above_diastolic_accepted(open_encounter):
    vid = record_vitals(open_encounter, systolic=101, diastolic=100)
    assert fetch_row(vid)["systolic"] == 101


def test_record_vitals_closed_encounter_rejected(closed_encounter):
    with pytest.raises(ValueError, match=r"^Vitals can only be recorded during an open encounter\.$"):
        record_vitals(closed_encounter, heart_rate=72)
    assert count_rows() == 0


def test_record_vitals_nonexistent_encounter_rejected():
    with pytest.raises(ValueError, match=r"^No such encounter with id 9999\.$"):
        record_vitals(9999, heart_rate=72)
    assert count_rows() == 0


def test_record_vitals_validates_values_before_encounter_lookup():
    # Value errors are reported even when the encounter doesn't exist.
    with pytest.raises(ValueError, match="Heart rate must be between"):
        record_vitals(9999, heart_rate=400)


def test_record_vitals_never_raises_integrity_error(open_encounter):
    for kwargs in [{}, {"systolic": 120}, {"systolic": 80, "diastolic": 90}, {"spo2": 101}]:
        with pytest.raises(ValueError):
            record_vitals(open_encounter, **kwargs)


def test_record_vitals_multiple_rows_same_encounter(open_encounter):
    a = record_vitals(open_encounter, heart_rate=70)
    b = record_vitals(open_encounter, heart_rate=80)
    assert a != b
    assert count_rows() == 2


# ================================================================ API: abnormal_flags

@pytest.mark.parametrize("systolic, diastolic, expected", [
    (139, 89, []),
    (140, 80, ["High blood pressure"]),
    (120, 90, ["High blood pressure"]),
    (120, 89, []),
    (90, 60, []),
    (89, 60, ["Low blood pressure"]),
])
def test_abnormal_flags_blood_pressure_thresholds(systolic, diastolic, expected):
    assert abnormal_flags(vitals_dict(systolic=systolic, diastolic=diastolic)) == expected


@pytest.mark.parametrize("hr, expected", [
    (59, ["Low heart rate"]),
    (60, []),
    (100, []),
    (101, ["High heart rate"]),
])
def test_abnormal_flags_heart_rate_thresholds(hr, expected):
    assert abnormal_flags(vitals_dict(heart_rate=hr)) == expected


@pytest.mark.parametrize("temp, expected", [
    (94.9, ["Low temperature"]),
    (95, []),
    (95.0, []),
    (100.3, []),
    (100.4, ["Fever"]),
])
def test_abnormal_flags_temperature_thresholds(temp, expected):
    assert abnormal_flags(vitals_dict(temperature_f=temp)) == expected


@pytest.mark.parametrize("rr, expected", [
    (11, ["Abnormal breathing rate"]),
    (12, []),
    (20, []),
    (21, ["Abnormal breathing rate"]),
])
def test_abnormal_flags_resp_rate_thresholds(rr, expected):
    assert abnormal_flags(vitals_dict(resp_rate=rr)) == expected


@pytest.mark.parametrize("spo2, expected", [
    (94, ["Low oxygen"]),
    (95, []),
    (100, []),
])
def test_abnormal_flags_spo2_thresholds(spo2, expected):
    assert abnormal_flags(vitals_dict(spo2=spo2)) == expected


def test_abnormal_flags_all_none_empty():
    assert abnormal_flags(vitals_dict()) == []


def test_abnormal_flags_multiple_in_order():
    v = vitals_dict(systolic=160, diastolic=100, heart_rate=120, temperature_f=101.0, resp_rate=25, spo2=90)
    assert abnormal_flags(v) == [
        "High blood pressure", "High heart rate", "Fever", "Abnormal breathing rate", "Low oxygen",
    ]


def test_abnormal_flags_normal_values_empty():
    v = vitals_dict(systolic=120, diastolic=80, heart_rate=72, temperature_f=98.6, resp_rate=16, spo2=98)
    assert abnormal_flags(v) == []


# ================================================================ API: list_vitals

def test_list_vitals_unknown_encounter_empty():
    assert list_vitals(9999) == []


def test_list_vitals_encounter_without_vitals_empty(open_encounter):
    assert list_vitals(open_encounter) == []


def test_list_vitals_returns_dicts_with_all_columns_and_flags(open_encounter):
    vid = record_vitals(open_encounter, systolic=120, diastolic=80, heart_rate=72,
                        temperature_f=98.6, resp_rate=16, spo2=98)
    [record] = list_vitals(open_encounter)
    assert type(record) is dict
    assert set(record) == {"id", "encounter_id", *VITAL_COLUMNS, "recorded_at", "flags"}
    assert record["id"] == vid
    assert record["flags"] == []


def test_list_vitals_attaches_flags(open_encounter):
    record_vitals(open_encounter, heart_rate=120, spo2=90)
    [record] = list_vitals(open_encounter)
    assert record["flags"] == ["High heart rate", "Low oxygen"]


def test_list_vitals_newest_first(open_encounter):
    old = record_vitals(open_encounter, heart_rate=70)
    new = record_vitals(open_encounter, heart_rate=80)
    mid = record_vitals(open_encounter, heart_rate=75)
    set_recorded_at(old, "2026-01-01 08:00:00")
    set_recorded_at(mid, "2026-01-01 09:00:00")
    set_recorded_at(new, "2026-01-01 10:00:00")
    assert [r["id"] for r in list_vitals(open_encounter)] == [new, mid, old]


def test_list_vitals_same_timestamp_id_desc_tiebreak(open_encounter):
    ids = [record_vitals(open_encounter, heart_rate=70 + i) for i in range(3)]
    for vid in ids:
        set_recorded_at(vid, "2026-01-01 08:00:00")
    assert [r["id"] for r in list_vitals(open_encounter)] == sorted(ids, reverse=True)


def test_list_vitals_only_returns_requested_encounter(patient, open_encounter):
    from encounters import start_encounter
    from patients import register_patient

    other_mrn = register_patient("Grace", "Hopper", "1906-12-09", "F")
    other = start_encounter(other_mrn, "emergency", "Fall")
    mine = record_vitals(open_encounter, heart_rate=70)
    record_vitals(other, heart_rate=80)
    assert [r["id"] for r in list_vitals(open_encounter)] == [mine]


def test_list_vitals_includes_closed_encounter_history(open_encounter):
    from encounters import close_encounter

    vid = record_vitals(open_encounter, heart_rate=70)
    close_encounter(open_encounter)
    assert [r["id"] for r in list_vitals(open_encounter)] == [vid]
