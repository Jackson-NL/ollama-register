# -*- coding: utf-8 -*-
"""测试: Playwright 加载用户真实扩展(scriptcat)后 Turnstile 是否正常。"""
import json
import logging
import sys
import time
import os

sys.path.insert(0, r'D:\PRO\ollama-register')

from playwright.sync_api import sync_playwright
from src.stealth import STEALTH_FULL

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('test')

SIGNUP_URL = ('https://signin.ollama.com/sign-up?'
              'client_id=client_01JX0QMHD43PFFCCNXH82A6K8B'
              '&redirect_uri=https%3A%2F%2Follama.com%2Fauth%2Fcallback'
              '&screen_hint=sign-up')

# scriptcat extension dir
EXT = os.path.join(os.environ['LOCALAPPDATA'],
                   r'Microsoft\Edge\User Data\Default\Extensions\amkbmndfnliijdhojkpoglbnaaahippg\1.32.5_0')


def main():
    print('ext dir exists:', os.path.exists(EXT))
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=r'E:\down\Temp\pw-scriptcat-test',
            channel='msedge', headless=False,
            args=['--no-first-run', '--no-default-browser-check',
                  '--disable-blink-features=AutomationControlled',
                  f'--disable-extensions-except={EXT}',
                  f'--load-extension={EXT}',
                  '--remote-debugging-port=9342', '--remote-allow-origins=*'],
            viewport={'width': 1400, 'height': 900},
            locale='en-US',
        )
        ctx.add_init_script(STEALTH_FULL)
        page = ctx.new_page()

        fps = page.evaluate("""() => ({
            webdriver: navigator.webdriver,
            chromeRuntime: typeof (window.chrome && window.chrome.runtime),
            plugins: navigator.plugins.length,
            scripts: document.scripts.length,
        })""")
        log.info('指纹: %s', json.dumps(fps))

        page.goto(SIGNUP_URL, wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(5000)
        for i in range(25):
            if page.evaluate("() => !!document.querySelector('input[name=\"email\"]')"):
                break
            page.wait_for_timeout(2000)
        else:
            log.error('表单未加载')
            return

        log.info('表单已加载')
        # 检查 content script 是否注入 (scriptcat 会在页面注入)
        log.info('body class 含 scriptcat:', page.evaluate("() => document.body ? document.body.className : ''")[:80])

        page.evaluate("""(email) => {
            const el = document.querySelector('input[name="email"]');
            const setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
            setter.call(el, email);
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }""", 'sctest.' + str(int(time.time())) + '@duck.com')
        page.wait_for_timeout(1000)
        page.evaluate("() => document.querySelector('form').requestSubmit()")

        for i in range(30):
            page.wait_for_timeout(2000)
            state = page.evaluate("""() => ({
                err: (() => {
                    const el = document.querySelector('[data-type="error"]');
                    return el ? el.innerText : '';
                })(),
                body: document.body.innerText.slice(0, 120),
                iframe: !!document.querySelector('iframe[src*="challenges.cloudflare.com"]'),
                token: (() => {
                    const el = document.querySelector('input[name="bot_detection_token"]');
                    return el ? el.value.slice(0, 20) : '';
                })(),
            })""")
            log.info('[%ds] %s', i * 2, json.dumps(state, ensure_ascii=False))
            if state['token']:
                log.info('>>> Turnstile 通过!')
                break
            if state['err'] and 'human' in state['err']:
                log.info('>>> 失败')
                break

        page.screenshot(path=r'D:\PRO\ollama-register\captures\sctest.png')
        ctx.close()


if __name__ == '__main__':
    main()
