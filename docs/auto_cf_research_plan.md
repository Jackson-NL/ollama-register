# 全自动流程研究方案（不改当前半自动主流程）

## 现状结论

当前已跑通的是“真实浏览器 + CF/Turnstile 人工点击 checkpoint + 自动接管邮箱/密码/短信/API key”的半自动流程。项目最大不稳定点在 CF/WorkOS Radar/Turnstile 阶段。

## 目标

在不破坏当前半自动流程的前提下，新增独立实验分支/脚本，对“点击一次页面即可继续”的场景做可测量验证：

1. 自动识别 challenge 是否出现。
2. 自动记录 challenge 前后的 DOM、frame、URL、cookie、performance/navigation 状态。
3. 测试真实用户手势注入是否能触发后续状态变化。
4. 若失败，保留浏览器和证据，不影响当前可用流程。

## 实验分层

### A. Baseline
- headed Chromium/Chrome channel。
- 独立 profile。
- 只打开注册页，记录 challenge 类型与页面状态。

### B. Human Gate Control
- 检测到 CF/Turnstile 后置顶窗口。
- 人工点击一次。
- 脚本轮询并记录跳转成功条件。

### C. Gesture Automation Probe
- 在独立 profile 中尝试 Playwright mouse move/down/up/click 触发页面普通点击。
- 对比人工点击后的事件序列差异。
- 不复用生产账号、不写入 `accounts.jsonl`，只写实验日志。

### D. Success Criteria
- challenge 后 60s 内进入 email/password/code/phone/settings 任一后续 stage。
- 记录 `stage`, `url`, `title`, `frames`, `turnstileResponses`, `bot_detection_token_present`。

## 文件规划

- `scripts/cf_baseline_probe.js`：只读 baseline 探针。
- `scripts/cf_gesture_probe.js`：独立 profile 手势实验。
- `output/playwright/cf-probes/`：实验输出，已被 `.gitignore` 排除。

## 风险控制

- 默认不批量、不并发。
- 默认不提交注册表单。
- 默认不写真实账号结果。
- 失败时不关闭浏览器，方便人工接管和复盘。
