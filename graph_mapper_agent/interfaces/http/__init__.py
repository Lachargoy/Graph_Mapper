from flask import Flask
from pathlib import Path

def create_app():
    templates_dir = Path(__file__).parent / "templates"
    app = Flask(__name__, template_folder=str(templates_dir))

    # Use absolute imports here to avoid duplicate module loading.
    from graph_mapper_agent.interfaces.http.api import api_bp
    from graph_mapper_agent.interfaces.http.views import views_bp

    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    return app
