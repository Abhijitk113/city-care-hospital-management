
import os
import re
import json
import math
import sqlite3
from datetime import date, datetime
from flask import Flask, render_template, request, redirect, session


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key-before-hosting"
)

DATABASE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "hospital.db"
)


# =========================================================
# DATABASE
# =========================================================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # PATIENTS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            age INTEGER NOT NULL,
            gender TEXT NOT NULL,
            phone TEXT NOT NULL,
            disease TEXT NOT NULL,
            address TEXT DEFAULT ''
        )
    """)

    patient_columns = [
        column["name"]
        for column in cursor.execute(
            "PRAGMA table_info(patients)"
        ).fetchall()
    ]

    if "address" not in patient_columns:
        cursor.execute("""
            ALTER TABLE patients
            ADD COLUMN address TEXT DEFAULT ''
        """)

    # DOCTORS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS doctors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            specialization TEXT NOT NULL,
            phone TEXT NOT NULL,
            status TEXT DEFAULT 'Active'
        )
    """)

    doctor_columns = [
        column["name"]
        for column in cursor.execute(
            "PRAGMA table_info(doctors)"
        ).fetchall()
    ]

    if "specialization" not in doctor_columns:
        cursor.execute("""
            ALTER TABLE doctors
            ADD COLUMN specialization TEXT
        """)

    if "status" not in doctor_columns:
        cursor.execute("""
            ALTER TABLE doctors
            ADD COLUMN status TEXT DEFAULT 'Active'
        """)

    # APPOINTMENTS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient TEXT NOT NULL,
            doctor TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            status TEXT DEFAULT 'Scheduled'
        )
    """)

    appointment_columns = [
        column["name"]
        for column in cursor.execute(
            "PRAGMA table_info(appointments)"
        ).fetchall()
    ]

    if "doctor_id" not in appointment_columns:
        cursor.execute("""
            ALTER TABLE appointments
            ADD COLUMN doctor_id INTEGER
        """)

    # BILLS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient TEXT NOT NULL,
            consultation_fee REAL DEFAULT 0,
            medicine_charges REAL DEFAULT 0,
            other_charges REAL DEFAULT 0,
            total REAL DEFAULT 0,
            status TEXT DEFAULT 'Pending'
        )
    """)

    bill_columns = [
        column["name"]
        for column in cursor.execute(
            "PRAGMA table_info(bills)"
        ).fetchall()
    ]

    if "issue_date" not in bill_columns:
        cursor.execute("""
            ALTER TABLE bills
            ADD COLUMN issue_date TEXT
        """)

    # Assign today's date to older bills without an issue date.
    cursor.execute("""
        UPDATE bills
        SET issue_date = ?
        WHERE issue_date IS NULL OR issue_date = ''
    """, (date.today().isoformat(),))

    conn.commit()
    conn.close()


# =========================================================
# VALIDATION HELPERS
# =========================================================

def valid_name(value):
    """Allow letters, spaces, periods, apostrophes and hyphens."""
    value = value.strip()

    if not value:
        return False

    return re.fullmatch(
        r"[^\W\d_][^\W\d_ .'-]*",
        value,
        flags=re.UNICODE
    ) is not None


def valid_phone(value):
    """Require exactly 10 digits."""
    return re.fullmatch(r"[0-9]{10}", value.strip()) is not None


def valid_date(value):
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


def valid_time(value):
    try:
        datetime.strptime(value, "%H:%M")
        return True
    except (ValueError, TypeError):
        return False


def valid_future_date(value):
    return valid_date(value) and value >= date.today().isoformat()


def form_error(message):
    """Show a simple validation alert and return to the previous page."""
    return (
        f"<script>alert({json.dumps(message)});"
        "history.back();</script>",
        400
    )


def parse_charge(field_name):
    raw_value = request.form.get(field_name, "0").strip()

    if not raw_value:
        raw_value = "0"

    try:
        amount = float(raw_value)
    except (ValueError, TypeError):
        raise ValueError("Please enter valid bill amounts.")

    if not math.isfinite(amount) or amount < 0:
        raise ValueError("Bill amounts cannot be negative or invalid.")

    return round(amount, 2)


# =========================================================
# LOGIN
# =========================================================

@app.route("/")
def home():
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    # Demo credentials for the college project.
    if username == "admin" and password == "admin123":
        session["user"] = username
        return redirect("/dashboard")

    return "Invalid username or password", 401


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")

    conn = get_db()

    patients = conn.execute(
        "SELECT COUNT(*) FROM patients"
    ).fetchone()[0]

    doctors = conn.execute(
        "SELECT COUNT(*) FROM doctors"
    ).fetchone()[0]

    appointments = conn.execute(
        "SELECT COUNT(*) FROM appointments"
    ).fetchone()[0]

    bills = conn.execute("""
        SELECT COALESCE(SUM(total), 0)
        FROM bills
    """).fetchone()[0]

    conn.close()

    return render_template(
        "dashboard.html",
        patients=patients,
        doctors=doctors,
        appointments=appointments,
        bills=bills
    )


