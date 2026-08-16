# Ollama 注册机 - 项目说明
# 基于抓包确认的 WorkOS Universal Auth 注册流程实现

## 抓包结论(详见 docs/capture-report.md)

- 注册入口: `https://ollama.com/signup` → `signin.ollama.com/sign-up`
- 认证: Email + Password(WorkOS Universal Auth)
- 防护链:
  1. Cloudflare TLS 指纹(纯 HTTP 客户端必 403,必须真实浏览器)
  2. WorkOS Radar 反机器人(指纹采集 + 自动化检测)
  3. Cloudflare Turnstile 人机验证(必须真人点击或打码平台)

## 架构

```
ollama-register/
├── main.py                 # CLI 入口
├── src/
│   ├── __init__.py
│   ├── config.py           # 配置(邮箱、代理、打码 API key)
│   ├── registrar.py        # 核心注册流程(Playwright 驱动)
│   ├── browser.py          # 浏览器启动 + stealth 反检测
│   └── captcha.py          # Turnstile 处理(半自动/打码平台)
├── tools/                  # 抓包分析脚本(逆向过程留档)
├── captures/               # 抓包数据
└── docs/capture-report.md  # 抓包分析报告
```

## 使用

```bash
python main.py --email your@mail.com --password yourpass --headful
```

## 关键实现点

1. **必须 headful 真实浏览器**: Playwright 启动 Edge/Chrome 非 headless,过 Cloudflare
2. **Radar 指纹**: 页面自带 JS 生成,注册机无需伪造(真实浏览器自动通过)
3. **Turnstile**: 默认半自动模式(检测到验证框时暂停等人工点击),可选接入打码平台
4. **server action**: 直接 DOM 操作提交,React 自动构造 Next-Action 请求
