"""Student Second Hand Book Exchange App - Flask + SQLite."""
import os, re, secrets, sqlite3, uuid
from datetime import datetime
from functools import wraps
from flask import (Flask, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

APP_NAME = "Student Second Hand Book Exchange"
BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "books.db")
ALLOWED = {"png", "jpg", "jpeg", "gif", "webp"}
CONDITIONS = ["Like new", "Good", "Fair", "Worn"]
SUBJECTS = ["Programming", "Databases", "Web Design", "Networking",
            "Mathematics", "Business", "Science", "Languages", "Other"]

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "change-this-secret-key"),
    UPLOAD_FOLDER=os.path.join(BASE, "static", "uploads"),
    MAX_CONTENT_LENGTH=4 * 1024 * 1024,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, student_id TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, is_admin INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS books(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT NOT NULL, author TEXT NOT NULL, subject TEXT NOT NULL,
  offer TEXT NOT NULL, price REAL, cond TEXT NOT NULL, note TEXT, photo TEXT,
  status TEXT DEFAULT 'available', created TEXT);
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  receiver_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  body TEXT NOT NULL, created TEXT);
CREATE TABLE IF NOT EXISTS reports(
  id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  reporter_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  reason TEXT NOT NULL, created TEXT);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(_=None):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    with sqlite3.connect(DB) as c:
        c.executescript(SCHEMA)


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


@app.before_request
def load_user():
    session.setdefault("csrf", secrets.token_hex(16))
    g.user = None
    if "uid" in session:
        g.user = get_db().execute("SELECT * FROM users WHERE id=?", (session["uid"],)).fetchone()
        if g.user is None:
            session.pop("uid")
    if request.method == "POST" and not secrets.compare_digest(
            request.form.get("csrf", ""), session["csrf"]):
        abort(400)


@app.context_processor
def inject():
    return dict(app_name=APP_NAME, user=g.user, csrf_token=session.get("csrf", ""),
                CONDITIONS=CONDITIONS, SUBJECTS=SUBJECTS)


def login_required(f):
    @wraps(f)
    def wrapper(*a, **k):
        if g.user is None:
            flash("Please log in first.", "error")
            return redirect(url_for("login"))
        return f(*a, **k)
    return wrapper


def get_book(book_id):
    b = get_db().execute(
        "SELECT b.*, u.name AS seller FROM books b JOIN users u ON u.id=b.user_id WHERE b.id=?",
        (book_id,)).fetchone()
    if b is None:
        abort(404)
    return b


def can_manage(b):
    return g.user is not None and (g.user["id"] == b["user_id"] or g.user["is_admin"])


def query_books(a):
    sql = ("SELECT b.*, u.name AS seller FROM books b JOIN users u ON u.id=b.user_id "
           "WHERE b.status='available'")
    p = []
    q = a.get("q", "").strip()
    if q:
        sql += " AND (b.title LIKE ? OR b.author LIKE ? OR b.subject LIKE ?)"
        p += [f"%{q}%"] * 3
    for key, col in (("condition", "cond"), ("offer", "offer"), ("subject", "subject")):
        if a.get(key):
            sql += f" AND b.{col}=?"
            p.append(a[key])
    try:
        mp = float(a.get("max_price", ""))
        sql += " AND (b.offer='exchange' OR b.price<=?)"
        p.append(mp)
    except ValueError:
        pass
    return get_db().execute(sql + " ORDER BY b.id DESC LIMIT 60", p).fetchall()


# ---------- browse ----------
@app.get("/")
def index():
    return render_template("index.html", books=query_books(request.args))


@app.get("/cards")
def cards():  # HTML fragment used by static/app.js for live search
    return render_template("_cards.html", books=query_books(request.args))