# =========================================================
# PATIENTS
# =========================================================

@app.route("/patients")
def patients():
    if "user" not in session:
        return redirect("/")

    conn = get_db()

    patient_list = conn.execute("""
        SELECT *
        FROM patients
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "patients.html",
        patients=patient_list
    )


@app.route("/add_patient", methods=["POST"])
def add_patient():
    if "user" not in session:
        return redirect("/")

    name = request.form.get("name", "").strip()
    age_text = request.form.get("age", "").strip()
    gender = request.form.get("gender", "").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()
    disease = request.form.get("disease", "").strip()

    if not valid_name(name):
        return form_error(
            "Patient name must contain letters only. "
            "Spaces, periods, apostrophes and hyphens are allowed."
        )

    try:
        age = int(age_text)
    except (ValueError, TypeError):
        return form_error("Age must be a whole number from 1 to 120.")

    if not 1 <= age <= 120:
        return form_error("Age must be between 1 and 120.")

    if not valid_phone(phone):
        return form_error("Phone number must contain exactly 10 digits.")

    if not gender or not disease:
        return form_error("Please complete all required patient fields.")

    conn = get_db()

    conn.execute("""
        INSERT INTO patients
        (name, age, gender, phone, address, disease)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (name, age, gender, phone, address, disease))

    conn.commit()
    conn.close()

    return redirect("/patients")


