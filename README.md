# 爱管理

爱管理是一个面向团队的项目任务协作系统。当前 Sprint 3 待发布代码提供可运行的任务闭环：项目经理创建任务，填写所属模块、描述、优先级和截止日期，分配项目成员；成员登录后查看自己的任务并更新状态；项目经理在任务看板中查看团队任务，并在“项目概览”核对总数、完成数、状态分布、截止日期提示以及人工记录的故事进度基线与实际值。管理员和项目经理可在任务详情中确认删除任务。只读管理员可查看项目概览，不能修改任务。

这是一版持续扩展中的产品。项目及成员由初始化命令创建；项目创建、成员管理、任务备注、复杂筛选和历史进度趋势等功能尚未开放。项目概览的任务级“进度提示”由任务状态和截止日期计算；另有独立的故事进度检查点供项目经理登记计划累计数、实际累计数及证据。故事数不会从任务看板自动推算。界面只展示已经实现的操作，不放课程或开发过程内容。最终发布范围须由团队根据质量证据人工确认。

## 技术结构

- Flask 应用工厂与按业务拆分的 Blueprint
- Flask-Login 管理登录会话，Werkzeug 保存密码哈希
- Flask-SQLAlchemy + Flask-Migrate 管理 SQLite 数据和迁移
- Flask-WTF 提供表单 CSRF 防护
- Jinja 模板与原生 CSS，无外部前端构建步骤
- pytest 覆盖登录、权限、任务闭环和历史交付门禁

## 本地启动

需要 Python 3.10 或更新版本。以下命令在 PowerShell 中执行：

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:DEMO_PASSWORD = "请换成自己设置的至少8位密码"
python -m flask --app app db upgrade
python -m flask --app app seed-demo
python app.py
```

浏览器打开 <http://127.0.0.1:5000/auth/login>。SQLite 文件位于 `instance/aimanager.db`，已被 Git 忽略。`seed-demo` 可以重复执行，不会清除已有任务，也不会重置已有账号密码。本地首次启动会在已忽略的 `instance/.secret_key` 生成会话密钥，后续重启沿用；部署时可通过 `SECRET_KEY` 环境变量明确指定。可通过 `DATABASE_URL` 指定其他数据库，本版只验证过 SQLite。

| 演示账号 | 权限 |
|---|---|
| `admin` | 平台管理员，可查看、维护及删除任务 |
| `manager` | 项目经理，可创建、分配、查看及删除项目任务 |
| `member`、`member2` | 项目成员，只能查看和更新自己的任务 |
| `observer` | 只读管理员，可查看任务，不能写入 |

这些账号是本地预设身份；账号注册和用户管理尚未实现。密码由本机 `DEMO_PASSWORD` 环境变量指定，不写进仓库。`requirements.txt` 和可选的 `requirements-browser.txt` 均使用 `constraints.txt` 中的精确版本约束；CI 也通过 `requirements.txt` 安装同一组核心依赖。调整依赖版本时应更新约束文件并重新运行全量测试。

## 操作流程

1. 以 `manager` 登录，打开“新建任务”，填写所属模块、任务标题、描述、优先级、截止日期和负责人。
2. 保存后，在任务故事地图中切换“待完成／进行中／已完成”，按模块查看任务卡片及负责人。
3. 以被分配的 `member` 登录，在“我的任务”中打开任务并更新状态。
4. 再以 `manager` 登录，确认故事地图和任务清单中的状态同步变化；完成任务会显示实际完成时间。
5. 打开“项目概览”，核对任务总数、已完成数、进行中数、待完成数、状态占比及逾期提示；再改变一项任务状态，确认任务统计同步更新。项目经理可另行录入故事进度检查点的计划累计数；到期后依据验收证据填写实际累计数，页面显示两者差额。
6. 以 `member2` 登录，确认看不到别人的任务，也无法打开项目整体概览；以 `observer` 登录，确认可以看概览但无法创建或修改任务。
7. 以 `manager` 或 `admin` 打开任务详情，通过“删除此任务”进入确认页；确认后任务及状态记录会被删除。成员和只读管理员无权打开确认页或提交删除请求。

已有账号登录时，可点击左下角“切换账号”，在登录页输入另一账号和密码；页面会显示当前登录身份，切换成功后按新身份加载工作台。

任务列表在数据库查询时按身份过滤。普通成员看板上的数字只统计“分配给我的任务”；项目概览只向项目经理、平台管理员和只读管理员开放，并且只统计选中项目。负责人必须是当前项目的有效成员；任务状态变化同时记录在状态历史中。只读限制和质量详情权限均在服务端判断，修改 URL 参数无法提升权限。

## 测试

```powershell
python -m pytest tests -q -p no:cacheprovider
```

测试使用独立内存数据库，不修改本地演示数据。数据库结构从空库执行 `flask db upgrade` 初始化。

GitHub Actions 配置位于 `.github/workflows/tests.yml`，在推送或拉取请求时运行同一测试命令。工作流是否在线通过，以实际 GitHub 运行记录为准；本地测试通过不等于 CI 已通过。

如需用真实浏览器核对主流程和权限异常流程，在**一次性演示数据库**上启动应用后执行：

```powershell
python -m pip install -r requirements-browser.txt
python -m playwright install chromium
python tests/browser_journeys.py
```

脚本会创建两项演示任务，结果和截图写入已忽略的 `instance/browser-evidence/`。默认访问 `http://127.0.0.1:5000`、项目 ID 1；可通过 `DEMO_BASE_URL`、`DEMO_PROJECT_ID` 调整。`DEMO_PASSWORD` 必须与初始化演示账号时一致。如使用系统已安装的浏览器，可用 `PLAYWRIGHT_BROWSER_EXECUTABLE` 指定可执行文件。浏览器脚本未纳入 CI；最终版本仍须人工查看截图和复核结果。

更详细的操作与权限说明见 [用户手册](docs/USER_GUIDE.md)，本轮变更及已知限制见 [发布说明](docs/RELEASE_NOTES.md)。

## 代码目录

```text
app.py                   启动入口
aimanager/__init__.py    应用工厂与模块装配
aimanager/auth/          登录与退出
aimanager/tasks/         任务页面、校验、状态服务
aimanager/evidence/      历史交付记录回归模块
aimanager/models.py      用户、项目、项目成员、任务和状态历史
aimanager/permissions.py 项目和任务权限
aimanager/seed.py        本地演示身份和项目初始化
migrations/              数据库结构迁移
templates/               页面模板
static/                  样式与轻量脚本
tests/                   自动化测试
```

历史交付数据仍保留在 `data/evidence.json`，用于验证权限隔离和三态完成门禁；它不参与当前任务统计，也不出现在产品主导航中。
