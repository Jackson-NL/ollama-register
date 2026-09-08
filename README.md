<p align="center">
  <img src="assets/qq-group.png" alt="code技术交流群" width="300" />
</p>
<p align="center"><strong>code技术交流群 · 群号：1073672527</strong> — QQ 扫码加入群聊</p>

---

# Ollama Register CLI

![Node.js](https://img.shields.io/badge/Node.js-18%2B-339933?logo=node.js&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-1.53-2EAD33?logo=playwright&logoColor=white)
![Camoufox](https://img.shields.io/badge/Camoufox-0.1.19-F76D0D?logo=firefox&logoColor=white)
![License](https://img.shields.io/github/license/Jackson-NL/ollama-register)

这是一个本地 CLI 自动化工具链，使用 Node.js + Camoufox/Playwright 执行 Ollama 注册流程，支持半自动和全自动运行、SMSBower 接码、Cloudflare checkpoint 处理、代理节点轮换、状态监控和运行证据输出。

项目地址：[github.com/Jackson-NL/ollama-register](https://github.com/Jackson-NL/ollama-register)

本项目采用 [MIT License](LICENSE) 开源。

## 核心特性

- **半自动与全自动流程**：保留人工处理 Cloudflare/Turnstile 的半自动入口，同时提供 CLI 全自动调度器。
- **批量与重试**：支持目标数量、并发数和单目标尝试次数配置。
- **SMSBower 接码**：支持国家、区号、服务商和价格上限配置。
- **代理与节点轮换**：可通过 Camoufox 代理和本机 mihomo/Clash controller 轮换出口节点。
- **状态与证据**：提供本地健康检查、运行状态、结构化日志和 Playwright 快照输出。
- **敏感信息保护**：真实 `.env`、账号结果、API key、运行输出和浏览器 profile 默认不会提交。

## 项目结构

```text
.
├── README.md
├── DESIGN.md
├── package.json
├── package-lock.json
├── .env.example
├── accounts.example.jsonl
├── config/                  # 本地私有配置，默认不提交
└── scripts/
    ├── cli.js               # CLI 入口；解析参数、加锁、启动 runner
    ├── run_auto_full.js     # 批量/重试调度器 + 本地状态服务
    ├── auto_signup_full.js  # 单次完整注册状态机
    ├── recover_api_key.js   # 已有账号 API key 恢复工具
    ├── watch_auto_run.js    # 本地运行状态查看工具
    └── lib/
        ├── auto_helpers.js
        ├── cli_helpers.js
        ├── clash_verge.js
        ├── run_logger.js
        └── *.test.js
```

## 快速开始

```powershell
npm install
Copy-Item .env.example .env
# 编辑 .env，填入 SMSBOWER_API_KEY；默认示例为智利 +56，价格上限 0.015
npm run cli -- --target 1 --country chile --keep-open
```

## 环境准备

- Node.js 18+
- Python 3.10+（仅使用旧版 Python 入口时需要）
- Camoufox 浏览器依赖
- SMSBower API key
- 可选：mihomo/Clash Verge Rev 与代理节点

复制 `.env.example` 为 `.env`，至少填写 `SMSBOWER_API_KEY`。`.env` 只保存在本地，不要上传到公开仓库。
## 半自动与全自动入口

当前工作区保留两条运行路径：

```powershell
# 半自动：旧版人工 Cloudflare/Turnstile checkpoint 流程
npm run register:one
# 或
npm run semi:auto

# 全自动：当前 CLI runner / SMSBower / Camoufox 流程
npm run cli -- --target 1 --country chile --max-price 0.015 --keep-open
```

旧版半自动 Python 入口也已恢复：

```powershell
python main.py --email your@mail.com --password yourpass --headful
```

常用命令：

```powershell
# 查看解析后的运行环境，不执行真实注册
npm run cli -- --target 1 --country chile --max-price 0.015 --keep-open --dry-run

# 单账号真实流程；失败也保留浏览器
npm run cli -- --target 1 --country chile --max-price 0.015 --keep-open

# 批量 5 个，单并发，每个目标尝试 1 次
npm run cli -- --target 5 --concurrency 1 --attempts 1 --country chile
```

## CLI 参数

- `--target <n>`：目标账号数量，默认 `1`。
- `--concurrency <n>`：并发数，默认 `1`。
- `--attempts <n>`：每个目标最大尝试次数，默认 `1`。
- `--country chile|cl|indonesia|id`：国家预设，默认 `chile`。
- `--sms-country <id>` / `--dial-code <+code>` / `--provider <ids>`：覆盖 SMSBower 参数。
- `--max-price <price>`：租号价格上限。
- `--proxy <url>`：Camoufox 浏览器代理。
- `--smsbower-proxy <url>`：SMSBower API 代理。
- `--keep-open`：结束或失败后不关闭浏览器。
- `--headless`：无头模式。
- `--dry-run`：只打印最终 runner 环境。

## 固定状态端口

CLI 运行时默认监听：`http://127.0.0.1:8787/status`。

- 健康检查：`http://127.0.0.1:8787/health`
- 当前状态：`http://127.0.0.1:8787/status`
- 如需覆盖：`npm run cli -- --port 8799`


## 服务器节点轮换

服务器部署建议走本机 `mihomo`：

```dotenv
CLASH_ENABLED=1
CLASH_CONTROLLER_URL=http://127.0.0.1:9090
CLASH_PROXY_URL=http://127.0.0.1:7890
CAMOUFOX_PROXY=http://127.0.0.1:7890
SMSBOWER_PROXY=http://127.0.0.1:7890
CLASH_ROTATE_AFTER_RUN=1
CLASH_ROTATE_GROUP=SELECT
CLASH_ROTATE_EXCLUDE=香港|Hong Kong|HK|🇭🇰
```

`run_auto_full.js` 会在每个账号 attempt 结束后调用 mihomo controller，把 `SELECT` 组切到下一个非香港、非 `AUTO/DIRECT` 节点；轮换失败只记录 `CLASH_ROTATE_FAILED`，不改变注册流程退出码。

## 输出与敏感文件

- 运行目录：`output/playwright/auto-runs/<runId>/`
- 主日志：`auto_signup.log`、`runner.log`
- 状态文件：`status.json`
- 表单快照/截图：同一运行目录下的 `*.json`、`*.png`
- 账号结果：`accounts_auto.jsonl`

日志会尽量脱敏；`accounts_auto.jsonl` 按当前实现会保存完整账号材料和 API key，用于本地后续使用。`.env`、`accounts_auto.jsonl`、`output/`、`config/*.json` 等默认被 `.gitignore` 忽略，不要提交。

## 安全与合规

- 账号结果、密码、验证码、API key 和代理配置属于敏感数据，只能保存在本地安全位置。
- 本项目默认面向本地或受控环境，不建议把状态端口暴露到公网。
- 使用前请遵守 Ollama、邮箱、SMSBower、Cloudflare 及代理服务的用户协议和当地法律法规。
- 本项目仅供学习和研究使用，使用者自行承担运行产生的账号、费用和合规风险。

## Star History

<a href="https://www.star-history.com/#Jackson-NL/ollama-register&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=Jackson-NL/ollama-register&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=Jackson-NL/ollama-register&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=Jackson-NL/ollama-register&type=Date" />
  </picture>
</a>

## 配置

复制 `.env.example` 为 `.env` 后填写真实密钥。智利默认配置：

```dotenv
SMSBOWER_COUNTRY=151
SMSBOWER_DIAL_CODE=+56
SMSBOWER_PROVIDER_IDS=3419
SMSBOWER_MAX_PRICE=0.015
SMS_WAIT_MS=60000
```

手机号流程会筛选智利移动号：本地号必须匹配 `9xxxxxxxx`，并在提交前校验 `country_code` 与 `local_number`，避免 React phone mask 清空或错位。

## 验证

```powershell
npm test
node --check scripts/auto_signup_full.js
node --check scripts/run_auto_full.js
node --check scripts/cli.js
npm run cli -- --target 1 --country chile --max-price 0.015 --keep-open --dry-run
```

真实注册会访问 Ollama、Cloudflare、临时邮箱和 SMSBower，可能产生外部服务费用；本地测试不会执行真实注册。
