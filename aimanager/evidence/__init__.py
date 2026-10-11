from flask import Blueprint

bp = Blueprint("evidence", __name__)

from . import routes  # noqa: E402,F401
