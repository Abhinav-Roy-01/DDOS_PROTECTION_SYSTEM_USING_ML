"""Admin dashboard page."""

from flask import Blueprint, render_template

dashboard_bp = Blueprint(
    "dashboard",
    __name__,
    template_folder="TEMPLATES",
    static_folder="STATIC",
    static_url_path="/static/dashboard",
)


@dashboard_bp.get("/dashboard")
def dashboard():
    """Render the dashboard shell; API data remains admin-key protected."""
    return render_template("dashboard/index.html")
