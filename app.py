from flask import Flask, render_template, request, redirect, session
from DBcm import UseDatabase
from werkzeug.security import generate_password_hash, check_password_hash
import re
from run import run_tests
import os
from flask_wtf.csrf import CSRFProtect

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
csrf = CSRFProtect(app)


db_config = {
    "host": os.environ["MYSQLHOST"],
    "user": os.environ["MYSQLUSER"],
    "password": os.environ["MYSQLPASSWORD"],
    "database": os.environ["MYSQLDATABASE"],
    "port": int(os.environ.get("MYSQLPORT", 3306)),
    "connection_timeout": 10,
}


def rows_as_dicts(cursor):
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


# Home Page
@app.get("/")
def home():
    return render_template("home.html")


# Signup
@app.get("/signup")
def signup():
    return render_template("signup.html")


@app.post("/signup")
def signup_post():
    name = request.form["name"].strip()
    email = request.form["email"].strip().lower()
    password = request.form["password"]
    role = request.form.get("role", "student")
 
    if role not in ["student", "teacher"]:
        return render_template("signup.html", error="Invalid account type.")
 
    if not name or not email or not password:
        return render_template("signup.html", error="Please fill in all fields.")
 
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return render_template("signup.html", error="Please enter a valid email.")
 
    if len(password) < 12:
        return render_template("signup.html", error="Password must be at least 12 characters.")
 
    with UseDatabase(db_config) as cursor:
        cursor.execute(
            "SELECT id FROM users WHERE email=%s", (email,)
        )
 
        if cursor.fetchone():
            return render_template("signup.html", error="Email already exists.")
 
        password_hash = generate_password_hash(password)
 
        cursor.execute("""
            INSERT INTO users (name, email, password_hash, role)
            VALUES (%s, %s, %s, %s)
        """, (name, email, password_hash, role))
 
    return redirect("/login")

 
 # Login
@app.get("/login")
def login():
    return render_template("login.html")


@app.post("/login")
def login_post():
    email = request.form["email"].strip().lower()
    password = request.form["password"]
 
    with UseDatabase(db_config) as cursor:
        cursor.execute(
            "SELECT * FROM users WHERE email=%s", (email,)
        )
        users = rows_as_dicts(cursor)
 
    user = users[0] if users else None
 
    if user and check_password_hash(user["password_hash"], password):
        session.clear()
        session["user_id"] = user["id"]
        session["name"] = user["name"]
        session["role"] = user["role"]
 
        return redirect("/dashboard")
 
    return render_template(
        "login.html", error="Email or password is incorrect."
    )
# Dashboard
@app.get("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")
 
    return render_template("dashboard.html")

# Problems 
@app.get("/problems")
def problems():
    if "user_id" not in session:
        return redirect("/login")
 
    with UseDatabase(db_config) as cursor:
        cursor.execute(
            """
            SELECT
                problems.*,
                COALESCE(MAX(submissions.passed_tests), 0) AS best_score,
                COALESCE(MAX(submissions.passed_tests + submissions.failed_tests), 0) AS total_tests
            FROM problems
            LEFT JOIN submissions
                ON problems.id = submissions.problem_id
                AND submissions.user_id = %s
            GROUP BY problems.id
            ORDER BY problems.id
            """,
            (session["user_id"],)
        )
 
        problems = rows_as_dicts(cursor)
 
    return render_template("problems.html", problems=problems)
 
@app.get("/problem/<int:problem_id>")
def problem(problem_id):
    if "user_id" not in session:
        return redirect("/login")
 
    with UseDatabase(db_config) as cursor:
        cursor.execute(
            "SELECT * FROM problems WHERE id = %s",
            (problem_id,)
        )
        rows = rows_as_dicts(cursor)
 
    if not rows:
        return "Problem not found", 404
 
    problem = rows[0]
 
    if problem_id == 1:
        starter_code = "def add(a, b):\n    pass"
    elif problem_id == 2:
        starter_code = "def multiply(a, b):\n    pass"
    elif problem_id == 3:
        starter_code = "def largest(a, b):\n    pass"
    else:
        starter_code = ""
 
    return render_template(
        "problem.html",
        problem=problem,
        starter_code=starter_code
    )
 
# Submit Solution
@app.post("/submit/<int:problem_id>")
def submit(problem_id):
    if "user_id" not in session:
        return redirect("/login")
 
    source_code = request.form.get("source_code", "").strip()
 
    if len(source_code) > 300:
        return "Code is too long.", 400
 
    if not source_code:
        return "Please enter some code.", 400
 
    with UseDatabase(db_config) as cursor:
        cursor.execute(
            "SELECT * FROM problems WHERE id = %s",
            (problem_id,)
        )
        rows = rows_as_dicts(cursor)
 
    if not rows:
        return "Problem not found", 404
 
    problem = rows[0]
 
    with UseDatabase(db_config) as cursor:
        cursor.execute(
            """
            SELECT id
            FROM submissions
            WHERE user_id = %s
              AND submitted_at > NOW() - INTERVAL 5 SECOND
            LIMIT 1
            """,
            (session["user_id"],)
        )
 
        recent_submission = cursor.fetchone()
 
    if recent_submission:
        return "Please wait 5 seconds before submitting again.", 429
 
    passed, failed, status = run_tests(problem_id, source_code)
 
    if status == "Time Limit Exceeded":
        result_status = "Time Limit Exceeded"
        message = "Time Limit Exceeded."
 
    elif status == "Runtime Error":
        result_status = "Runtime Error"
        message = "Runtime Error. Your code crashed while running."
 
    elif status != "Completed":
        result_status = "Error"
        message = "Could not run the tests. Check your code syntax."
 
    elif passed + failed == 0:
        result_status = "No Tests"
        message = "No tests were run."
 
    elif failed == 0:
        result_status = "Accepted"
        message = f"Accepted! {passed}/{passed + failed} tests passed."
 
    else:
        result_status = "Wrong Answer"
        message = f"Wrong Answer. {passed}/{passed + failed} tests passed."
 
    with UseDatabase(db_config) as cursor:
        cursor.execute(
            """
            INSERT INTO submissions
            (user_id, problem_id, source_code, status, passed_tests, failed_tests)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                session["user_id"],
                problem_id,
                source_code,
                result_status,
                passed,
                failed
            )
        )
 
    return render_template(
        "problem.html",
        problem=problem,
        message=message,
        starter_code=source_code
    )
 
# Logout
@app.post("/logout")
def logout():
    session.clear()
    return redirect("/")
 
if __name__ == "__main__":
    app.run(debug=False)