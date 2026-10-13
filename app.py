from flask import Flask, render_template, request, redirect, session
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
import re

app = Flask(__name__)
app.secret_key = "secret123"


# Database Connection
def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="root",
        database="codesite"
    )


# Home Page
@app.route("/")
def home():
    return render_template("home.html")


# Signup
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
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

        db = get_db()
        cursor = db.cursor()

        try:
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

            db.commit()

        finally:
            cursor.close()
            db.close()

        return redirect("/login")

    return render_template("signup.html")


# Login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        db = get_db()
        cursor = db.cursor(dictionary=True)

        try:
            cursor.execute(
                "SELECT * FROM users WHERE email=%s", (email,)
            )
            user = cursor.fetchone()
        finally:
            cursor.close()
            db.close()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]

            return redirect("/dashboard")

        return render_template(
            "login.html", error="Email or password is incorrect."
        )

    return render_template("login.html")


# Dashboard
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    return render_template("dashboard.html")


# Logout
@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect("/")


if __name__ == "__main__":
    app.run(debug=True)