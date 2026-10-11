"""Historical delivery records kept for permission and gate regression."""

import json
from pathlib import Path

from flask import abort, current_app, render_template
from flask_login import current_user, login_required

from dod_gate import build_evidence_chain, evaluate_dod
from permissions import ROLE_CONTENT

from . import bp


def load_evidence(path=None, inline=None):
    """Read historical delivery evidence without modifying it."""
    if inline is not None:
        return inline
    with Path(path or current_app.config["EVIDENCE_PATH"]).open(encoding="utf-8") as handle:
        return json.load(handle)


def render_cockpit(quality_detail=False):
    role = current_user.evidence_role
    evidence = load_evidence(current_app.config["EVIDENCE_PATH"], current_app.config.get("EVIDENCE_DATA"))
    dod = evaluate_dod(evidence)
    return render_template(
        "index.html", role=role, role_content=ROLE_CONTENT[role], evidence=evidence,
        dod=dod, chain=build_evidence_chain(evidence, dod), quality_detail=quality_detail,
    )


@bp.get("/evidence")
@login_required
def index():
    return render_cockpit()


@bp.get("/quality")
@login_required
def quality_detail():
    # Query parameters cannot grant the quality role.
    if current_user.evidence_role != "quality":
        abort(403)
    return render_cockpit(quality_detail=True)
