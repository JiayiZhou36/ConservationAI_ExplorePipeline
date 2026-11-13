"""Flask-compatible Vercel entrypoint; same WSGI application as the local server."""
from flask import Flask
from app import StudyApp
app=Flask(__name__)
app.wsgi_app=StudyApp()
