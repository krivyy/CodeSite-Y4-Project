from flask import Flask, render_template, request, redirect, session
from DBcm import UseDatabase
from werkzeug.security import generate_password_hash, check_password_hash
import re
from run import run_tests
import os
from flask_wtf.csrf import CSRFProtect
import secrets

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
 
    if session["role"] == "teacher":
        return teacher_dashboard()

    return student_dashboard()


def student_dashboard(error=None):
    with UseDatabase(db_config) as cursor:
        cursor.execute(
            """
            SELECT classes.id, classes.name, users.name AS teacher_name
            FROM class_members
            JOIN classes ON classes.id = class_members.class_id
            JOIN users ON users.id = classes.teacher_id
            WHERE class_members.student_id = %s
            ORDER BY classes.name
            """,
            (session["user_id"],)
        )
        my_classes = rows_as_dicts(cursor)
 
        cursor.execute("SELECT COUNT(*) FROM problems")
        total_problems = cursor.fetchall()[0][0]
 
        cursor.execute(
            """
            SELECT COUNT(DISTINCT problem_id)
            FROM submissions
            WHERE user_id = %s AND status = 'Accepted'
            """,
            (session["user_id"],)
        )
        solved_problems = cursor.fetchall()[0][0]
 
    return render_template(
        "student_dashboard.html",
        error=error,
        my_classes=my_classes,
        total_problems=total_problems,
        solved_problems=solved_problems
    )
 
 
def teacher_dashboard():
    with UseDatabase(db_config) as cursor:
        cursor.execute(
            """
            SELECT classes.id, classes.name, classes.join_code,
                   COUNT(class_members.student_id) AS students
            FROM classes
            LEFT JOIN class_members ON class_members.class_id = classes.id
            WHERE classes.teacher_id = %s
            GROUP BY classes.id
            ORDER BY classes.name
            """,
            (session["user_id"],)
        )
        my_classes = rows_as_dicts(cursor)
 
    return render_template("teacher_dashboard.html", my_classes=my_classes)
 
 
# Classes
JOIN_CODE_CHARACTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
 
 
@app.post("/classes")
def create_class():
    if session.get("role") != "teacher":
        return redirect("/login")
 
    name = request.form.get("name", "").strip()
 
    if not name or len(name) > 100:
        return redirect("/dashboard")
 
    with UseDatabase(db_config) as cursor:
        # Pick a random code that no other class is using
        while True:
            join_code = "".join(secrets.choice(JOIN_CODE_CHARACTERS) for _ in range(6))
            cursor.execute("SELECT id FROM classes WHERE join_code = %s", (join_code,))
            if not cursor.fetchall():
                break
 
        cursor.execute(
            "INSERT INTO classes (name, join_code, teacher_id) VALUES (%s, %s, %s)",
            (name, join_code, session["user_id"])
        )
 
    return redirect("/dashboard")
 
 
@app.post("/classes/join")
def join_class():
    if session.get("role") != "student":
        return redirect("/login")
 
    join_code = request.form.get("join_code", "").strip().upper()
 
    with UseDatabase(db_config) as cursor:
        cursor.execute("SELECT id FROM classes WHERE join_code = %s", (join_code,))
        rows = cursor.fetchall()
 
        if rows:
            # IGNORE: joining a class you're already in does nothing
            cursor.execute(
                "INSERT IGNORE INTO class_members (class_id, student_id) VALUES (%s, %s)",
                (rows[0][0], session["user_id"])
            )
 
    if not rows:
        return student_dashboard(error="No class found with that code.")
 
    return redirect("/dashboard")
 
 
def get_class(class_id):
    # Returns (class_info, is_teacher), or (None, False) if this user isn't
    # the class's teacher or one of its students.
    with UseDatabase(db_config) as cursor:
        cursor.execute(
            """
            SELECT classes.id, classes.name, classes.join_code, classes.teacher_id,
                   users.name AS teacher_name
            FROM classes
            JOIN users ON users.id = classes.teacher_id
            WHERE classes.id = %s
            """,
            (class_id,)
        )
        rows = rows_as_dicts(cursor)
 
        cursor.execute(
            "SELECT student_id FROM class_members WHERE class_id = %s AND student_id = %s",
            (class_id, session["user_id"])
        )
        is_student = bool(cursor.fetchall())
 
    is_teacher = bool(rows) and rows[0]["teacher_id"] == session["user_id"]
 
    if not (is_teacher or is_student):
        return None, False
 
    return rows[0], is_teacher
 
 
