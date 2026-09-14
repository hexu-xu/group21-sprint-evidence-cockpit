# Sprint可信交付舱

21组“爱管理”实验二 Sprint 1 的 U6 可运行候选版本。页面按岗位隔离交付内容，用本地 JSON 证据计算 DoD 状态。

## 环境与启动

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py app.py
```

打开 http://127.0.0.1:5000/。岗位通过 `?role=product`、`?role=tech`、`?role=quality`、`?role=ai_record` 切换。

## 测试

```powershell
pytest -q
```

## Git流程

基础提交在 `main`，候选开发分支为 `feat/sprint-evidence-cockpit`。候选分支须先交杨濠宇完成人工审查，收到“允许合并”后才能合并 main。

## 范围与证据

本轮正式完成范围只有实验一 Sprint 1 的 U6。不包含注册、真实登录、数据库、任务 CRUD、通知、部署和真实大模型接口。`data/evidence.json` 中的候选提交和测试字段已记录本候选版本的真实结果；人工审查仍待杨濠宇完成。DoD 只有全部必要证据存在时才显示绿色。
