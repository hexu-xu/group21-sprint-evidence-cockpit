"""Real-browser smoke checks for newly implemented backlog journeys.

Run against a disposable, seeded SQLite database. The script creates a user
and a task note, and writes screenshots only after assertions pass.
"""

import json
import os
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("DEMO_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
PASSWORD = os.environ["DEMO_PASSWORD"]
OUT = Path(os.environ.get("BROWSER_EVIDENCE_DIR", ROOT / "instance" / "browser-evidence"))
OUT.mkdir(parents=True, exist_ok=True)
SHA = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def sign_in(page, username):
    page.goto(f"{BASE_URL}/auth/login")
    page.locator("#username").fill(username)
    page.locator("#password").fill(PASSWORD)
    page.get_by_role("button", name="登录工作台").click()
    page.wait_for_url("**/tasks")


with sync_playwright() as playwright:
    options = {"headless": True}
    if os.environ.get("PLAYWRIGHT_BROWSER_EXECUTABLE"):
        options["executable_path"] = os.environ["PLAYWRIGHT_BROWSER_EXECUTABLE"]
    browser = playwright.chromium.launch(**options)
    page = browser.new_page(viewport={"width": 1440, "height": 980})
    sign_in(page, "admin")
    assert page.goto(f"{BASE_URL}/admin/users").status == 200
    role_name = "验收角色-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    role_form = page.locator('form[action="/admin/roles"]')
    role_form.locator('[name="name"]').fill(role_name)
    role_form.locator('[name="platform_role"]').select_option("standard")
    role_form.locator('button[type="submit"]').click()
    assert role_name in page.content()
    user_name = "accept_" + datetime.now(timezone.utc).strftime("%H%M%S")
    user_form = page.locator('form[action="/admin/users"]')
    user_form.locator('[name="username"]').fill(user_name)
    user_form.locator('[name="password"]').fill(PASSWORD)
    user_form.locator('[name="role_id"]').select_option(label=role_name)
    user_form.locator('[name="project_id"]').select_option(index=0)
    user_form.locator('[name="project_role"]').select_option("member")
    user_form.locator('button[type="submit"]').click()
    assert user_name in page.content()
    page.screenshot(path=str(OUT / "新增角色与用户.png"), full_page=True)

    sign_in(page, "manager")
    assert page.goto(f"{BASE_URL}/tasks/new?project_id=1").status == 200
    page.locator("#module_name").fill("待办验收")
    page.locator("#title").fill("浏览器备注验收任务")
    page.locator("#description").fill("用于验证成员进展备注")
    page.locator("#priority").select_option("medium")
    page.locator("#due_date").fill((date.today() + timedelta(days=7)).isoformat())
    page.locator("#assignee_id").select_option(label="member")
    page.get_by_role("button", name="创建任务").click()
    page.wait_for_url("**/tasks/*")
    task_id = int(page.url.rsplit("/", 1)[-1])
    for path, expected in (("/admin/projects/1/members", user_name),
                           ("/tasks/attention?project_id=1", "待关注任务"),
                           ("/tasks/analytics?project_id=1", "统计分析"),
                           ("/tasks/trend?project_id=1", "项目进度趋势")):
        assert page.goto(BASE_URL + path).status == 200
        assert expected in page.content()
    page.screenshot(path=str(OUT / "项目进度趋势.png"), full_page=True)

    sign_in(page, "member")
    assert page.goto(f"{BASE_URL}/tasks/{task_id}").status == 200
    note = "浏览器验收备注-" + datetime.now(timezone.utc).strftime("%H%M%S")
    page.locator("#note_body").fill(note)
    page.get_by_role("button", name="保存备注").click()
    assert note in page.content()
    page.screenshot(path=str(OUT / "成员进展备注.png"), full_page=True)
    assert page.goto(f"{BASE_URL}/admin/users").status == 403
    browser.close()

(OUT / "待办故事浏览器验证.json").write_text(json.dumps({
    "candidate_sha": SHA,
    "run_time_utc": datetime.now(timezone.utc).isoformat(),
    "created_user": user_name,
    "role": role_name,
    "note": note,
    "task_id": task_id,
    "status": "passed against local candidate; not independent team review",
}, ensure_ascii=False, indent=2), encoding="utf-8")
print("BACKLOG_BROWSER_PASS", SHA, user_name)
