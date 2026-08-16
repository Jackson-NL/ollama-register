# -*- coding: utf-8 -*-
"""完整注册流程(半自动): Playwright 驱动真实 Edge。
流程:
1. 打开 sign-in 页, 填邮箱 (email.txt)
2. requestSubmit -> 等用户点击 Turnstile -> token 注入自动重提
3. 跳转密码页 -> 填密码 -> requestSubmit -> 等用户再点 Turnstile
4. 完成注册 -> 回调 ollama.com

Turnstile 每次提交都需要真人点击 (Cloudflare 检测自动化)。
"""
import json
import logging
import sys
import time
import uuid

from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('reg')

SIGNUP_URL = ('https://signin.ollama.com/sign-up?'
              'client_id=client_01JX0QMHD43PFFCCNXH82A6K8B'
              '&redirect_uri=https%3A%2F%2Follama.com%2Fauth%2Fcallback'
              '&screen_hint=sign-up')

STEALTH = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
for (const k of Object.getOwnPropertyNames(window)) {
    if (k.startsWith('$cdc_') || k.startsWith('cdc_')) {
        try { delete window[k]; } catch (e) {}
    }
}
"""


def read_emails(path):
    with open(path, encoding='utf-8') as f:
        return [l.strip() for l in f if l.strip()]


def fill_react_input(page, selector, value):
    page.evaluate("""(args) => {
        const [sel, val] = args;
        const el = document.querySelector(sel);
        if (!el) throw new Error('not found: ' + sel);
        const setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, val);
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }""", [selector, value])


def wait_turnstile_and_submit(page, timeout=300):
    """等待用户点击 Turnstile 并自动完成提交。返回 True=已离开/成功。"""
    log.info('>>> 请在浏览器窗口完成 Turnstile 人机验证(点击验证框)')
    start = time.time()
    while time.time() - start < timeout:
        url = page.url
        if 'signin.ollama.com' not in url:
            log.info('页面已跳转: %s', url[:120])
            return True
        token = page.evaluate("""(() => {
            const el = document.querySelector('input[name="bot_detection_token"]');
            return el ? el.value : '';
        })()""")
        if token:
            log.info('Turnstile token 已获得, 自动重提...')
            page.evaluate("() => { const f = document.querySelector('form'); if (f) f.requestSubmit(); }")
            time.sleep(3)
            return True
        # 尝试桥接 turnstile API 的 token
        bridged = page.evaluate("""(() => {
            if (typeof window.turnstile === 'undefined') return false;
            const token = window.turnstile.getResponse();
            if (!token) return false;
            const form = document.querySelector('form');
            if (!form) return false;
            let el = form.querySelector('input[name="bot_detection_token"]');
            if (!el) {
                el = document.createElement('input');
                el.type = 'hidden';
                el.name = 'bot_detection_token';
                form.appendChild(el);
            }
            el.value = token;
            return true;
        })()""")
        if bridged:
            log.info('桥接 turnstile token, 重新提交...')
            page.evaluate("() => { const f = document.querySelector('form'); if (f) f.requestSubmit(); }")
            time.sleep(3)
            return True
        time.sleep(2)
    log.warning('Turnstile 等待超时')
    return False


def run(email, password, debug_port=None):
    with sync_playwright() as p:
        launch_args = ['--no-first-run', '--no-default-browser-check',
                       '--disable-blink-features=AutomationControlled']
        if debug_port:
            launch_args.append(f'--remote-debugging-port={debug_port}')
            launch_args.append('--remote-allow-origins=*')
        browser = p.chromium.launch(
            channel='msedge', headless=False,
            args=launch_args,
        )
        ctx = browser.new_context(viewport={'width': 1400, 'height': 900}, locale='en-US')
        ctx.add_init_script(STEALTH)
        page = ctx.new_page()

        log.info('打开注册页...')
        page.goto(SIGNUP_URL, wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(3000)

        # 等 Cloudflare 质询 + 表单
        for i in range(30):
            if page.evaluate("() => !!document.querySelector('input[name=\"email\"]')"):
                break
            page.wait_for_timeout(2000)
        else:
            log.error('表单未加载(可能 Cloudflare 拦截)')
            browser.close()
            return False

        auth_sid = page.evaluate(
            "() => document.querySelector('input[name=\"authorization_session_id\"]')?.value || ''")
        log.info('authorization_session_id: %s', auth_sid)

        # 填邮箱
        fill_react_input(page, 'input[name="email"]', email)
        log.info('已填邮箱: %s', email)
        page.wait_for_timeout(1000)

        # 提交 -> 触发 Turnstile #1
        page.evaluate("() => document.querySelector('form').requestSubmit()")
        log.info('已提交邮箱, 等待 Turnstile #1...')
        ok1 = wait_turnstile_and_submit(page)
        if not ok1:
            log.error('Turnstile #1 未完成')
            browser.close()
            return False

        # 等待跳转密码页
        for i in range(30):
            url = page.url
            if 'password' in url:
                log.info('已进入密码页: %s', url[:100])
                break
            if 'ollama.com' in url and 'signin' not in url:
                log.info('直接跳到 ollama.com(可能已注册): %s', url[:100])
                browser.close()
                return True
            page.wait_for_timeout(2000)
        else:
            log.error('未跳转密码页, 当前: %s', page.url)
            browser.close()
            return False

        # 填密码
        page.wait_for_timeout(2000)
        fill_react_input(page, 'input[name="password"]', password)
        log.info('已填密码')
        page.wait_for_timeout(1000)

        # 提交密码 -> 触发 Turnstile #2
        page.evaluate("() => document.querySelector('form').requestSubmit()")
        log.info('已提交密码, 等待 Turnstile #2...')
        ok2 = wait_turnstile_and_submit(page)
        if not ok2:
            log.error('Turnstile #2 未完成')
            browser.close()
            return False

        # 等待最终回调
        for i in range(30):
            url = page.url
            if 'ollama.com' in url and 'signin' not in url:
                log.info('注册完成! 回调: %s', url[:100])
                browser.close()
                return True
            page.wait_for_timeout(2000)
        log.warning('回调超时, 当前 URL: %s', page.url)
        browser.close()
        return False


def main():
    emails = read_emails(r'C:\Users\Jackson\Desktop\email.txt')
    log.info('邮箱列表: %d 个', len(emails))
    email = emails[0]
    password = 'Ollama#2026!Secure'
    log.info('使用邮箱: %s', email)
    ok = run(email, password, debug_port=9337)
    log.info('结果: %s', '成功' if ok else '失败')


if __name__ == '__main__':
    main()
