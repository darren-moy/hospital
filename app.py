import os

from flask import Flask, abort, render_template, request

from allergies import list_allergies
from conditions import list_conditions
from encounters import list_encounters
from patients import find_patient_by_mrn, search_by_last_name

app = Flask(__name__)

@app.template_filter("utc_iso")
def utc_iso(value):
    # SQLite CURRENT_TIMESTAMP is UTC with no zone ("2026-11-09 03:12:00"); mark it as UTC for the browser
    return value.replace(" ", "T") + "Z"

@app.route("/")
def search ():
    query = request.args.get("q", "").strip()
    results = None 
    error = None 
    if query:
        try:
            results = search_by_last_name(query)
        except ValueError as exc:
            error = str(exc)
    return render_template("search.html", query = query, results = results, error = error)

@app.route("/patients/<mrn>")
def chart(mrn):
    patient = find_patient_by_mrn(mrn)
    if patient is None:
        abort(404)
    return render_template(
        "chart.html",
        patient = patient,
        allergies = list_allergies(mrn), 
        conditions = list_conditions(mrn),
        encounters = list_encounters(mrn)
    )

if __name__ == "__main__":
    # Debug mode's error page can run code, so it stays off unless FLASK_DEBUG=1 is set locally
    app.run(host="127.0.0.1", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")