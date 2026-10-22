"""Vercel entrypoint. No local writes are made when DATABASE_URL is configured."""
import os
from pathlib import Path
from app import create_app

app = create_app(
    study_dir=os.environ.get("STUDY_DIR", str(Path(__file__).resolve().parent / "study")),
    max_trials=int(os.environ.get("MAX_TRIALS", "24")),
    secure_cookie=os.environ.get("VERCEL") == "1",
)
