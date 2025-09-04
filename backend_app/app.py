# backend_app/app.py
from flask import Flask, session, redirect, render_template, url_for,request, flash
from backend_app.auth_routes import auth_bp

app = Flask(__name__)
app.secret_key = "f0852f66a626764d1210fd350779cb9b80aece8949c0ef3ed2ce14f61f2e0aab"
app.register_blueprint(auth_bp)

@app.route('/')
def splash():
    return render_template('splash.html')

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("auth_bp.login"))
    return render_template("dashboard.html")

if __name__ == "__main__":
    app.run(debug=True)

