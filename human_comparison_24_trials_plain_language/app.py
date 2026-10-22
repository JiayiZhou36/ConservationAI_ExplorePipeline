"""Human evaluation: blinded removal vs black-mask / blur comparisons."""
import argparse
import hmac
import json
import os
import random
import secrets
import time
from datetime import datetime, timezone, timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, Response, abort, redirect, render_template, request, send_file, session, url_for
from analysis import SUMMARY_FIELDS, csv_text, summarize, summarize_ratings, summarize_individual_ratings
from database import Database
from scheduling import TOTAL_TRIALS, DESIGN_VERSION, build_schedule, validate_pairs

VOTES = {"left", "right", "tie", "cannot_judge"}
RATING_VOTES = {"rating_1", "rating_2", "rating_3", "rating_4", "rating_5", "rating_cannot_judge"}
RESPONSE_FIELDS = ["study_id", "participant_id", "participant_complete", "pair_id", "source_id", "animal",
                   "baseline", "trial_index", "left_method", "right_method", "left_asset", "right_asset",
                   "realism_choice", "realism_winner", "preference_choice", "preference_winner",
                   "reference_asset", "questions_version", "design_version", "shown_at", "submitted_at", "elapsed_seconds", "comment"]


RESPONSE_FIELDS += ["second_question_type", "selected_image_rating", "rated_image", "rated_method", "image_a_rating", "image_b_rating", "image_a_rating_answer", "image_b_rating_answer", "image_a_method", "image_b_method", "response_status", "final_submitted_at", "submission_type", "workflow_version"]

def utcnow():
    return datetime.now(timezone.utc).isoformat()


