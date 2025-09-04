# backend_app/auth_routes.py
from flask import Blueprint, render_template, request, redirect, session, flash, url_for
from backend_app.db import get_db_connection
from backend_app.otp_utils import generate_otp
from backend_app.email_utils import send_otp_email
import bcrypt
import re

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        fname = request.form["first_name"]
        lname = request.form["last_name"]
        email = request.form["email"]
        password = request.form["password"]
        confirm = request.form["confirm_password"]

        # Email format validation
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            flash("Invalid email format.", "error")
            return redirect(url_for("auth.signup"))

        # Password match check
        if password != confirm:
            flash("Passwords do not match.", "error")
            return redirect(url_for("auth.signup"))

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (first_name, last_name, email, password_hash) VALUES (%s, %s, %s, %s) RETURNING user_id",
                    (fname, lname, email, hashed.decode()))
        user_id = cur.fetchone()[0]

        otp = generate_otp()
        send_otp_email(email, otp)
        cur.execute("INSERT INTO otps (user_id, otp_code, purpose, expires_at) VALUES (%s, %s, %s, NOW() + INTERVAL '10 minutes')",
                    (user_id, otp, "signup"))
        conn.commit()
        cur.close()
        conn.close()

        session["pending_user_id"] = user_id
        return redirect("/verify_signup_otp")

    return render_template("signup.html")

@auth_bp.route("/verify_signup_otp", methods=["GET", "POST"])
def verify_signup_otp():
    if request.method == "POST":
        otp_input = request.form["otp"]
        user_id = session.get("pending_user_id")

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT otp_code FROM otps WHERE user_id = %s AND purpose = 'signup' ORDER BY created_at DESC LIMIT 1", (user_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()

        if row and row[0] == otp_input:
            return redirect("/login")
        else:
            flash("Invalid OTP. Please try again.", "error")
            return redirect(url_for("auth.verify_signup_otp"))

    return render_template("verify_otp.html")

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT user_id, password_hash FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and bcrypt.checkpw(password.encode(), user[1].encode()):
            otp = generate_otp()
            send_otp_email(email, otp)

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO otps (user_id, otp_code, purpose, expires_at) VALUES (%s, %s, %s, NOW() + INTERVAL '10 minutes')",
                        (user[0], otp, "login"))
            conn.commit()
            cur.close()
            conn.close()

            session["pending_login_user_id"] = user[0]
            return redirect("/verify_login_otp")
        else:
            flash("Invalid credentials. Please try again.", "error")
            return redirect(url_for("auth.login"))

    return render_template("login.html")

@auth_bp.route("/verify_login_otp", methods=["GET", "POST"])
def verify_login_otp():
    if request.method == "POST":
        otp_input = request.form["otp"]
        user_id = session.get("pending_login_user_id")

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT otp_code 
            FROM otps 
            WHERE user_id = %s AND purpose = 'login' 
            ORDER BY created_at DESC 
            LIMIT 1
        """, (user_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()

        if row and row[0] == otp_input:
            session["user_id"] = user_id
            session.pop("pending_login_user_id", None)  # ✅ Clear pending session
            return redirect("/dashboard")
        else:
            flash("Invalid OTP. Please try again.", "error")
            # ✅ Render the OTP page directly so the error shows here
            return render_template("verify_otp.html")

    return render_template("verify_otp.html")

@auth_bp.route("/send_password_otp", methods=["POST"])
def send_password_otp():
    data = request.get_json()
    email = data.get("email")
    new_password = data.get("new_password")
    confirm_password = data.get("confirm_password")

    # ✅ Validate password fields
    if not new_password or not confirm_password:
        return {"success": False, "message": "Both password fields are required."}, 400

    if new_password != confirm_password:
        return {"success": False, "message": "Passwords do not match."}, 400

    # ✅ Proceed only if passwords match
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE email = %s", (email,))
    user = cur.fetchone()

    if not user:
        return {"success": False, "message": "User not found"}, 404

    otp = generate_otp()
    send_otp_email(email, otp)
    cur.execute("INSERT INTO otps (user_id, otp_code, purpose, expires_at) VALUES (%s, %s, %s, NOW() + INTERVAL '10 minutes')",
                (user[0], otp, "password"))
    conn.commit()
    cur.close()
    conn.close()

    print("DEBUG: Incoming data =", data)
    print("DEBUG: new_password =", data.get("new_password"))
    print("DEBUG: confirm_password =", data.get("confirm_password"))


    return {"success": True, "message": "OTP sent successfully"}

@auth_bp.route("/verify_password_otp", methods=["POST"])
def verify_password_otp():
    data = request.get_json()
    otp_input = data.get("otp")
    new_password = data.get("new_password")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id FROM otps 
        WHERE otp_code = %s AND purpose = 'password' AND expires_at > NOW()
        ORDER BY created_at DESC LIMIT 1
    """, (otp_input,))
    row = cur.fetchone()

    if not row:
        cur.close()
        conn.close()
        return {"success": False, "message": "Invalid or expired OTP"}, 400

    hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    cur.execute("UPDATE users SET password_hash = %s WHERE user_id = %s", (hashed, row[0]))
    conn.commit()
    cur.close()
    conn.close()

    return {"success": True, "message": "Password updated successfully"}

@auth_bp.route("/upload_avatar", methods=["POST"])
def upload_avatar():
    if "user_id" not in session:
        return redirect("/login")

    file = request.files.get("avatar")
    if not file:
        flash("No file uploaded.", "error")
        return redirect("/profile")
    
    filename = file.filename
    relative_path = f"uploads/{filename}"  # ✅ relative to static/
    absolute_path = f"backend_app/static/{relative_path}"
    file.save(absolute_path)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET profile_photo = %s WHERE user_id = %s", (relative_path, session["user_id"]))
    conn.commit()
    cur.close()
    conn.close()

    flash("Avatar updated successfully.", "success")
    return redirect("/profile")

@auth_bp.route("/profile", methods=["GET"])
def profile():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT first_name, last_name, email, profile_photo, created_at FROM users WHERE user_id = %s", (session["user_id"],))
    user = cur.fetchone()
    cur.close()
    conn.close()

    return render_template("profile.html", user=user)
