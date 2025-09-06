# backend_app/auth_routes.py
from flask import Blueprint, render_template, request, redirect, session, flash, url_for, jsonify, send_file
from backend_app.db import get_db_connection
from backend_app.otp_utils import generate_otp
from backend_app.email_utils import send_otp_email
import bcrypt
import re
import os
from werkzeug.utils import secure_filename
from backend_app.db import get_db_connection
import pickle
from fpdf import FPDF
import torch
from peft import PeftModel
from transformers import AutoModelForSeq2SeqLM, AutoModelForSeq2SeqLM, AutoTokenizer
import fitz  # PyMuPDF
from backend_app.db import get_db_connection
from psycopg2.extras import RealDictCursor
from datetime import datetime
from backend_app.lora_adapter import generate_with_lora
from backend_app.nlp_postprocess import clean_output
from backend_app.utils.pdf_utils import extract_text_from_pdf   

auth_bp = Blueprint("auth", __name__)

# ✅ Load base model and LoRA adapter correctly
base_model = AutoModelForSeq2SeqLM.from_pretrained("google/flan-t5-small")
tokenizer = AutoTokenizer.from_pretrained("google/flan-t5-small")
lora_model = PeftModel.from_pretrained(base_model, "backend_app/utils/lora_adapter")

# ✅ Only one simplify_text function
def simplify_text(text):
    inputs = tokenizer("simplify: " + text, return_tensors="pt", truncation=True, max_length=512)
    outputs = lora_model.generate(
        input_ids=inputs["input_ids"],
        attention_mask=inputs["attention_mask"],
        max_new_tokens=256
    )
    return tokenizer.decode(outputs[0], skip_special_tokens=True)

def get_user_details(user_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT first_name, last_name, email, profile_photo
        FROM users
        WHERE user_id = %s
    """, (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

def extract_text_from_pdf(path):
    text = ""
    try:
        doc = fitz.open(path)
        for page in doc:
            text += page.get_text()
        doc.close()
    except Exception as e:
        print("Error extracting text:", e)
    return text

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

@auth_bp.route("/accept_agreement", methods=["POST"])
def accept_agreement():
    user_id = session.get("user_id")
    if not user_id:
        flash("Session expired. Please log in again.", "error")
        return redirect("/login")

    agreement_accepted = request.form.get("agreement") == "on"
    if not agreement_accepted:
        flash("You must accept the agreement to continue.", "error")
        return redirect("/agreement")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO agreements (user_id, accepted, accepted_at)
        VALUES (%s, TRUE, NOW())
    """, (user_id,))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("auth.document_interface"))


@auth_bp.route("/agreement")
def agreement():
    return render_template("agreement.html")