# ---------- accounts ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        name, sid = f.get("name", "").strip(), f.get("student_id", "").strip()
        email, pw = f.get("email", "").strip().lower(), f.get("password", "")
        db = get_db()
        if len(name) < 2 or not re.fullmatch(r"\d{6,15}", sid) or "@" not in email or len(pw) < 8:
            flash("Enter your name, a numeric student ID, a valid email and a password of 8+ characters.", "error")
        elif db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            flash("That email is already registered. Log in instead.", "error")
        else:
            first = db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
            cur = db.execute("INSERT INTO users(name,student_id,email,password_hash,is_admin) VALUES(?,?,?,?,?)",
                             (name, sid, email, generate_password_hash(pw), int(first)))
            db.commit()
            session["uid"] = cur.lastrowid
            flash("Welcome! Your account is ready.", "ok")
            return redirect(url_for("index"))
    return render_template("auth.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = get_db().execute("SELECT * FROM users WHERE email=?",
                             (request.form.get("email", "").strip().lower(),)).fetchone()
        if u and check_password_hash(u["password_hash"], request.form.get("password", "")):
            session["uid"] = u["id"]
            return redirect(url_for("index"))
        flash("Email or password is wrong.", "error")
    return render_template("auth.html", mode="login")


@app.post("/logout")
def logout():
    session.pop("uid", None)
    return redirect(url_for("index"))


# ---------- listings ----------
def save_photo(file):
    if not file or not file.filename:
        return None
    ext = secure_filename(file.filename).rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED:
        return None
    name = f"{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], name))
    return name


def remove_photo(name):
    if name:
        try:
            os.remove(os.path.join(app.config["UPLOAD_FOLDER"], name))
        except OSError:
            pass


def book_form(book=None):
    if request.method == "POST":
        f, errors = request.form, []
        d = dict(title=f.get("title", "").strip()[:120], author=f.get("author", "").strip()[:80],
                 subject=f.get("subject", ""), offer=f.get("offer", "sell"),
                 cond=f.get("condition", ""), note=f.get("note", "").strip()[:300], price=None)
        if not d["title"] or not d["author"]:
            errors.append("Title and author are required.")
        if d["subject"] not in SUBJECTS or d["cond"] not in CONDITIONS or d["offer"] not in ("sell", "exchange"):
            errors.append("Choose a subject, condition and offer type.")
        if d["offer"] == "sell":
            try:
                d["price"] = round(float(f.get("price", "")), 2)
                if not 0 <= d["price"] <= 1000:
                    raise ValueError
            except ValueError:
                errors.append("Enter a price between 0 and 1000.")
        if not errors:
            db = get_db()
            photo = save_photo(request.files.get("photo"))
            if book is None:
                cur = db.execute("INSERT INTO books(user_id,title,author,subject,offer,price,cond,note,photo,created) "
                                 "VALUES(?,?,?,?,?,?,?,?,?,?)",
                                 (g.user["id"], d["title"], d["author"], d["subject"], d["offer"],
                                  d["price"], d["cond"], d["note"], photo, now()))
                bid = cur.lastrowid
            else:
                bid = book["id"]
                if photo:
                    remove_photo(book["photo"])
                db.execute("UPDATE books SET title=?,author=?,subject=?,offer=?,price=?,cond=?,note=?,photo=? WHERE id=?",
                           (d["title"], d["author"], d["subject"], d["offer"], d["price"], d["cond"],
                            d["note"], photo or book["photo"], bid))
            db.commit()
            flash("Listing saved.", "ok")
            return redirect(url_for("book", book_id=bid))
        for e in errors:
            flash(e, "error")
    return render_template("book_form.html", book=dict(book) if book else None)


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    return book_form()


@app.route("/book/<int:book_id>/edit", methods=["GET", "POST"])
@login_required
def edit(book_id):
    b = get_book(book_id)
    if not can_manage(b):
        abort(403)
    return book_form(b)


@app.get("/book/<int:book_id>")
def book(book_id):
    b = get_book(book_id)
    msgs, partners = [], []
    if g.user:
        msgs = get_db().execute(
            "SELECT m.*, s.name AS sender, s.email AS sender_email FROM messages m "
            "JOIN users s ON s.id=m.sender_id WHERE m.book_id=? AND (m.sender_id=? OR m.receiver_id=?) ORDER BY m.id",
            (book_id, g.user["id"], g.user["id"])).fetchall()
        if g.user["id"] == b["user_id"]:
            seen = {}
            for m in msgs:
                if m["sender_id"] != g.user["id"]:
                    seen[m["sender_id"]] = m["sender"]
            partners = list(seen.items())
    return render_template("book.html", b=b, msgs=msgs, partners=partners)


