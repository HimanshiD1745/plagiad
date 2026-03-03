import json
import os
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

try:
    import PyPDF2
except Exception:
    PyPDF2 = None

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
REPORT_DIR = BASE_DIR / "reports"
UPLOAD_DIR.mkdir(exist_ok=True)
REPORT_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///plagiad.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AnalysisHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    source_name = db.Column(db.String(255), nullable=False)
    source_type = db.Column(db.String(32), nullable=False)
    raw_text = db.Column(db.Text, nullable=False)
    line_results_json = db.Column(db.Text, nullable=False)
    overall_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def current_user_id():
    return session.get("user_id")


def login_required():
    if not current_user_id():
        flash("Please login first.", "warning")
        return False
    return True


def split_lines(text: str):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        lines = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    return lines


def classify_line(line: str):
    lower = line.lower()
    suspicious_keywords = {
        "direct": ["as an ai language model", "in conclusion", "furthermore", "moreover"],
        "paraphrased": ["rephrased", "summarized", "restated", "adapted from"],
        "mosaic": ["mix of", "blended", "compiled from", "based on several sources"],
    }

    score = 5
    if len(line.split()) > 20:
        score += 10
    if sum(1 for ch in line if ch in ",;:") > 3:
        score += 8
    if re.search(r"\b(the|an|a)\b", lower) and re.search(r"\btherefore|hence|thus\b", lower):
        score += 14

    label = "human-likely"
    highlight_words = []
    if any(k in lower for k in suspicious_keywords["direct"]):
        label = "direct"
        score += 40
        highlight_words.extend([k for k in suspicious_keywords["direct"] if k in lower])
    elif any(k in lower for k in suspicious_keywords["paraphrased"]):
        label = "paraphrasing"
        score += 32
        highlight_words.extend([k for k in suspicious_keywords["paraphrased"] if k in lower])
    elif any(k in lower for k in suspicious_keywords["mosaic"]):
        label = "mosaic"
        score += 28
        highlight_words.extend([k for k in suspicious_keywords["mosaic"] if k in lower])

    score = min(99, max(1, score))
    return {"line": line, "score": score, "label": label, "highlights": highlight_words}


def detect_image_ai_model(filename: str):
    lower = filename.lower()
    signatures = {
        "midjourney": ["mj", "midjourney"],
        "dall-e": ["dalle", "openai", "dall-e"],
        "stable-diffusion": ["sdxl", "stable", "diffusion"],
        "unknown": [],
    }
    for model, keys in signatures.items():
        if any(k in lower for k in keys):
            return model
    return "unknown"


def analyze_text(text: str):
    lines = split_lines(text)
    line_results = [classify_line(line) for line in lines]
    if not line_results:
        return [], {"overall_ai_probability": 0, "dominant_type": "n/a"}

    avg_score = round(sum(item["score"] for item in line_results) / len(line_results), 2)
    type_counts = {}
    for item in line_results:
        type_counts[item["label"]] = type_counts.get(item["label"], 0) + 1
    dominant_type = max(type_counts, key=type_counts.get)
    return line_results, {
        "overall_ai_probability": avg_score,
        "dominant_type": dominant_type,
        "total_lines": len(line_results),
        "flagged_lines": sum(1 for item in line_results if item["label"] != "human-likely"),
    }


def extract_pdf_text(path: Path):
    if PyPDF2 is None:
        return ""
    reader = PyPDF2.PdfReader(str(path))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def highlight_text(line: str, words):
    rendered = line
    for word in words:
        if not word:
            continue
        pattern = re.compile(re.escape(word), re.IGNORECASE)
        rendered = pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", rendered)
    return rendered


