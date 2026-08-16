# -*- coding: utf-8 -*-
"""对比测试: 完整 stealth 下, 手动 render Turnstile 看能否拿到 token。
不提交表单, 只验证 Turnstile 本身是否工作。
"""
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
                  '--remote-debugging-port=9339', '--remote-allow-origins=*'],
        )
        ctx = browser.new_context(viewport={'width': 1400, 'height': 900}, locale='en-US')
        ctx.add_init_script(STEALTH_FULL)
        page = ctx.new_page()

        page.goto(SIGNUP_URL, wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(4000)
        for i in range(25):
            if page.evaluate("() => !!document.querySelector('input[name=\"email\"]')"):
                break
            page.wait_for_timeout(2000)

        # 手动 render Turnstile 到 #cf-turnstile, 带完整回调
        log.info('手动 render Turnstile...')
        result = page.evaluate("""() => {
            window.__ts = { tok: null, err: null, state: 'pending' };
            try {
                const el = document.getElementById('cf-turnstile');
                const wid = window.turnstile.render(el, {
                    sitekey: '0x4AAAAAAAMNIvC45A4Wjjln',
                    action: 'sign-in',
                    appearance: 'interaction-only',
                    'error-callback': (code) => { window.__ts.err = code; window.__ts.state = 'error'; },
                    'expired-callback': () => { window.__ts.state = 'expired'; },
                    callback: (token) => { window.__ts.tok = token; window.__ts.state = 'ok'; },
                });
                window.__ts.wid = wid;
                return 'rendered: ' + wid;
            } catch(e) {
                window.__ts.state = 'render_exc';
                window.__ts.err = e.message;
                return 'render exc: ' + e.message;
            }
        }""")
        log.info('render: %s', result)

        # 观察 90 秒: 等 iframe / token / error
        for i in range(45):
            page.wait_for_timeout(2000)
            state = page.evaluate("""() => ({
                tsState: window.__ts ? window.__ts.state : 'n/a',
                tsErr: window.__ts ? window.__ts.err : 'n/a',
                tok: window.__ts && window.__ts.tok ? window.__ts.tok.slice(0, 20) : '',
                iframe: !!document.querySelector('iframe[src*="challenges.cloudflare.com"]'),
                tsDiv: !!document.getElementById('cf-turnstile'),
                divHtml: (document.getElementById('cf-turnstile') || {}).innerHTML ?
                    document.getElementById('cf-turnstile').innerHTML.slice(0, 150) : '',
            })""")
            log.info('[%ds] %s', i * 2, json.dumps(state, ensure_ascii=False))
            if state['tsState'] == 'ok' or state['tok']:
                log.info('>>> Turnstile TOKEN 成功!')
                break
            if state['tsState'] == 'error':
                log.info('>>> Turnstile ERROR: %s', state['tsErr'])
                break

        page.screenshot(path=r'D:\PRO\ollama-register\captures\ts-manual.png')
        browser.close()


if __name__ == '__main__':
    main()
