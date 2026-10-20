"""Exercise a real browser journey against a running, seeded demo instance.

This optional check creates two demo tasks. Use a disposable demo database.
"""

import json
import os
import re
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("DEMO_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
PROJECT_ID = int(os.environ.get("DEMO_PROJECT_ID", "1"))
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


def metric(html, label):
    match = re.search(rf"{re.escape(label)}</span><strong>(\d+)</strong>", html)
    assert match, f"missing metric: {label}"
    return int(match.group(1))


with sync_playwright() as playwright:
    executable = os.environ.get("PLAYWRIGHT_BROWSER_EXECUTABLE")
    launch_options = {"headless": True}
    if executable:
        launch_options["executable_path"] = executable
    browser = playwright.chromium.launch(**launch_options)
    page = browser.new_page(viewport={"width": 1440, "height": 980})
    sign_in(page, "manager")
    before = page.goto(f"{BASE_URL}/tasks/overview?project_id={PROJECT_ID}")
    assert before.status == 200
    old_total = metric(page.content(), "任务总数")
    old_done = metric(page.content(), "已完成")

    unique = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    titles = (f"浏览器主流程-{unique}", f"浏览器权限流程-{unique}")
    task_ids = []
    for title, assignee in zip(titles, ("member", "member2")):
        page.goto(f"{BASE_URL}/tasks/new?project_id={PROJECT_ID}")
        page.locator("#module_name").fill("浏览器验证")
        page.locator("#title").fill(title)
        page.locator("#description").fill("一次性演示数据，可在验证后删除")
        page.locator("#priority").select_option("medium")
        page.locator("#due_date").fill((date.today() + timedelta(days=7)).isoformat())
        page.locator("#assignee_id").select_option(label=assignee)
        page.get_by_role("button", name="创建任务").click()
        page.wait_for_url("**/tasks/*")
        task_ids.append(int(page.url.rsplit("/", 1)[-1]))

    sign_in(page, "member")
    assert page.goto(f"{BASE_URL}/tasks?project_id={PROJECT_ID}").status == 200
    assert titles[0] in page.content() and titles[1] not in page.content()
    page.goto(f"{BASE_URL}/tasks/{task_ids[0]}")
    page.locator("#status").select_option("done")
    page.get_by_role("button", name="保存状态").click()
    assert page.goto(f"{BASE_URL}/tasks/overview?project_id={PROJECT_ID}").status == 403
    page.screenshot(path=str(OUT / "成员访问项目概览403.png"), full_page=True)

    sign_in(page, "manager")
    assert page.goto(f"{BASE_URL}/tasks/overview?project_id={PROJECT_ID}").status == 200
    assert metric(page.content(), "任务总数") == old_total + 2
    assert metric(page.content(), "已完成") == old_done + 1
    page.screenshot(path=str(OUT / "项目概览.png"), full_page=True)
    browser.close()

(OUT / "浏览器验证结果.json").write_text(json.dumps({
    "candidate_sha": SHA,
    "run_time_utc": datetime.now(timezone.utc).isoformat(),
    "base_url": BASE_URL,
    "project_id": PROJECT_ID,
    "created_task_ids": task_ids,
    "main_journey": "manager created two tasks, member updated own task, manager overview reflected the change",
    "permission_journey": "member could not see another member task and received HTTP 403 for project overview",
    "status": "passed against local candidate; not a team release approval",
}, ensure_ascii=False, indent=2), encoding="utf-8")
print("BROWSER_JOURNEYS_PASS", SHA, task_ids)
