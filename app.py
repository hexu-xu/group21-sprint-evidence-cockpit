"""Sprint可信交付舱：按岗位隔离交付内容，并用真实证据计算DoD状态。"""

from pathlib import Path
import json

from flask import Flask, abort, render_template, request

from dod_gate import build_evidence_chain, evaluate_dod
from permissions import ROLE_CONTENT, can_view_quality, normalize_role

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_EVIDENCE_PATH = BASE_DIR / "data" / "evidence.json"


def load_evidence(path=None, inline=None):
    """读取顶层证据数据。

    证据文件只保存真实产生的事实（故事、任务、分支、提交、测试、审查）；
    页面状态全部由这些数据分析得出，不在文件里写死绿色或红色。
    传入 ``inline`` 时直接使用该数据，便于测试在不改动真实证据文件、
    也不依赖临时目录的情况下验证红色和绿色两种状态。
    """
    if inline is not None:
        return inline
    evidence_path = Path(path) if path else DEFAULT_EVIDENCE_PATH
    with evidence_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _render_cockpit(role, evidence, quality_detail=False):
    """统一渲染入口：岗位内容 + 证据门禁结论 + 八段证据链。"""
    dod = evaluate_dod(evidence)
    return render_template(
        "index.html",
        role=role,
        role_content=ROLE_CONTENT[role],
        evidence=evidence,
        dod=dod,
        chain=build_evidence_chain(evidence, dod),
        quality_detail=quality_detail,
    )


def create_app(test_config=None):
    """创建Flask应用。

    证据来源可配置：``EVIDENCE_PATH`` 指定证据文件路径（默认真实证据文件），
    ``EVIDENCE_DATA`` 可直接注入内存证据，供测试验证红色与绿色状态。
    """
    app = Flask(__name__)
    app.config.update(
        TESTING=False, EVIDENCE_PATH=str(DEFAULT_EVIDENCE_PATH), EVIDENCE_DATA=None
    )
    if test_config:
        app.config.update(test_config)

    def current_evidence():
        """读取当前生效的证据数据，避免每个路由重复取值逻辑。"""
        return load_evidence(app.config["EVIDENCE_PATH"], app.config.get("EVIDENCE_DATA"))

    @app.get("/")
    def index():
        """首页：按岗位返回职责范围内的内容，并显示当前DoD状态。"""
        role = normalize_role(request.args.get("role", "product"))
        return _render_cockpit(role, current_evidence())

    @app.get("/quality")
    def quality_detail():
        """完整质量详情：只有quality/DRI可以访问，其余岗位由服务端返回403。"""
        role = normalize_role(request.args.get("role", "product"))
        if not can_view_quality(role):
            # 服务端强制校验，而不是仅在页面隐藏入口。
            abort(403)
        return _render_cockpit(role, current_evidence(), quality_detail=True)

    @app.errorhandler(403)
    def forbidden(_error):
        """统一的403页面，隐藏具体授权细节。"""
        return render_template("403.html"), 403

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