@app.post("/book/<int:book_id>/sold")
@login_required
def toggle_sold(book_id):
    b = get_book(book_id)
    if not can_manage(b):
        abort(403)
    get_db().execute("UPDATE books SET status=? WHERE id=?",
                     ("available" if b["status"] == "sold" else "sold", book_id))
    get_db().commit()
    return redirect(url_for("book", book_id=book_id))


@app.post("/book/<int:book_id>/delete")
@login_required
def delete(book_id):
    b = get_book(book_id)
    if not can_manage(b):
        abort(403)
    remove_photo(b["photo"])
    get_db().execute("DELETE FROM books WHERE id=?", (book_id,))
    get_db().commit()
    flash("Listing deleted.", "ok")
    return redirect(url_for("admin" if request.form.get("from") == "admin" else "my"))


# ---------- messages and reports ----------
@app.post("/book/<int:book_id>/message")
@login_required
def message(book_id):
    b = get_book(book_id)
    body = request.form.get("body", "").strip()[:500]
    to = b["user_id"]
    if g.user["id"] == b["user_id"]:  # seller replying to a buyer who wrote first
        try:
            to = int(request.form.get("to", ""))
        except ValueError:
            abort(400)
        if not get_db().execute("SELECT 1 FROM messages WHERE book_id=? AND sender_id=?", (book_id, to)).fetchone():
            abort(400)
    if not body:
        flash("Write a message first.", "error")
    else:
        get_db().execute("INSERT INTO messages(book_id,sender_id,receiver_id,body,created) VALUES(?,?,?,?,?)",
                         (book_id, g.user["id"], to, body, now()))
        get_db().commit()
        flash("Message sent.", "ok")
    return redirect(url_for("book", book_id=book_id) + "#messages")


@app.post("/book/<int:book_id>/report")
@login_required
def report(book_id):
    get_book(book_id)
    reason = request.form.get("reason", "").strip()[:300]
    if reason:
        get_db().execute("INSERT INTO reports(book_id,reporter_id,reason,created) VALUES(?,?,?,?)",
                         (book_id, g.user["id"], reason, now()))
        get_db().commit()
        flash("Thanks. An administrator will review this listing.", "ok")
    return redirect(url_for("book", book_id=book_id))


# ---------- my account and admin ----------
@app.get("/my")
@login_required
def my():
    db = get_db()
    books = db.execute("SELECT * FROM books WHERE user_id=? ORDER BY id DESC", (g.user["id"],)).fetchall()
    inbox = db.execute(
        "SELECT m.*, s.name AS sender, b.title FROM messages m JOIN users s ON s.id=m.sender_id "
        "JOIN books b ON b.id=m.book_id WHERE m.receiver_id=? ORDER BY m.id DESC LIMIT 30",
        (g.user["id"],)).fetchall()
    return render_template("my.html", books=books, inbox=inbox)


@app.get("/admin")
@login_required
def admin():
    if not g.user["is_admin"]:
        abort(403)
    reports = get_db().execute(
        "SELECT r.*, b.title, u.name AS reporter FROM reports r JOIN books b ON b.id=r.book_id "
        "JOIN users u ON u.id=r.reporter_id ORDER BY r.id DESC").fetchall()
    return render_template("admin.html", reports=reports)


@app.post("/report/<int:report_id>/dismiss")
@login_required
def dismiss(report_id):
    if not g.user["is_admin"]:
        abort(403)
    get_db().execute("DELETE FROM reports WHERE id=?", (report_id,))
    get_db().commit()
    return redirect(url_for("admin"))


@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(400)
def error(e):
    return render_template("error.html", e=e), e.code


init_db()

if __name__ == "__main__":
    app.run(debug=True)
