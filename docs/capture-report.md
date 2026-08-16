# Ollama 注册机 — 抓包分析报告(更新)

> 项目: D:\PRO\ollama-register | 阶段: 1(WorkOS Universal Auth 逆向,协议已打通)

## 1. 注册入口与认证架构

访问 `https://ollama.com/signup` → 302 → `signin.ollama.com/sign-up`(WorkOS Universal Auth)

```
https://signin.ollama.com/sign-up?client_id=client_01JX0QMHD43PFFCCNXH82A6K8B
  &redirect_uri=https%3A%2F%2Follama.com%2Fauth%2Fcallback&screen_hint=sign-up
```

- 前端: Next.js App Router(RSC/Flight 协议)
- 认证: **Email + Password**(magic_codes=false, passkey=false)
- 人机验证: **Cloudflare Turnstile(siteKey `0x4AAAAAAAMNIvC45A4Wjjln`, interaction-only 模式)** — 必须真人点击,无法程序化绕过
- 反机器人: **WorkOS Radar**(WebGL/canvas/音频指纹 + puppeteer/playwright/selenium 检测)

## 2. 请求流程(全部经真实浏览器 CDP 抓包确认)

### 2.1 GET 注册页
- 首次请求:**Cloudflare 托管质询(403 + chl_page)** — 真实浏览器自动执行 Turnstile JS 后放行
- Set-Cookie: `__cf_bm`, `_cfuvid`
- 页面含 `authorization_session_id`(每次动态,如 `01M04ECKWTA70A6CDXPRPR9126`)
- 表单字段: `email` / `signals`(Radar 指纹 btoa-base64)/ `redirect_uri` / `authorization_session_id` / `browser_supports_passkeys`
- **纯 HTTP 客户端(curl/Python)会因 TLS 指纹被 403,必须真实浏览器**

### 2.2 Radar 指纹(signFingerprint server action)
- `POST /`  header `Next-Action: 40997b27aaa3cef30beb8078d05c5b6a4a6935720f`
- body(text/plain, **JSON 数组**): `["<fingerprintHash>"]`
- 响应: `{"payload":"Fe26.2*..."}` → 前端写入 cookie `__wuid`
- 另有 `POST /api/radar-signals` body `{"signals":{...}}` → `{"success":true}`

### 2.3 email 提交(signIn server action)
- `POST <页面完整URL>` header `Next-Action: 408f756f6d8ddf10c06b05ff2cdf5cf640ce7f9dbd`
- body: **multipart/form-data, React Flight 编码**:
  ```
  name="0" → ["$K1"]        ← 参数序列化声明(关键!)
  name="1_<字段名>" → 值     ← 字段(1_ 前缀)
  ```
- 字段: email / redirect_uri / authorization_session_id / state / signals / bot_detection_token
- 协议打通证据: 带 `["$K1"]` 时返回业务错误 `{"code":"invalid_params"}`,不带时 500

### 2.4 Turnstile(当前卡点)
- 页面 bot-check 阶段显示「请验证您是真人」,widget 容器 `#cf-turnstile`
- `window.turnstile.render(el, {sitekey, action, appearance:'interaction-only'})` 可渲染 widget
- **必须真人点击 checkbox,iframe 才出现并生成 token → 写入 bot_detection_token → 表单自动重提**
- CDP 鼠标事件模拟点击无效(Cloudflare 检测自动化)

## 3. server actions 清单

| action | id | 用途 |
|---|---|---|
| signFingerprint | `40997b27aaa3cef30beb8078d05c5b6a4a6935720f` | 指纹 → __wuid |
| signIn(email/password) | `408f756f6d8ddf10c06b05ff2cdf5cf640ce7f9dbd` | 提交 email |
| joinWaitlist | `40c478ca68c40f63f1aa399983cc65e38b8b7b1d4d` | waitlist |
| createPasskeyChallenge | `00871a7aeacd106abc8f94cbff909afaa399a0863c` | passkey |
| signInWithPasskey | `40c4c3a9876587d7863fee41a24fa7cc9ea7efbbf9` | passkey |

## 4. 结论(注册机可行性)

1. **纯 HTTP 模拟不可能**: Cloudflare TLS 指纹 + Turnstile 双重拦截
2. **必须真实浏览器自动化**(Playwright/CDP 驱动 Edge/Chrome,非 headless)
3. **Turnstile 是决定性障碍**: 每个新 IP/指纹可能都要人机验证;批量注册需:
   - 打码平台(如 CapSolver/2Captcha 的 Turnstile 服务),或
   - 人工辅助点击(半自动),或
   - 优质住宅 IP 池降低触发率
4. Radar 指纹可通过真实浏览器自动生成(页面 JS 自带),signFingerprint 协议已确认

## 5. 下一步

- [ ] 人工点击 Turnstile → 抓包确认 signIn 成功后的完整响应(密码设置页 / OTP / 回调)
- [ ] 确认密码设置 action(可能为另一个 server action)
- [ ] 确认 ollama.com/auth/callback 的 session 建立
- [ ] 用 Playwright 实现注册机骨架(真实浏览器自动化)
- [ ] 评估 Turnstile 打码方案(CapSolver 等)或半自动模式
