from pathlib import Path
import json
from flask import Flask, abort, render_template, request

from dod_gate import evaluate_dod
from permissions import ROLE_CONTENT, can_view_quality, normalize_role

BASE_DIR = Path(__file__).resolve().parent
EVIDENCE_PATH = BASE_DIR / "data" / "evidence.json"


def load_evidence():
    with EVIDENCE_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(TESTING=False)
    if test_config:
        app.config.update(test_config)

    @app.get("/")
    def index():
        role = normalize_role(request.args.get("role", "product"))
        evidence = load_evidence()
        return render_template(
            "index.html",
            role=role,
            role_content=ROLE_CONTENT[role],
            role_content_map=ROLE_CONTENT,
            evidence=evidence,
            dod=evaluate_dod(evidence),
        )

    @app.get("/quality")
    def quality_detail():
        role = normalize_role(request.args.get("role", "product"))
        if not can_view_quality(role):
            abort(403)
        evidence = load_evidence()
        return render_template(
            "index.html",
            role=role,
            role_content=ROLE_CONTENT[role],
            role_content_map=ROLE_CONTENT,
            evidence=evidence,
            dod=evaluate_dod(evidence),
            quality_detail=True,
        )

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("403.html"), 403

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
