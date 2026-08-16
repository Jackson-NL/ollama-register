# -*- coding: utf-8 -*-
"""配置模块: 注册机参数。"""
import os


class Config:
    def __init__(self):
        # 注册邮箱(可从命令行/环境变量覆盖)
        self.email = os.environ.get('OLLAMA_REG_EMAIL', '')
        # 密码(WorkOS password 认证)
        self.password = os.environ.get('OLLAMA_REG_PASSWORD', '')
        # 注册后展示名
        self.display_name = os.environ.get('OLLAMA_REG_NAME', '')

        # 浏览器
        self.browser_type = os.environ.get('OLLAMA_REG_BROWSER', 'edge')  # edge | chrome
        self.headless = os.environ.get('OLLAMA_REG_HEADLESS', '0') == '1'

        # 代理(可选, 格式 http://user:pass@host:port)
        self.proxy = os.environ.get('OLLAMA_REG_PROXY', '')

        # 打码平台(可选): 2captcha / capsolver, 用于 Turnstile 自动通过
        # 半自动模式留空 = 检测到 Turnstile 时暂停等人工点击
        self.captcha_service = os.environ.get('OLLAMA_REG_CAPTCHA', '')  # none | capsolver | 2captcha
        self.captcha_api_key = os.environ.get('OLLAMA_REG_CAPTCHA_KEY', '')

        # 请求节流(秒), 避免触发 Cloudflare 限流
        self.action_delay = float(os.environ.get('OLLAMA_REG_DELAY', '2'))

        # 邮箱验证码(手动输入模式)
        self.otp_manual = os.environ.get('OLLAMA_REG_OTP_MANUAL', '1') == '1'

    def validate(self):
        problems = []
        if not self.email:
            problems.append('缺少邮箱 (--email 或 OLLAMA_REG_EMAIL)')
        if not self.password:
            problems.append('缺少密码 (--password 或 OLLAMA_REG_PASSWORD)')
        if self.captcha_service and not self.captcha_api_key:
            problems.append('配置了打码服务但缺少 API key')
        return problems


def parse_args(argv):
    """轻量参数解析, 避免引入 argparse 之外的依赖。"""
    cfg = Config()
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--email', '-e'):
            cfg.email = argv[i + 1]; i += 2
        elif a in ('--password', '-p'):
            cfg.password = argv[i + 1]; i += 2
        elif a in ('--name', '-n'):
            cfg.display_name = argv[i + 1]; i += 2
        elif a == '--proxy':
            cfg.proxy = argv[i + 1]; i += 2
        elif a == '--browser':
            cfg.browser_type = argv[i + 1]; i += 2
        elif a == '--headless':
            cfg.headless = True; i += 1
        elif a == '--captcha-service':
            cfg.captcha_service = argv[i + 1]; i += 2
        elif a == '--captcha-key':
            cfg.captcha_api_key = argv[i + 1]; i += 2
        elif a == '--no-otp-manual':
            cfg.otp_manual = False; i += 1
        elif a == '--delay':
            cfg.action_delay = float(argv[i + 1]); i += 2
        else:
            i += 1
    return cfg
