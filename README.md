# Sprint可信交付舱

21组“爱管理”实验二 Sprint 1 的增量交付物。页面按岗位隔离交付内容，并用本地 JSON 证据实时计算 DoD 状态——**不是说做完了，而是用证据证明做完了**。

本轮正式完成的用户故事只有实验一 Sprint 1 的 **U6：团队成员只能看到自己有权限的项目内容**。

## 当前状态

| 项目 | 状态 |
|---|---|
| main 合并提交 | `0a82780`（DRI 二次复审通过后合并） |
| 候选分支 | `feat/sprint-evidence-cockpit` = `9b802bd` |
| 自动化测试 | 51 项全部通过 |
| 人工审查 | 杨濠宇二次复审通过，允许合并 main |
| 远程仓库 | https://github.com/hexu-xu/group21-sprint-evidence-cockpit |
| DoD 页面状态 | 绿色「可以进入Sprint评审」（六项必要证据齐全） |

## 环境要求

- Windows / macOS / Linux 均可
- Python 3.10 及以上（开发环境为 Python 3.14）
- 依赖仅 Flask 与 pytest，见 `requirements.txt`

## 安装与启动

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1        # macOS/Linux: source .venv/bin/activate
py -m pip install -r requirements.txt
py app.py
```

启动后访问 http://127.0.0.1:5000/ ，按 Ctrl+C 停止。

页面不依赖任何外部 CDN，可离线演示。

## 岗位与访问地址

| 岗位键 | 展示名 | 可见内容 | 示例地址 |
|---|---|---|---|
| `product` | 产品与范围 | U6 用户故事、用户价值、验收标准、当前演示状态 | `/?role=product` |
| `tech` | 技术与架构 | Sprint 开发任务、功能分支、提交、运行说明 | `/?role=tech` |
| `quality` | 质量与风险（DRI） | 完整八段证据链与 DoD 结论 | `/?role=quality` |
| `ai_record` | AI协调与记录 | AI 角色、提示词、输出摘要、团队处置、证据缺口 | `/?role=ai_record` |

权限规则：岗位只返回其职责范围内容；完整质量详情为 `/quality?role=quality`。非 `quality` 岗位访问 `/quality` 时，**服务端直接返回 HTTP 403**，不只是隐藏页面按钮。

未知的 `role` 参数会回落到 `product`，不会造成越权。

## 测试

```powershell
py -m pytest tests -q
```

若本机 pytest 缓存目录报权限错误，可加参数：

```powershell
py -m pytest tests -q -p no:cacheprovider
```

测试文件与覆盖范围：

| 文件 | 覆盖内容 |
|---|---|
| `tests/test_permissions.py` | 岗位归一化、只有 quality 可看完整详情、四岗位均有展示名 |
| `tests/test_dod_gate.py` | 三态归一化、任意一项 pending/rejected/布尔False 均不通过、八段证据链顺序与真实文本 |
| `tests/test_routes.py` | 首页岗位隔离、非 DRI 不可见证据链、红绿状态、403 服务端校验、真实证据与页面一致 |

## DoD 判定规则

`data/evidence.json` 顶层保存六项必要证据，每项为三态结构：

```json
"human_review": {"status": "approved", "value": "杨濠宇二次复审结论：通过，允许合并main"}
```

- `approved`：已通过；
- `rejected`：被拒绝或失败，已退回修复；
- `pending`：尚未补齐。

只有六项**全部**为 `approved` 时，页面才显示绿色「可以进入Sprint评审」。任意一项为 `rejected` 或 `pending` 都显示红色「未达到DoD」；**被拒绝的证据不会被其他齐备证据放过**，布尔 `False` 同样不通过。

判定逻辑集中在 `dod_gate.py`，状态由证据计算得出，页面没有任何写死的绿色。

六项必要证据依次为：用户故事、Sprint任务、AI功能分支、Git提交、自动化测试、人工审查。

## 证据链

完整链路按固定八段展示，页面直接读取顶层真实数据，不使用写死的占位数组：

```text
用户故事 → Sprint任务 → AI功能分支 → Git提交
→ 自动化测试 → 人工审查 → DoD门禁 → 可以评审
```

每段都带三态标记（已通过 / 已拒绝 / 待补证）。`rejected` 与 `pending` 的段会同时出现在页面的“缺口”提示中。

## 目录结构

```text
app.py                   Flask应用、路由与服务端权限校验
permissions.py           四岗位定义与权限判断
dod_gate.py              三态归一化、DoD计算、八段证据链构建
data/evidence.json       顶层真实证据（六项 + 分支/提交/审查记录）
templates/index.html     交付舱页面（岗位内容 + 状态面板 + 证据链）
templates/403.html       统一403页面
static/style.css         页面样式
static/app.js            轻量交互
tests/                   51项自动化测试
requirements.txt         依赖清单
README.md                本文件
```

## Git 流程与分支策略

- 基础提交：`main` 上的 `36e3778 chore: initialize sprint evidence cockpit`；
- 唯一功能分支：`feat/sprint-evidence-cockpit`；
- 功能提交：`c7e0fb1`、`ffc2646`（首次候选）；
- 二次修复提交：`2b88da8`（DoD三态与顶层证据链）、`43405dc`（证据记录）；
- 审查后补充提交：`c443063`（仅测试解耦）、`9b802bd`（人工审查 approved）；
- 合并提交：`0a82780`，使用 `--no-ff`，**人工审查结论先于 main 合并提交产生**。

门禁要求：候选分支必须先交本轮 DRI（杨濠宇）完成人工审查，收到“允许合并”后才能合并 `main`；人工审查不得晚于 `main` 合并。完整分支图见交付证据 `../21组_证据/Git记录/01_Git分支图_TC11.txt`（相对本仓库）。

## 范围与真实性边界

本轮范围仅 U6。**不包含**注册、真实登录、数据库、任务 CRUD、消息通知、多项目管理、云端部署和真实大模型产品接口。

- `data/evidence.json` 中的提交号、测试结果与审查结论均为真实产生；未产生的证据保持 `pending`，不提前填绿。

## 常见问题

**页面一直是红色？**
检查 `data/evidence.json` 六项证据是否全部为 `approved`；任意一项 `pending`/`rejected` 都会保持红色，这是预期行为。

**访问 `/quality` 报 403？**
说明当前 `role` 不是 `quality`。完整质量详情仅对本轮 DRI 开放，这是服务端强制校验的结果。

**测试报缓存目录权限错误？**
使用 `py -m pytest tests -q -p no:cacheprovider` 跳过 pytest 缓存。