@app.route("/delete_patient/<int:id>")
def delete_patient(id):
    if "user" not in session:
        return redirect("/")

    conn = get_db()
    conn.execute("DELETE FROM patients WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    return redirect("/patients")


# =========================================================
# DOCTORS
# =========================================================

@app.route("/doctors")
def doctors():
    if "user" not in session:
        return redirect("/")

    conn = get_db()

    doctor_list = conn.execute("""
        SELECT *
        FROM doctors
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "doctors.html",
        doctors=doctor_list
    )


@app.route("/add_doctor", methods=["POST"])
def add_doctor():
    if "user" not in session:
        return redirect("/")

    name = request.form.get("name", "").strip()
    specialization = request.form.get("specialization", "").strip()
    phone = request.form.get("phone", "").strip()

    if not valid_name(name):
        return form_error(
            "Doctor name must contain letters only. "
            "Spaces, periods, apostrophes and hyphens are allowed."
        )

    if not specialization:
        return form_error("Please select the doctor's specialization.")

    if not valid_phone(phone):
        return form_error("Phone number must contain exactly 10 digits.")

    conn = get_db()

    conn.execute("""
        INSERT INTO doctors
        (name, specialization, phone, status)
        VALUES (?, ?, ?, 'Active')
    """, (name, specialization, phone))

    conn.commit()
    conn.close()

    return redirect("/doctors")


@app.route("/delete_doctor/<int:id>")
def delete_doctor(id):
    if "user" not in session:
        return redirect("/")

    conn = get_db()
    conn.execute("DELETE FROM doctors WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    return redirect("/doctors")


# =========================================================
# APPOINTMENTS
# =========================================================

@app.route("/appointments")
def appointments():
    if "user" not in session:
        return redirect("/")

    conn = get_db()

    patient_list = conn.execute("""
        SELECT *
        FROM patients
        ORDER BY name
    """).fetchall()

    doctor_list = conn.execute("""
        SELECT *
        FROM doctors
        WHERE status = 'Active'
        ORDER BY name
    """).fetchall()

    appointment_list = conn.execute("""
        SELECT *
        FROM appointments
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "appointments.html",
        patients=patient_list,
        doctors=doctor_list,
        appointments=appointment_list,
        today=date.today().isoformat(),
        availability_checked=False,
        selected_date="",
        selected_time=""
    )


@app.route("/check_availability", methods=["POST"])
def check_availability():
    if "user" not in session:
        return redirect("/")

    selected_date = request.form.get("date", "").strip()
    selected_time = request.form.get("time", "").strip()

    if not valid_future_date(selected_date):
        return form_error("Please select today or a future appointment date.")

    if not valid_time(selected_time):
        return form_error("Please select a valid appointment time.")

    conn = get_db()

    available_doctors = conn.execute("""
        SELECT *
        FROM doctors
        WHERE status = 'Active'
        AND id NOT IN (
            SELECT doctor_id
            FROM appointments
            WHERE date = ?
              AND time = ?
              AND doctor_id IS NOT NULL
        )
        ORDER BY name
    """, (selected_date, selected_time)).fetchall()

    patient_list = conn.execute("""
        SELECT *
        FROM patients
        ORDER BY name
    """).fetchall()

    appointment_list = conn.execute("""
        SELECT *
        FROM appointments
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "appointments.html",
        patients=patient_list,
        doctors=available_doctors,
        appointments=appointment_list,
        today=date.today().isoformat(),
        selected_date=selected_date,
        selected_time=selected_time,
        availability_checked=True
    )


@app.route("/add_appointment", methods=["POST"])
def add_appointment():
    if "user" not in session:
        return redirect("/")

    patient = request.form.get("patient", "").strip()
    doctor_id_text = request.form.get("doctor_id", "").strip()
    selected_date = request.form.get("date", "").strip()
    selected_time = request.form.get("time", "").strip()

    if not patient:
        return form_error("Please select a registered patient.")

    if not valid_future_date(selected_date):
        return form_error("Please select today or a future appointment date.")

    if not valid_time(selected_time):
        return form_error("Please select a valid appointment time.")

    try:
        doctor_id = int(doctor_id_text)
    except (ValueError, TypeError):
        return form_error("Please select an available doctor.")

    conn = get_db()

    patient_record = conn.execute("""
        SELECT name
        FROM patients
        WHERE name = ?
        LIMIT 1
    """, (patient,)).fetchone()

    doctor_record = conn.execute("""
        SELECT id, name
        FROM doctors
        WHERE id = ? AND status = 'Active'
    """, (doctor_id,)).fetchone()

    if not patient_record:
        conn.close()
        return form_error("That patient is not registered.")

    if not doctor_record:
        conn.close()
        return form_error("That doctor is not active or does not exist.")

    existing = conn.execute("""
        SELECT id
        FROM appointments
        WHERE doctor_id = ?
          AND date = ?
          AND time = ?
    """, (doctor_id, selected_date, selected_time)).fetchone()

    if existing:
        conn.close()
        return form_error(
            "This doctor is already booked at this date and time."
        )

    conn.execute("""
        INSERT INTO appointments
        (patient, doctor, doctor_id, date, time, status)
        VALUES (?, ?, ?, ?, ?, 'Scheduled')
    """, (
        patient_record["name"],
        doctor_record["name"],
        doctor_id,
        selected_date,
        selected_time
    ))

    conn.commit()
    conn.close()

    return redirect("/appointments")


@app.route("/delete_appointment/<int:id>")
def delete_appointment(id):
    if "user" not in session:
        return redirect("/")

    conn = get_db()
    conn.execute("DELETE FROM appointments WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    return redirect("/appointments")


# =========================================================
# BILLING
# =========================================================

@app.route("/billing")
def billing():
    if "user" not in session:
        return redirect("/")

    conn = get_db()

    patient_list = conn.execute("""
        SELECT *
        FROM patients
        ORDER BY name
    """).fetchall()

    bill_list = conn.execute("""
        SELECT *
        FROM bills
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "billing.html",
        patients=patient_list,
        bills=bill_list
    )


@app.route("/add_bill", methods=["POST"])
def add_bill():
    if "user" not in session:
        return redirect("/")

    patient = request.form.get("patient", "").strip()
    status = request.form.get("status", "Pending").strip()

    allowed_statuses = {"Pending", "Overdue", "Paid"}

    if status not in allowed_statuses:
        return form_error("Please select a valid payment status.")

    try:
        consultation_fee = parse_charge("consultation_fee")
        medicine_charges = parse_charge("medicine_charges")
        other_charges = parse_charge("other_charges")
    except ValueError as error:
        return form_error(str(error))

    conn = get_db()

    patient_record = conn.execute("""
        SELECT name
        FROM patients
        WHERE name = ?
        LIMIT 1
    """, (patient,)).fetchone()

    if not patient_record:
        conn.close()
        return form_error("Please select a registered patient.")

    total = round(
        consultation_fee + medicine_charges + other_charges,
        2
    )

    issue_date = date.today().isoformat()

    conn.execute("""
        INSERT INTO bills (
            patient,
            consultation_fee,
            medicine_charges,
            other_charges,
            total,
            status,
            issue_date
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        patient_record["name"],
        consultation_fee,
        medicine_charges,
        other_charges,
        total,
        status,
        issue_date
    ))

    conn.commit()
    conn.close()

    return redirect("/billing")


@app.route("/update_bill_status/<int:id>", methods=["POST"])
def update_bill_status(id):
    if "user" not in session:
        return redirect("/")

    status = request.form.get("status", "").strip()
    allowed_statuses = {"Pending", "Overdue", "Paid"}

    if status not in allowed_statuses:
        return form_error("Please select a valid payment status.")

    conn = get_db()

    bill = conn.execute(
        "SELECT id FROM bills WHERE id = ?",
        (id,)
    ).fetchone()

    if not bill:
        conn.close()
        return form_error("Bill not found.")

    conn.execute("""
        UPDATE bills
        SET status = ?
        WHERE id = ?
    """, (status, id))

    conn.commit()
    conn.close()

    return redirect("/billing")


@app.route("/delete_bill/<int:id>")
def delete_bill(id):
    if "user" not in session:
        return redirect("/")

    conn = get_db()
    conn.execute("DELETE FROM bills WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    return redirect("/billing")


# =========================================================
# START
# =========================================================

init_db()

if __name__ == "__main__":
    app.run(debug=True)