@app.route("/")
def index():
    return render_template("index.html", logged_in=bool(current_user_id()))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not username or not email or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("register"))

        existing = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing:
            flash("Username or email already exists.", "danger")
            return redirect(url_for("register"))

        user = User(username=username, email=email, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        flash("Registration successful. Please login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash("Invalid credentials.", "danger")
            return redirect(url_for("login"))

        session["user_id"] = user.id
        session["username"] = user.username
        flash("Welcome back!", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("index"))


@app.route("/dashboard")
def dashboard():
    if not login_required():
        return redirect(url_for("login"))
    history = AnalysisHistory.query.filter_by(user_id=current_user_id()).order_by(AnalysisHistory.created_at.desc()).all()
    return render_template("dashboard.html", history=history)


@app.route("/analyze", methods=["POST"])
def analyze():
    if not login_required():
        return redirect(url_for("login"))

    text_input = request.form.get("text_input", "").strip()
    uploaded_file = request.files.get("file_input")

    source_type = "text"
    source_name = "typed_text"
    raw_text = text_input
    ai_image_model = None

    if uploaded_file and uploaded_file.filename:
        filename = secure_filename(uploaded_file.filename)
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        file_path = UPLOAD_DIR / f"{datetime.utcnow().timestamp()}_{filename}"
        uploaded_file.save(file_path)
        source_name = filename

        if ext == "pdf":
            source_type = "pdf"
            raw_text = extract_pdf_text(file_path)
        elif ext in {"png", "jpg", "jpeg", "webp"}:
            source_type = "image"
            raw_text = f"Image upload: {filename}. Text analysis skipped."
            ai_image_model = detect_image_ai_model(filename)
        else:
            source_type = "text"
            raw_text = text_input or ""

    if not raw_text:
        flash("Please add text or upload a supported file.", "danger")
        return redirect(url_for("dashboard"))

    line_results, overall = analyze_text(raw_text)
    if ai_image_model:
        overall["detected_image_ai_model"] = ai_image_model

    entry = AnalysisHistory(
        user_id=current_user_id(),
        source_name=source_name,
        source_type=source_type,
        raw_text=raw_text,
        line_results_json=json.dumps(line_results),
        overall_json=json.dumps(overall),
    )
    db.session.add(entry)
    db.session.commit()

    return redirect(url_for("report", analysis_id=entry.id))


@app.route("/report/<int:analysis_id>")
def report(analysis_id):
    if not login_required():
        return redirect(url_for("login"))

    entry = AnalysisHistory.query.filter_by(id=analysis_id, user_id=current_user_id()).first_or_404()
    line_results = json.loads(entry.line_results_json)
    overall = json.loads(entry.overall_json)
    rendered_lines = [
        {**line, "rendered_line": highlight_text(line["line"], line.get("highlights", []))}
        for line in line_results
    ]
    return render_template("report.html", entry=entry, line_results=rendered_lines, overall=overall)


@app.route("/download-report/<int:analysis_id>")
def download_report(analysis_id):
    if not login_required():
        return redirect(url_for("login"))

    entry = AnalysisHistory.query.filter_by(id=analysis_id, user_id=current_user_id()).first_or_404()
    line_results = json.loads(entry.line_results_json)
    overall = json.loads(entry.overall_json)

    body_lines = []
    for idx, line in enumerate(line_results, start=1):
        body_lines.append(
            f"<li><strong>Line {idx}</strong> [{line['label']}, {line['score']}%]: {highlight_text(line['line'], line.get('highlights', []))}</li>"
        )

    html = f"""
    <html><head><meta charset='utf-8'><title>Plagiad Report</title>
    <style>body{{font-family:Arial;padding:20px}}mark{{background:#ffed6f}} .card{{border:1px solid #ccc;padding:16px;border-radius:8px}}</style>
    </head><body>
    <h1>Plagiad Analysis Report</h1>
    <p><strong>Source:</strong> {entry.source_name} ({entry.source_type})</p>
    <div class='card'><h2>Line by Line Analysis</h2><ol>{''.join(body_lines)}</ol></div>
    <div class='card'><h2>Overall Analysis</h2>
    <p>AI Probability: {overall.get('overall_ai_probability', 0)}%</p>
    <p>Dominant Type: {overall.get('dominant_type', 'n/a')}</p>
    <p>Flagged Lines: {overall.get('flagged_lines', 0)} / {overall.get('total_lines', 0)}</p>
    </div>
    </body></html>
    """

    buffer = BytesIO(html.encode("utf-8"))
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"report_{analysis_id}.html",
        mimetype="text/html",
    )


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)