# ✅ Optional fallback simplifier (can be removed)
def simplify_document(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    simplified = content.replace("hereinafter", "from now on").replace("aforementioned", "mentioned earlier")
    return simplified

def generate_pdf(text, output_path):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # ✅ Use Unicode-compatible font
    font_path = os.path.join("backend_app", "static", "fonts", "DejaVuSans.ttf")
    pdf.add_font("DejaVu", "", font_path, uni=True)
    pdf.set_font("DejaVu", size=12)

    for line in text.split("\n"):
        try:
            pdf.multi_cell(0, 10, line)
        except Exception as e:
            print("PDF write error:", e)
            pdf.multi_cell(0, 10, "[⚠️ Text could not be rendered]")

    pdf.output(output_path)

@auth_bp.route("/submit_document", methods=["POST"])
def submit_document():
    try:
        file = request.files.get("document")
        print("Received file:", file.filename)
        user_id = session.get("user_id")
        if not user_id:
            return redirect("/login")

        if not file or not file.filename.lower().endswith(".pdf"):
            flash("Only PDF files are allowed.", "error")
            return redirect(url_for("auth.document_interface"))

        filename = secure_filename(file.filename)
        raw_path = os.path.join("backend_app/static/uploads", filename)
        os.makedirs(os.path.dirname(raw_path), exist_ok=True)
        file.save(raw_path)

        original_text = extract_text_from_pdf(raw_path)
        print("Extracted text length:", len(original_text))

        prompt = f"Simplify this clause for a small business owner unfamiliar with legal terms:\n\n{original_text}"

        simplified_text = None
        try:
            raw_output = generate_with_lora(prompt)
            print("Raw Output from LoRA:", raw_output)
            simplified_text = clean_output(raw_output)
            print("Cleaned Output:", simplified_text)
        except Exception as e:
            print("Simplification error:", e)
            flash("⚠️ Simplification failed. Please try again.", "error")
            return redirect(url_for("auth.document_interface"))

        if not simplified_text or simplified_text.strip() == "":
            flash("⚠️ Simplification returned empty output.", "error")
            return redirect(url_for("auth.document_interface"))

        simplified_filename = f"simplified_{filename.replace('.pdf', '')}.pdf"
        simplified_path = os.path.join("static", "simplified", simplified_filename)
        os.makedirs(os.path.dirname(simplified_path), exist_ok=True)
        generate_pdf(simplified_text, simplified_path)
        print("PDF generated at:", simplified_path)

        session["pending_doc"] = {
            "filename": filename,
            "raw_path": raw_path,
            "simplified_path": simplified_path
        }

        return redirect(url_for("auth.save_prompt", path=simplified_path))

    except Exception as e:
        print("Error during document submission:", e)
        flash("⚠️ Internal server error during document processing.", "error")
        return redirect(url_for("auth.document_interface"))
    
@auth_bp.route("/confirm_save", methods=["POST"])
def confirm_save():
    user_id = session.get("user_id")
    if not user_id or "pending_doc" not in session:
        return redirect("/document_interface")

    decision = request.form.get("save_decision")
    doc_data = session.pop("pending_doc")

    if decision == "yes":
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO documents (user_id, filename, file_path, saved)
            VALUES (%s, %s, %s, TRUE) RETURNING doc_id
        """, (user_id, doc_data["filename"], doc_data["raw_path"]))
        doc_id = cur.fetchone()[0]
        cur.execute("""
            INSERT INTO simplified_documents (doc_id, file_path)
            VALUES (%s, %s)
        """, (doc_id, doc_data["simplified_path"]))
        conn.commit()
        cur.close()
        conn.close()

    user = get_user_details(user_id)
    return render_template("post_actions.html", simplified_path=doc_data["simplified_path"], user=user, current_year=datetime.now().year)

@auth_bp.route("/download_simplified")
def download_simplified():
    rel_path = request.args.get("path")
    abs_path = os.path.join(os.getcwd(), rel_path)

    if not os.path.exists(abs_path):
        flash("Simplified document not found.", "error")
        return redirect(url_for("auth.document_interface"))

    return send_file(abs_path, as_attachment=True)

@auth_bp.route("/view_simplified")
def view_simplified():
    rel_path = request.args.get("path")
    abs_path = os.path.join(os.getcwd(), rel_path)

    if not os.path.exists(abs_path):
        flash("Simplified document not found.", "error")
        return redirect(url_for("auth.document_interface"))

    return send_file(abs_path)

@auth_bp.route("/submit_review", methods=["POST"])
def submit_review():
    user_id = session.get("user_id")
    simplified_path = request.form.get("simplified_path")
    rating = int(request.form.get("rating"))
    comment = request.form.get("comment")

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Get simplified_id from path
    cur.execute("""
        SELECT simplified_id FROM simplified_documents WHERE file_path = %s
    """, (simplified_path,))
    simplified = cur.fetchone()

    if simplified:
        simplified_id = simplified["simplified_id"]
        cur.execute("""
            INSERT INTO document_reviews (simplified_id, user_id, rating, comment)
            VALUES (%s, %s, %s, %s)
        """, (simplified_id, user_id, rating, comment))
        conn.commit()
        flash("Thanks for your feedback!", "success")

    # Fetch current user details for profile dropdown
    cur.execute("""
        SELECT first_name, last_name, email, profile_photo
        FROM users
        WHERE user_id = %s
    """, (user_id,))
    user = cur.fetchone()

    cur.close()
    conn.close()

    return render_template("post_actions.html", simplified_path=simplified_path, user=user, current_year=datetime.now().year)


@auth_bp.route("/document_interface")
def document_interface():
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")
    user = get_user_details(user_id)
    return render_template("document_interface.html", user=user, current_year=datetime.now().year)


@auth_bp.route("/save_prompt")
def save_prompt():
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")
    path = request.args.get("path")
    user = get_user_details(user_id)
    return render_template("save_prompt.html", simplified_path=path, user=user, current_year=datetime.now().year)


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect("/login")

@auth_bp.route("/saved")
def view_documents():
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    # Get search query and toast flag
    search = request.args.get("search", "").strip()
    deleted = request.args.get("deleted") == "true"

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Fetch user details for navbar dropdown
    cur.execute("""
        SELECT first_name, last_name, email, profile_photo
        FROM users
        WHERE user_id = %s
    """, (user_id,))
    user = cur.fetchone()

    # Fetch saved documents
    query = """
        SELECT d.doc_id,
               d.filename,
               d.file_path AS original_path,
               sd.simplified_id,
               sd.file_path AS simplified_path,
               dr.rating,
               dr.comment
        FROM documents d
        LEFT JOIN simplified_documents sd ON d.doc_id = sd.doc_id
        LEFT JOIN document_reviews dr ON sd.simplified_id = dr.simplified_id AND dr.user_id = %s
        WHERE d.user_id = %s
    """
    params = [user_id, user_id]

    if search:
        query += " AND LOWER(d.filename) LIKE %s"
        params.append(f"%{search.lower()}%")

    query += " ORDER BY d.uploaded_at ASC"

    cur.execute(query, params)
    documents = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "view_documents.html",
        documents=documents,
        search=search,
        deleted=deleted,
        user=user,
        current_year=datetime.now().year
    )

@auth_bp.route("/delete_document/<int:doc_id>", methods=["POST"])
def delete_document(doc_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Get simplified document path
    cur.execute("""
        SELECT d.file_path AS original_path,
               sd.file_path AS simplified_path,
               sd.simplified_id
        FROM documents d
        LEFT JOIN simplified_documents sd ON d.doc_id = sd.doc_id
        WHERE d.doc_id = %s AND d.user_id = %s
    """, (doc_id, user_id))
    doc = cur.fetchone()

    if not doc:
        cur.close()
        conn.close()
        return redirect("/saved")

    # Delete files
    for path in [doc["original_path"], doc["simplified_path"]]:
        if path:
            abs_path = os.path.join(os.getcwd(), path)
            if os.path.exists(abs_path):
                os.remove(abs_path)

    # Delete review
    if doc["simplified_id"]:
        cur.execute("DELETE FROM document_reviews WHERE simplified_id = %s", (doc["simplified_id"],))

    # Delete simplified document
    cur.execute("DELETE FROM simplified_documents WHERE doc_id = %s", (doc_id,))
    # Delete original document
    cur.execute("DELETE FROM documents WHERE doc_id = %s", (doc_id,))
    conn.commit()

    conn.commit()
    cur.close()
    conn.close()

    return redirect("/saved?deleted=true")

@auth_bp.route("/reviews", methods=["GET", "POST"])
def site_reviews():
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Fetch current user details for profile dropdown
    cur.execute("""
        SELECT first_name, last_name, email, profile_photo
        FROM users
        WHERE user_id = %s
    """, (user_id,))
    user = cur.fetchone()

    # Handle form submission
    if request.method == "POST":
        rating = int(request.form.get("rating", 0))
        comment = request.form.get("comment", "").strip()

        if 1 <= rating <= 5 and comment:
            cur.execute("""
                INSERT INTO site_reviews (user_id, rating, comment)
                VALUES (%s, %s, %s)
            """, (user_id, rating, comment))
            conn.commit()
            return redirect("/reviews")

    # Fetch all reviews
    cur.execute("""
        SELECT sr.rating, sr.comment, sr.reviewed_at, u.first_name, u.last_name
        FROM site_reviews sr
        JOIN users u ON sr.user_id = u.user_id
        ORDER BY sr.reviewed_at ASC
    """)
    reviews = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("site_reviews.html", reviews=reviews, user=user, current_year=datetime.now().year)


@auth_bp.route("/dashboard")
def dashboard():
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT first_name, last_name, email, profile_photo FROM users WHERE user_id = %s", (user_id,))
    user = cur.fetchone()

    cur.close()
    conn.close()

    return render_template("dashboard.html", user=user, current_year=datetime.now().year)

@auth_bp.route("/remove_avatar", methods=["POST"])
def remove_avatar():
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor()

    # Set profile_photo to NULL
    cur.execute("UPDATE users SET profile_photo = NULL WHERE user_id = %s", (user_id,))
    conn.commit()

    cur.close()
    conn.close()

    return redirect("/profile")