def get_students(class_id):
    with UseDatabase(db_config) as cursor:
        cursor.execute(
            """
            SELECT users.id, users.name, users.email, class_members.joined_at
            FROM class_members
            JOIN users ON users.id = class_members.student_id
            WHERE class_members.class_id = %s
            ORDER BY users.name
            """,
            (class_id,)
        )
        return rows_as_dicts(cursor)
 
 
# Stream tab
@app.get("/class/<int:class_id>")
def class_stream(class_id):
    if "user_id" not in session:
        return redirect("/login")
 
    class_info, is_teacher = get_class(class_id)
    if not class_info:
        return "Class not found", 404
 
    recent_submissions = []
    if is_teacher:
        with UseDatabase(db_config) as cursor:
            cursor.execute(
                """
                SELECT users.name, problems.title, submissions.status,
                       submissions.passed_tests, submissions.failed_tests,
                       submissions.submitted_at
                FROM submissions
                JOIN users ON users.id = submissions.user_id
                JOIN problems ON problems.id = submissions.problem_id
                JOIN class_members ON class_members.student_id = submissions.user_id
                WHERE class_members.class_id = %s
                ORDER BY submissions.submitted_at DESC
                LIMIT 10
                """,
                (class_id,)
            )
            recent_submissions = rows_as_dicts(cursor)
 
    return render_template(
        "class_stream.html",
        class_info=class_info,
        is_teacher=is_teacher,
        tab="stream",
        recent_submissions=recent_submissions
    )
 
 
# Classwork tab
@app.get("/class/<int:class_id>/classwork")
def class_classwork(class_id):
    if "user_id" not in session:
        return redirect("/login")
 
    class_info, is_teacher = get_class(class_id)
    if not class_info:
        return "Class not found", 404
 
    return render_template(
        "class_classwork.html",
        class_info=class_info,
        is_teacher=is_teacher,
        tab="classwork"
    )
 
 
# People tab
@app.get("/class/<int:class_id>/people")
def class_people(class_id):
    if "user_id" not in session:
        return redirect("/login")
 
    class_info, is_teacher = get_class(class_id)
    if not class_info:
        return "Class not found", 404
 
    return render_template(
        "class_people.html",
        class_info=class_info,
        is_teacher=is_teacher,
        tab="people",
        students=get_students(class_id)
    )
 
 
# Grades tab (teacher only)
@app.get("/class/<int:class_id>/grades")
def class_grades(class_id):
    if "user_id" not in session:
        return redirect("/login")
 
    class_info, is_teacher = get_class(class_id)
    if not class_info or not is_teacher:
        return "Class not found", 404
 
    students = get_students(class_id)
 
    with UseDatabase(db_config) as cursor:
        cursor.execute("SELECT id, title FROM problems ORDER BY id")
        problems = rows_as_dicts(cursor)
 
        # Each student's best score on each problem
        cursor.execute(
            """
            SELECT submissions.user_id, submissions.problem_id,
                   MAX(submissions.passed_tests) AS best,
                   MAX(submissions.passed_tests + submissions.failed_tests) AS total
            FROM submissions
            JOIN class_members ON class_members.student_id = submissions.user_id
            WHERE class_members.class_id = %s
            GROUP BY submissions.user_id, submissions.problem_id
            """,
            (class_id,)
        )
        grades = {}
        for row in rows_as_dicts(cursor):
            grades.setdefault(row["user_id"], {})[row["problem_id"]] = row
 
    return render_template(
        "class_grades.html",
        class_info=class_info,
        is_teacher=is_teacher,
        tab="grades",
        students=students,
        problems=problems,
        grades=grades
    )

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