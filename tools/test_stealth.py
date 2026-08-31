# -*- coding: utf-8 -*-
"""测试完整 stealth: 启动浏览器检查指纹 + 访问 signin 页面看 Turnstile 是否正常。"""
import json
import logging
import sys
import time

sys.path.insert(0, r'D:\PRO\ollama-register')

from playwright.sync_api import sync_playwright
from src.stealth import STEALTH_FULL

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('test')

SIGNUP_URL = ('https://signin.ollama.com/sign-up?'
              'client_id=client_01JX0QMHD43PFFCCNXH82A6K8B'
              '&redirect_uri=https%3A%2F%2Follama.com%2Fauth%2Fcallback'
              '&screen_hint=sign-up')


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel='msedge', headless=False,
            args=['--no-first-run', '--no-default-browser-check',
                  '--disable-blink-features=AutomationControlled',
                  '--remote-debugging-port=9338', '--remote-allow-origins=*'],
        )
        ctx = browser.new_context(viewport={'width': 1400, 'height': 900}, locale='en-US')
        ctx.add_init_script(STEALTH_FULL)
        page = ctx.new_page()

        # check fingerprints
        fps = page.evaluate("""() => ({
            webdriver: navigator.webdriver,
            chromeRuntime: typeof (window.chrome && window.chrome.runtime),
            chromeLoadTimes: typeof (window.chrome && window.chrome.loadTimes),
            plugins: navigator.plugins.length,
            cdc: (() => { var n=0; for (var k in window) if (k.startsWith('$cdc_')) n++; return n; })(),
        })""")
        log.info('指纹: %s', json.dumps(fps))

        log.info('访问注册页...')
        page.goto(SIGNUP_URL, wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(4000)

        # 等表单
        for i in range(25):
            if page.evaluate("() => !!document.querySelector('input[name=\"email\"]')"):
                break
            page.wait_for_timeout(2000)
        else:
            log.error('表单未加载')
            browser.close()
            return

        log.info('表单已加载, 填写邮箱并提交...')
        page.evaluate("""(email) => {
            const el = document.querySelector('input[name="email"]');
            const setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
            setter.call(el, email);
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }""", 'test.stealth.' + str(int(time.time())) + '@duck.com')
        page.wait_for_timeout(1000)
        page.evaluate("() => document.querySelector('form').requestSubmit()")

        # 观察 Turnstile 状态 60 秒 (看是否 600010)
        for i in range(30):
            page.wait_for_timeout(2000)
            state = page.evaluate("""() => ({
                err: (() => {
                    const el = document.querySelector('[data-type="error"]');
                    return el ? el.innerText : '';
                })(),
                iframe: !!document.querySelector('iframe[src*="challenges.cloudflare.com"]'),
                tsDiv: !!document.getElementById('cf-turnstile'),
                token: (() => {
                    const el = document.querySelector('input[name="bot_detection_token"]');
                    return el ? el.value.slice(0, 20) : '';
                })(),
            })""")
            log.info('[%ds] %s', i * 2, json.dumps(state, ensure_ascii=False))
            if state['token']:
                log.info('>>> Turnstile 通过!')
                break
            if state['err']:
                log.info('>>> 页面报错: %s', state['err'])
                break

        page.screenshot(path=r'D:\PRO\ollama-register\captures\stealth-test.png')
        browser.close()


if __name__ == '__main__':
    main()
