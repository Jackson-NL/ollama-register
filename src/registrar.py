# -*- coding: utf-8 -*-
"""注册机核心流程: Playwright 驱动真实浏览器完成 ollama.com 注册。

抓包确认的流程 (docs/capture-report.md):
1. 打开 ollama.com/signup -> 302 到 signin.ollama.com/sign-up (WorkOS)
2. 等 Cloudflare 托管质询自动通过 (真实浏览器)
3. 页面加载: Radar 指纹自动生成 (signals 字段) + signFingerprint -> __wuid
4. 填 email -> requestSubmit -> 触发 Turnstile
5. 人工/打码完成 Turnstile -> bot_detection_token 注入 -> 表单自动重提
6. signIn server action -> 进入密码设置 (password 认证)
7. 设密码 -> 回调 ollama.com/auth/callback -> 注册完成
"""
import logging
import time

from .browser import launch_browser
from .captcha import wait_and_handle_turnstile, TurnstileError

log = logging.getLogger('registrar')

SIGNUP_URL = ('https://signin.ollama.com/sign-up?'
              'client_id=client_01JX0QMHD43PFFCCNXH82A6K8B'
              '&redirect_uri=https%3A%2F%2Follama.com%2Fauth%2Fcallback'
              '&screen_hint=sign-up')


class Registrar:
    def __init__(self, cfg):
        self.cfg = cfg
        self.browser = None
        self.context = None
        self.page = None

    def run(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            self.browser, self.context, self.page = launch_browser(p, self.cfg)
            try:
                return self._flow()
            finally:
                self.browser.close()

    def _flow(self):
        page = self.page
        page.goto(SIGNUP_URL, wait_until='domcontentloaded', timeout=60000)
        log.info('已打开注册页')

        # 1. 等待 Cloudflare 质询通过 + 页面表单加载
        self._wait_email_form(timeout=90)

        # 2. 记录 authorization_session_id
        auth_sid = page.evaluate("""(() => {
            const el = document.querySelector('input[name="authorization_session_id"]');
            return el ? el.value : null;
        })()""")
        log.info('authorization_session_id: %s', auth_sid)

        # 3. 填写邮箱 (原生 setter 触发 React onChange)
        page.evaluate("""(email) => {
            const el = document.querySelector('input[name="email"]');
            if (!el) throw new Error('email input not found');
            const setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
            setter.call(el, email);
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }""", self.cfg.email)
        log.info('已填写邮箱: %s', self.cfg.email)
        time.sleep(self.cfg.action_delay)

        # 4. 提交表单 (requestSubmit 触发 React form action)
        page.evaluate("() => document.querySelector('form').requestSubmit()")
        log.info('已提交邮箱表单')

        # 5. 处理 Turnstile
        ok = wait_and_handle_turnstile(page, self.cfg)
        if not ok:
            raise TurnstileError('Turnstile 未通过')

        # 6. 等待下一步 (密码设置 或 邮箱验证码)
        self._wait_next_step()

        # 7. 设置密码
        self._set_password()

        # 8. 等待回调 ollama.com
        self._wait_callback()
        return {'status': 'ok', 'email': self.cfg.email}

    def _wait_email_form(self, timeout):
        log.info('等待注册表单加载...')
        end = time.time() + timeout
        while time.time() < end:
            try:
                ok = self.page.evaluate(
                    "() => !!document.querySelector('input[name=\"email\"]')")
                if ok:
                    title = self.page.title()
                    log.info('表单已加载, title=%s', title)
                    return
            except Exception:
                pass
            time.sleep(2)
        raise RuntimeError('注册表单加载超时 (可能被 Cloudflare 拦截)')

    def _wait_next_step(self):
        """Turnstile 通过后: 等待出现密码输入框或验证码输入框。"""
        log.info('等待下一步 (密码/验证码)...')
        end = time.time() + 120
        while time.time() < end:
            url = self.page.url
            # 密码输入框 (Create a password)
            has_pw = self.page.evaluate("""(() => {
                const el = document.querySelector('input[type="password"]');
                return !!el;
            })()""")
            if has_pw:
                log.info('出现密码输入框')
                return 'password'
            # 验证码输入 (OTP)
            has_otp = self.page.evaluate("""(() => {
                const el = document.querySelector('input[autocomplete="one-time-code"]');
                return !!el;
            })()""")
            if has_otp:
                log.info('出现验证码输入框')
                return 'otp'
            if 'signin.ollama.com' not in url:
                log.info('页面跳转: %s', url[:120])
                return 'navigated'
            time.sleep(2)
        raise RuntimeError('等待下一步超时')

    def _set_password(self):
        """WorkOS 密码设置: 输入密码 + 确认 + 提交。"""
        pw = self.cfg.password
        page = self.page
        log.info('设置密码...')
        page.fill('input[type="password"]', pw)
        time.sleep(0.5)
        # 可能有确认密码框
        pws = page.query_selector_all('input[type="password"]')
        if len(pws) > 1:
            pws[1].fill(pw)
            time.sleep(0.5)
        # 提交
        page.evaluate("""(() => {
            const f = document.querySelector('form');
            if (f) f.requestSubmit();
            else {
                const b = document.querySelector('button[type="submit"]');
                if (b) b.click();
            }
        })()""")
        log.info('密码已提交')

    def _wait_callback(self, timeout=120):
        log.info('等待跳转回 ollama.com...')
        end = time.time() + timeout
        while time.time() < end:
            url = self.page.url
            if 'ollama.com' in url and 'signin' not in url:
                log.info('注册回调完成: %s', url[:120])
                return
            time.sleep(2)
        log.warning('回调等待超时, 当前 URL: %s', self.page.url)