def create_app(study_dir="study", admin_password=None, max_trials=TOTAL_TRIALS, secure_cookie=False):
    root = Path(study_dir).resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if not manifest["pairs"]:
        raise ValueError("Study has no image pairs")
    password = admin_password or os.environ.get("STUDY_ADMIN_PASSWORD", "")
    if len(password) < 16:
        raise ValueError("Set STUDY_ADMIN_PASSWORD to a private password of at least 16 characters")
    if max_trials != TOTAL_TRIALS:
        raise ValueError("This version requires exactly 24 trials. Set MAX_TRIALS=24 or remove the old setting.")
    is_vercel = os.environ.get("VERCEL") == "1"
    database_url = os.environ.get("DATABASE_URL")
    secret_key = os.environ.get("SECRET_KEY")
    if is_vercel and (not database_url or not secret_key):
        raise ValueError("Vercel requires DATABASE_URL and SECRET_KEY environment variables")
    if not secret_key:
        secret_key = (root / "session.key").read_text().strip()
    if len(secret_key) < 32:
        raise ValueError("SECRET_KEY must contain at least 32 characters")
    app = Flask(__name__, static_folder=None)
    app.config.update(SECRET_KEY=secret_key,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      SESSION_COOKIE_SECURE=secure_cookie, PERMANENT_SESSION_LIFETIME=timedelta(days=30),
                      MAX_CONTENT_LENGTH=16_384, STUDY_DIR=str(root))
    database = Database(root / "responses.sqlite3", database_url)
    db = database.connect
    validate_pairs(manifest["pairs"])
    pairs = {pair["pair_id"]: pair for pair in manifest["pairs"]}
    if manifest.get("design_version") != DESIGN_VERSION:
        raise ValueError("Prepare a NEW study with this 24-trial version of prepare_study.py")
    if manifest.get("questions_version") != "reference-realism-and-overall-v4":
        raise ValueError("Prepare a NEW reference-enabled study with the updated prepare_study.py")

    with db() as connection:
        if not database.postgres:
            connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS participants (
                id TEXT PRIMARY KEY, schedule TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS exposures (
                participant_id TEXT NOT NULL REFERENCES participants(id), trial_index INTEGER NOT NULL,
                shown_at TEXT NOT NULL, shown_epoch DOUBLE PRECISION NOT NULL,
                PRIMARY KEY (participant_id, trial_index));
            CREATE TABLE IF NOT EXISTS responses (
                participant_id TEXT NOT NULL REFERENCES participants(id), trial_index INTEGER NOT NULL,
                realism_choice TEXT NOT NULL, preference_choice TEXT NOT NULL,
                submitted_at TEXT NOT NULL, elapsed_seconds DOUBLE PRECISION NOT NULL, comment TEXT NOT NULL,
                PRIMARY KEY (participant_id, trial_index));
        ''')
        # Additive table: existing responses and old questionnaires remain intact.
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS individual_ratings (
                participant_id TEXT NOT NULL, trial_index INTEGER NOT NULL,
                left_rating TEXT NOT NULL, right_rating TEXT NOT NULL,
                PRIMARY KEY (participant_id, trial_index),
                FOREIGN KEY (participant_id, trial_index)
                    REFERENCES responses(participant_id, trial_index));
        ''')
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS study_submissions (
                participant_id TEXT PRIMARY KEY REFERENCES participants(id),
                final_submitted_at TEXT NOT NULL, submission_type TEXT NOT NULL);
        ''')
        connection.execute("INSERT INTO metadata VALUES ('study_id', ?) ON CONFLICT DO NOTHING", (manifest["study_id"],))
        old = connection.execute("SELECT value FROM metadata WHERE key='study_id'").fetchone()
        if old and old["value"] != manifest["study_id"]:
            raise ValueError("Manifest differs from this database. Create a new study folder.")
        design = connection.execute("SELECT value FROM metadata WHERE key='design_version'").fetchone()
        if design is None:
            prior = connection.execute("SELECT COUNT(*) AS n FROM participants").fetchone()
            if prior["n"]:
                raise ValueError("This database has sessions from an earlier design. Use a fresh study folder/database for the 24-trial study.")
            connection.execute("INSERT INTO metadata VALUES ('design_version', ?) ON CONFLICT DO NOTHING", (DESIGN_VERSION,))
            design = connection.execute("SELECT value FROM metadata WHERE key='design_version'").fetchone()
        if design["value"] != DESIGN_VERSION:
            raise ValueError("Database study design differs. Use a fresh study folder/database.")
        # Claim this migration once, so later deployments cannot auto-finalize drafts.
        claimed = connection.execute(
            "INSERT INTO metadata VALUES ('review_submit_workflow', 'v1') ON CONFLICT DO NOTHING RETURNING key"
        ).fetchone()
        if claimed:
            for participant in connection.execute("SELECT id, schedule FROM participants").fetchall():
                count = connection.execute("SELECT COUNT(*) AS n FROM responses WHERE participant_id=?", (participant["id"],)).fetchone()["n"]
                if count == len(json.loads(participant["schedule"])):
                    connection.execute("INSERT INTO study_submissions VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
                                       (participant["id"], utcnow(), "legacy_completed_before_review_workflow"))


    def csrf():
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(24)
        return session["csrf"]

    app.jinja_env.globals["csrf"] = csrf

    @app.before_request
    def protect_posts():
        if request.method == "POST":
            supplied = request.form.get("csrf", "")
            expected = session.get("csrf", "")
            if not supplied or not expected or not hmac.compare_digest(supplied, expected):
                abort(400, "Invalid form session; reload the page and try again.")

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; img-src 'self'; form-action 'self'; frame-ancestors 'none'"
        return response

    def progress():
        pid = session.get("participant_id")
        if not pid:
            return None, [], 0
        with db() as connection:
            participant = connection.execute("SELECT * FROM participants WHERE id=?", (pid,)).fetchone()
            if not participant:
                return None, [], 0
            completed = {row["trial_index"] for row in connection.execute("SELECT trial_index FROM responses WHERE participant_id=?", (pid,))}
        schedule = json.loads(participant["schedule"])
        current = next((i for i in range(len(schedule)) if i not in completed), len(schedule))
        return pid, schedule, current

    def submission(pid, connection=None):
        if connection is not None:
            return connection.execute("SELECT * FROM study_submissions WHERE participant_id=?", (pid,)).fetchone()
        with db() as connection:
            return submission(pid, connection)

    def lock_participant(connection, pid):
        # Both saving and final submission take the same lock. A concurrent save
        # cannot change answers after final submission commits.
        if database.postgres:
            connection.execute("SELECT id FROM participants WHERE id=? FOR UPDATE", (pid,)).fetchone()
        else:
            connection.execute("BEGIN IMMEDIATE")

    @app.get("/assets/<name>")
    def assets(name):
        if name not in {"style.css", "study.js"}:
            abort(404)
        return send_file(Path(__file__).resolve().parent / "public" / "assets" / name)

    @app.get("/")
    def home():
        if progress()[0]:
            return redirect(url_for("trial"))
        return render_template("start.html", estimated_trials=TOTAL_TRIALS)

    @app.post("/start")
    def start():
        if progress()[0]:
            return redirect(url_for("trial"))
        if request.form.get("agree") != "yes":
            abort(400, "Please confirm that you want to participate.")
        rng = random.Random(secrets.randbits(128))
        schedule = build_schedule(list(pairs.values()), rng)
        pid = secrets.token_hex(16)
        with db() as connection:
            connection.execute("INSERT INTO participants VALUES (?, ?, ?)", (pid, json.dumps(schedule), utcnow()))
        session["participant_id"] = pid
        session.permanent = True
        return redirect(url_for("trial"))

    @app.get("/trial")
    def trial():
        pid, schedule, current = progress()
        if not pid:
            return redirect(url_for("home"))
        if submission(pid):
            return render_template("done.html")
        try:
            index = int(request.args.get("index", current))
        except (ValueError, TypeError):
            abort(400, "Invalid comparison number.")
        if index == len(schedule):
            return redirect(url_for("review"))
        if not 0 <= index < len(schedule):
            abort(404)
        with db() as connection:
            connection.execute("INSERT INTO exposures VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING", (pid, index, utcnow(), time.time()))
            saved = connection.execute("SELECT * FROM responses WHERE participant_id=? AND trial_index=?", (pid, index)).fetchone()
            ratings = connection.execute("SELECT * FROM individual_ratings WHERE participant_id=? AND trial_index=?", (pid, index)).fetchone()
            answered = connection.execute("SELECT COUNT(*) AS n FROM responses WHERE participant_id=?", (pid,)).fetchone()["n"]
        answers = dict(saved) if saved else {}
        if ratings:
            answers.update(dict(ratings))
        return render_template("trial.html", index=index, total=len(schedule), answers=answers, answered=answered)

    @app.get("/review")
    def review():
        pid, schedule, current = progress()
        if not pid:
            return redirect(url_for("home"))
        if submission(pid):
            return render_template("done.html")
        with db() as connection:
            records = {r["trial_index"]: dict(r) for r in connection.execute("SELECT * FROM responses WHERE participant_id=?", (pid,))}
            ratings = {r["trial_index"]: dict(r) for r in connection.execute("SELECT * FROM individual_ratings WHERE participant_id=?", (pid,))}
        items = []
        for index, item in enumerate(schedule):
            saved = records.get(index)
            rating = ratings.get(index, {})
            items.append(dict(index=index, animal=pairs[item["pair_id"]]["animal"], saved=bool(saved),
                              a=rating.get("left_rating"), b=rating.get("right_rating"),
                              choice=saved["realism_choice"] if saved else None))
        return render_template("review.html", items=items, answered=len(records), total=len(schedule), ready=len(records)==len(schedule))

    @app.post("/submit-study")
    def submit_study():
        pid, schedule, current = progress()
        if not pid:
            abort(400, "Start the study first.")
        if request.form.get("confirm_final") != "yes":
            abort(400, "Confirm that you are ready to submit your final answers.")
        with db() as connection:
            lock_participant(connection, pid)
            if not submission(pid, connection):
                completed = {r["trial_index"] for r in connection.execute("SELECT trial_index FROM responses WHERE participant_id=?", (pid,))}
                if completed != set(range(len(schedule))):
                    abort(400, "Answer all comparisons before submitting the study.")
                connection.execute("INSERT INTO study_submissions VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
                                   (pid, utcnow(), "participant_final_submit"))
        return redirect(url_for("trial"))

    @app.get("/image/<int:index>/<side>")
    def image(index, side):
        pid, schedule, current = progress()
        if not pid or not 0 <= index < len(schedule) or submission(pid) or side not in {"left", "right", "reference"}:
            abort(404)
        item = schedule[index]
        pair = pairs[item["pair_id"]]
        method = "original" if side == "reference" else item[side + "_method"]
        asset = pair["assets"][method]
        # The browser sees only /image/0/left, not method names or source paths.
        return send_file(root / "images" / f"{asset}.png", mimetype="image/png", download_name=f"image_{side}.png")

    @app.post("/answer")
    def answer():
        pid, schedule, current = progress()
        if not pid:
            abort(400, "Start the study first.")
        try:
            index = int(request.form.get("trial_index", ""))
        except ValueError:
            abort(400)
        if submission(pid):
            abort(403, "Your study has been submitted. Answers can no longer be changed.")
        if not 0 <= index < len(schedule):
            abort(400, "Invalid comparison number.")
        navigation = request.form.get("navigate", "next")
        if navigation not in {"previous", "next", "review"}:
            abort(400)
        # Previous can leave a new unanswered page. Complete answers are saved.
        if navigation == "previous" and request.form.get("questionnaire_version") == "individual-realism-three-v1":
            complete = (request.form.get("realism") in VOTES and
                        request.form.get("left_rating") in RATING_VOTES and
                        request.form.get("right_rating") in RATING_VOTES)
            if not complete:
                return redirect(url_for("trial", index=max(0, index-1)))
        form_version = request.form.get("questionnaire_version")
        left_rating = right_rating = None
        if form_version == "individual-realism-three-v1":
            realism = request.form.get("realism")
            left_rating = request.form.get("left_rating")
            right_rating = request.form.get("right_rating")
            if realism not in VOTES or left_rating not in RATING_VOTES or right_rating not in RATING_VOTES:
                abort(400, "Answer all three questions using the supplied options.")
            # Retained legacy column; new Q1/Q2 ratings live in individual_ratings.
            preference = "cannot_judge"
        elif form_version:
            abort(400, "Unknown questionnaire version; reload the page.")
        else:
            # Support a cached older page submitted across deployment.
            realism = request.form.get("realism")
            preference = request.form.get("preference")
            if realism not in VOTES or preference not in (VOTES | RATING_VOTES):
                abort(400, "Answer both questions using the supplied options.")
            if realism == "cannot_judge" and preference in RATING_VOTES and preference != "rating_cannot_judge":
                abort(400, "Select Cannot judge for the rating as well.")
        comment = request.form.get("comment", "").strip()
        if len(comment) > 1000:
            abort(400, "Comment is too long.")
        with db() as connection:
            lock_participant(connection, pid)
            if submission(pid, connection):
                abort(403, "Your study has been submitted. Answers can no longer be changed.")
            exposure = connection.execute("SELECT * FROM exposures WHERE participant_id=? AND trial_index=?", (pid, index)).fetchone()
            if not exposure:
                abort(400, "Open the trial before submitting.")
            connection.execute("""INSERT INTO responses VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (participant_id, trial_index) DO UPDATE SET
                realism_choice=excluded.realism_choice, preference_choice=excluded.preference_choice,
                submitted_at=excluded.submitted_at, elapsed_seconds=excluded.elapsed_seconds,
                comment=excluded.comment""",
                (pid, index, realism, preference, utcnow(), max(0.0, time.time()-exposure["shown_epoch"]), comment))
            if form_version == "individual-realism-three-v1":
                connection.execute(
                    """INSERT INTO individual_ratings VALUES (?, ?, ?, ?)
                    ON CONFLICT (participant_id, trial_index) DO UPDATE SET
                    left_rating=excluded.left_rating, right_rating=excluded.right_rating""",
                    (pid, index, left_rating, right_rating))
            else:
                connection.execute("DELETE FROM individual_ratings WHERE participant_id=? AND trial_index=?", (pid, index))
        if navigation == "review" or (navigation == "next" and index == len(schedule)-1):
            return redirect(url_for("review"))
        return redirect(url_for("trial", index=max(0, index-1) if navigation == "previous" else index+1))

    def admin_required(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            if session.get("admin_until", 0) < time.time():
                return redirect(url_for("admin_login"))
            return function(*args, **kwargs)
        return wrapped

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if request.method == "POST":
            if not hmac.compare_digest(request.form.get("password", "").encode(), password.encode()):
                return render_template("login.html", error="Incorrect password."), 403
            session["admin_until"] = time.time()+8*3600
            return redirect(url_for("admin"))
        return render_template("login.html")

    @app.post("/admin/logout")
    def logout():
        session.pop("admin_until", None)
        return redirect(url_for("admin_login"))

    def response_rows():
        with db() as connection:
            participants = [dict(p) for p in connection.execute("SELECT * FROM participants").fetchall()]
            submissions = {r["participant_id"]: dict(r) for r in connection.execute("SELECT * FROM study_submissions").fetchall()}
            for participant in participants:
                participant.update(submissions.get(participant["id"], {}))
            records = connection.execute("SELECT r.*, e.shown_at FROM responses r JOIN exposures e USING(participant_id, trial_index) ORDER BY r.submitted_at").fetchall()
            rating_records = connection.execute("SELECT * FROM individual_ratings").fetchall()
        rating_lookup = {(r["participant_id"], r["trial_index"]): dict(r) for r in rating_records}
        schedules = {p["id"]: json.loads(p["schedule"]) for p in participants}
        counts = {}
        for record in records:
            counts[record["participant_id"]] = counts.get(record["participant_id"], 0)+1
        rows = []
        for record in records:
            row = dict(record)
            pid, index = row["participant_id"], row["trial_index"]
            item = schedules[pid][index]
            pair = pairs[item["pair_id"]]
            row.update(study_id=manifest["study_id"], participant_complete=pid in submissions,
                       response_status="submitted" if pid in submissions else "draft",
                       final_submitted_at=submissions.get(pid, {}).get("final_submitted_at", ""),
                       submission_type=submissions.get(pid, {}).get("submission_type", ""),
                       workflow_version="review-submit-v1",
                       pair_id=pair["pair_id"], source_id=pair["source_id"], animal=pair["animal"],
                       baseline=pair["baseline"], left_method=item["left_method"], right_method=item["right_method"],
                       left_asset=pair["assets"][item["left_method"]], right_asset=pair["assets"][item["right_method"]],
                       reference_asset=pair["assets"]["original"], questions_version=manifest["questions_version"], design_version=DESIGN_VERSION)
            row.update(image_a_method=item["left_method"], image_b_method=item["right_method"],
                       image_a_rating="", image_b_rating="", image_a_rating_answer="", image_b_rating_answer="")
            individual = rating_lookup.get((pid, index))
            if individual:
                row["questions_version"] = "individual-realism-three-v1"
                row["second_question_type"] = "individual_image_ratings"
                row["selected_image_rating"] = ""
                row["rated_image"] = ""
                row["rated_method"] = ""
                row["preference_winner"] = ""
                row["preference_choice"] = ""  # Not a legacy preference answer.
                choice = row["realism_choice"]
                row["realism_winner"] = item[choice + "_method"] if choice in {"left", "right"} else choice
                for side, letter in (("left", "a"), ("right", "b")):
                    answer = individual[side + "_rating"]
                    row["image_" + letter + "_rating_answer"] = answer
                    row["image_" + letter + "_rating"] = int(answer.rsplit("_", 1)[1]) if answer != "rating_cannot_judge" else ""
            else:
                choice = row["realism_choice"]
                row["realism_winner"] = item[choice + "_method"] if choice in {"left", "right"} else choice
                second = row["preference_choice"]
                if second in RATING_VOTES:
                    row["second_question_type"] = "selected_image_realism_rating_v1"
                    row["questions_version"] = "reference-selected-realism-rating-v1"
                    row["selected_image_rating"] = int(second.rsplit("_", 1)[1]) if second != "rating_cannot_judge" else ""
                    row["rated_image"] = {"left": "A", "right": "B", "tie": "both_equal", "cannot_judge": "cannot_judge"}[choice]
                    row["rated_method"] = item[choice + "_method"] if choice in {"left", "right"} else "both_equal" if choice == "tie" else "cannot_judge"
                    row["preference_winner"] = ""
                else:
                    row["second_question_type"] = "overall_preference"
                    row["selected_image_rating"] = ""
                    row["rated_image"] = ""
                    row["rated_method"] = ""
                    row["preference_winner"] = item[second + "_method"] if second in {"left", "right"} else second
            rows.append(row)
        return rows, participants

    @app.get("/admin")
    @admin_required
    def admin():
        rows, participants = response_rows()
        complete_only = request.args.get("complete", "1") == "1"
        selected = [r for r in rows if r["participant_complete"]] if complete_only else rows
        completed = len({r["participant_id"] for r in rows if r["participant_complete"]})
        return render_template("admin.html", summaries=summarize(selected), rating_summaries=summarize_ratings(selected), individual_summaries=summarize_individual_ratings(selected), complete_only=complete_only,
                               started=len(participants), completed=completed, judgments=len(selected))

    @app.get("/admin/export/<kind>")
    @admin_required
    def export(kind):
        rows, participants = response_rows()
        if kind != "participants" and request.args.get("complete", "1") == "1":
            rows = [r for r in rows if r["participant_complete"]]
        if kind == "responses":
            fields, data = RESPONSE_FIELDS, rows
        elif kind == "summary":
            fields, data = SUMMARY_FIELDS, summarize(rows) + summarize_individual_ratings(rows) + summarize_ratings(rows)
        elif kind == "participants":
            fields = ["participant_id", "created_at", "assigned_trials", "answered_trials", "complete", "response_status", "final_submitted_at", "submission_type"]
            data = []
            for participant in participants:
                count = sum(r["participant_id"] == participant["id"] for r in rows)
                total = len(json.loads(participant["schedule"]))
                data.append(dict(participant_id=participant["id"], created_at=participant["created_at"],
                                 assigned_trials=total, answered_trials=count, complete=bool(participant.get("final_submitted_at")),
                                 response_status="submitted" if participant.get("final_submitted_at") else "draft",
                                 final_submitted_at=participant.get("final_submitted_at", ""), submission_type=participant.get("submission_type", "")))
        else:
            abort(404)
        # Neutralize spreadsheet formulas in free text fields without changing DB contents.
        safe = []
        for row in data:
            safe.append({key: "'"+value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value
                         for key, value in row.items()})
        return Response(csv_text(safe, fields), mimetype="text/csv", headers={"Content-Disposition": f'attachment; filename="{kind}.csv"'})

    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", default="study")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--max-trials", type=int, choices=[TOTAL_TRIALS], default=TOTAL_TRIALS, help="Fixed at 24 for this balanced study")
    parser.add_argument("--https", action="store_true", help="Require secure cookies; use behind HTTPS")
    args = parser.parse_args()
    from waitress import serve
    serve(create_app(args.study, max_trials=args.max_trials, secure_cookie=args.https),
          host=args.host, port=args.port, threads=8)
