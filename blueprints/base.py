from flask import Flask, render_template, redirect, url_for, request, Blueprint
from flask_login import login_required
from utils.database import get_db_connection

base_blueprint = Blueprint('base', __name__, template_folder='templates')

# WEBSITE BASE
@base_blueprint.route("/")
def home():
    return redirect(url_for('auth.login'))

@base_blueprint.route("/index")
@login_required
def index():
    sort_by = request.args.get("sort_by", "title")  # Default sort by title
    sort_order = request.args.get("sort_order", "asc")  # Default ascending order

    valid_columns = {"title", "author", "publish_year", "created_at"}  # Add columns you want to sort by
    valid_orders = {"asc", "desc"}

    if sort_by not in valid_columns:
        sort_by = "title"
    if sort_order not in valid_orders:
        sort_order = "asc"

    conn = get_db_connection()
    query = f"SELECT * FROM books ORDER BY {sort_by} {sort_order}"
    books = conn.execute(query).fetchall()
    conn.close()

    return render_template("index.html", books=books, sort_by=sort_by, sort_order=sort_order)