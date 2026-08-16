# -*- coding: utf-8 -*-
"""带 CDP 端口 + 全量网络抓包的注册流程(专用于分析 Turnstile 失败原因)。
启动后打印 CDP 端口, 供外部用 websocket 连接抓包。
"""
import json
import logging
import sys
import time
import uuid
import threading
import websocket
import urllib.request

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

# 抓包事件收集
capture_events = []


def attach_capture(debug_port):
    """后台线程: 连接 CDP, 收集所有 Network 事件到文件。"""
    def worker():
        for attempt in range(30):
            try:
                r = urllib.request.urlopen(f'http://127.0.0.1:{debug_port}/json/list', timeout=2)
                targets = json.loads(r.read().decode())
                page = None
                for t in targets:
                    if t.get('type') == 'page':
                        page = t
                        break
                if not page:
                    time.sleep(1)
                    continue
                ws = websocket.create_connection(page['webSocketDebuggerUrl'], timeout=30)
                log.info('[capture] CDP connected: %s', page['url'][:80])
                mid = 0
                def send(method, params=None):
                    nonlocal mid
                    mid += 1
                    ws.send(json.dumps({'id': mid, 'method': method, 'params': params or {}}))
                    return mid
                def wait(mid_, timeout=15):
                    end = time.time() + timeout
                    while time.time() < end:
                        try:
                            ws.settimeout(0.4)
                            raw = ws.recv()
                        except Exception:
                            continue
                        if not raw:
                            continue
                        try:
                            msg = json.loads(raw)
                        except Exception:
                            continue
                        m = msg.get('method', '')
                        if msg.get('id') == mid_:
                            return msg
                        if m.startswith('Network.'):
                            capture_events.append(msg)
                            if m == 'Network.requestWillBeSent':
                                req = msg['params']['request']
                                url = req.get('url', '')
                                if ('ollama.com' in url or 'cloudflare.com' in url) and 'data:' not in url:
                                    log.info('[CAP] >>> %s %s', req.get('method'), url[:130])
                                    if req.get('postData'):
                                        log.info('[CAP]     BODY: %s', req['postData'][:400])
                            elif m == 'Network.responseReceived':
                                resp = msg['params']['response']
                                url = resp.get('url', '')
                                if ('ollama.com' in url or 'cloudflare.com' in url) and 'data:' not in url:
                                    log.info('[CAP] <<< %s %s', resp.get('status'), url[:130])
                    return None
                for dom in ['Network', 'Page', 'Runtime']:
                    wait(send(f'{dom}.enable'))
                # 保持连接
                while True:
                    time.sleep(30)
            except Exception as e:
                log.warning('[capture] retry: %s', str(e)[:80])
                time.sleep(2)
    t = threading.Thread(target=worker, daemon=True)
    t.start()


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
    log.info('>>> 请在浏览器窗口完成 Turnstile 人机验证')
    start = time.time()
    while time.time() - start < timeout:
        url = page.url
        if 'signin.ollama.com' not in url:
            log.info('页面已跳转: %s', url[:120])
            return True
        # 检查页面上的错误信息
        err = page.evaluate("""(() => {
            const els = document.querySelectorAll('[class*="Callout"], [data-type="error"]');
            for (const el of els) {
                const t = el.innerText || '';
                if (t) return t.slice(0, 200);
            }
            return '';
        })()""")
        if err:
            log.warning('页面错误: %s', err)
            # 不退出, 继续等 (可能只是瞬时)
        token = page.evaluate("""(() => {
            const el = document.querySelector('input[name="bot_detection_token"]');
            return el ? el.value : '';
        })()""")
        if token:
            log.info('Turnstile token 已获得, 自动重提...')
            page.evaluate("() => { const f = document.querySelector('form'); if (f) f.requestSubmit(); }")
            time.sleep(3)
            return True
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
        if debug_port:
            attach_capture(debug_port)
        ctx = browser.new_context(viewport={'width': 1400, 'height': 900}, locale='en-US')
        ctx.add_init_script(STEALTH)
        page = ctx.new_page()

        log.info('打开注册页...')
        page.goto(SIGNUP_URL, wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(3000)

        for i in range(30):
            if page.evaluate("() => !!document.querySelector('input[name=\"email\"]')"):
                break
            page.wait_for_timeout(2000)
        else:
            log.error('表单未加载')
            browser.close()
            return False

        auth_sid = page.evaluate(
            "() => document.querySelector('input[name=\"authorization_session_id\"]')?.value || ''")
        log.info('authorization_session_id: %s', auth_sid)

        fill_react_input(page, 'input[name="email"]', email)
        log.info('已填邮箱: %s', email)
        page.wait_for_timeout(1000)

        page.evaluate("() => document.querySelector('form').requestSubmit()")
        log.info('已提交邮箱, 等待 Turnstile #1...')
        ok1 = wait_turnstile_and_submit(page)
        if not ok1:
            log.error('Turnstile #1 未完成')
            browser.close()
            return False

        for i in range(30):
            url = page.url
            if 'password' in url:
                log.info('已进入密码页: %s', url[:100])
                break
            if 'ollama.com' in url and 'signin' not in url:
                log.info('直接跳到 ollama.com: %s', url[:100])
                browser.close()
                return True
            page.wait_for_timeout(2000)
        else:
            log.error('未跳转密码页, 当前: %s', page.url)
            browser.close()
            return False

        page.wait_for_timeout(2000)
        fill_react_input(page, 'input[name="password"]', password)
        log.info('已填密码')
        page.wait_for_timeout(1000)

        page.evaluate("() => document.querySelector('form').requestSubmit()")
        log.info('已提交密码, 等待 Turnstile #2...')
        ok2 = wait_turnstile_and_submit(page)
        if not ok2:
            log.error('Turnstile #2 未完成')
            browser.close()
            return False

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
    import os
    emails = []
    with open(r'C:\Users\Jackson\Desktop\email.txt', encoding='utf-8') as f:
        emails = [l.strip() for l in f if l.strip()]
    log.info('邮箱列表: %d 个', len(emails))
    email = emails[0]
    password = 'Ollama#2026!Secure'
    log.info('使用邮箱: %s', email)
    ok = run(email, password, debug_port=9337)
    log.info('结果: %s', '成功' if ok else '失败')
    # 保存抓包
    with open(r'D:\PRO\ollama-register\captures\cap-turnstile-fail.json', 'w', encoding='utf-8') as f:
        json.dump(capture_events, f, indent=1, default=str)
    log.info('抓包已保存: %d 事件', len(capture_events))


if __name__ == '__main__':
    main()
