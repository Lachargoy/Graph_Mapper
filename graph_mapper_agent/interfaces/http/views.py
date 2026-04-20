from flask import Blueprint, render_template
from graph_mapper_agent.interfaces.http.services import load_profiles

views_bp = Blueprint("views", __name__)

@views_bp.get("/")
def index():
    profiles = load_profiles()
    return render_template("index.html", profiles=profiles)
