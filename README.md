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
py -m pytest tests -q -p no:cacheprovider
```

## DoD判定规则

`data/evidence.json` 顶层保存六项必要证据，每项使用三态：

- `approved`：已通过；
- `rejected`：被拒绝或失败，已退回修复；
- `pending`：尚未补齐。

只有六项全部为 `approved` 时，页面才显示绿色“可以进入Sprint评审”。任意一项为 `rejected` 或 `pending` 都显示红色“未达到DoD”，被拒绝的证据不会被其他齐备证据放过。证据链页面直接读取顶层真实提交、测试和审查数据，不使用写死的占位数组。

## 岗位与权限

`product`、`tech`、`quality`、`ai_record` 四个岗位各自只显示职责范围内内容；完整八段证据链只有 `quality`（本轮DRI）可见。非 `quality` 岗位访问 `/quality` 时由服务端返回 HTTP 403。

## Git流程

基础提交在 `main`，候选开发分支为 `feat/sprint-evidence-cockpit`。候选分支须先交杨濠宇完成人工审查，收到“允许合并”后才能合并 main；人工审查发生在合并 main 之前。

## 范围与证据

本轮正式完成范围只有实验一 Sprint 1 的 U6。不包含注册、真实登录、数据库、任务 CRUD、通知、部署和真实大模型接口。`data/evidence.json` 中的提交和测试字段记录真实结果；人工审查在结论产生前保持 `pending`。
