# -*- coding: utf-8 -*-
"""Clean reload + natural Turnstile flow: navigate, fill, requestSubmit, observe, click."""
import json
import time
import urllib.request
import websocket
import uuid

DEBUG_PORT = 9335
SIGNUP_URL = ('https://signin.ollama.com/sign-up?client_id=client_01JX0QMHD43PFFCCNXH82A6K8B'
              '&redirect_uri=https%3A%2F%2Follama.com%2Fauth%2Fcallback&screen_hint=sign-up')

def find_page():
    r = urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json/list', timeout=3)
    targets = json.loads(r.read().decode())
    for t in targets:
        if t.get('type') == 'page' and 'scriptcat' not in t.get('url', '') and 'extension' not in t.get('url', ''):
            return t
    return None

def main():
    tgt = find_page()
    if not tgt:
        print('no page')
        return
    ws = websocket.create_connection(tgt['webSocketDebuggerUrl'], timeout=30)
    print('connected to', tgt['url'][:80])

    mid = 0
    def send(method, params=None):
        nonlocal mid
        mid += 1
        ws.send(json.dumps({'id': mid, 'method': method, 'params': params or {}}))
        return mid

    def ev(expr, timeout=10, await_promise=False):
        m = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True, 'awaitPromise': await_promise})
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
            if msg.get('id') == m:
                v = msg.get('result', {})
                if 'exceptionDetails' in v:
                    return 'EXC'
                return v.get('result', {}).get('value')
        return None

    def quiet(sec):
        end = time.time() + sec
        while time.time() < end:
            try:
                ws.settimeout(0.3)
                ws.recv()
            except Exception:
                continue

    send('Page.enable')
    send('Runtime.enable')
    quiet(1)

    print('navigating...')
    send('Page.navigate', {'url': SIGNUP_URL})
    quiet(5)

    # wait for page ready (email input present and title not "Just a moment")
    for i in range(30):
        title = ev('document.title') or ''
        has_input = ev('!!document.querySelector(\'input[name="email"]\')')
        if has_input and 'moment' not in title.lower():
            print(f'page ready after ~{i*2}s, title={title}')
            break
        quiet(2)
    else:
        print('!! page did not become ready')
        print('text:', (ev('document.body ? document.body.innerText.slice(0,300) : "")') or ''))
        return

    print('auth_sid:', ev("""(() => { var m = document.documentElement.outerHTML.match(/name="authorization_session_id" value="([^"]+)"/); return m ? m[1] : null; })()"""))

    # fill email
    email = 'regtest.' + uuid.uuid4().hex[:8] + '@mailinator.com'
    print('email:', email)
    print('fill:', ev(f"""(() => {{
        var el = document.querySelector('input[name="email"]');
        var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, '{email}');
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
        return 'OK';
    }})()"""))
    quiet(1)

    print('--- requestSubmit ---')
    print(ev("""(() => { document.querySelector('form').requestSubmit(); return 'submitted'; })()"""))

    # watch bot check
    for i in range(20):
        quiet(1)
        ts = ev('!!document.getElementById(\'cf-turnstile\')')
        iframe = ev("""(() => { var f = document.querySelector('iframe[src*="challenges.cloudflare.com"]'); return f ? f.src.slice(0,100) : null; })()""")
        disabled = ev('document.querySelector(\'button[type="submit"]\') ? document.querySelector(\'button[type="submit"]\').disabled : null')
        print(f'[{i}s] cf-turnstile={ts} iframe={iframe} submitDisabled={disabled}')
        if iframe:
            print('  >>> TURNSTILE IFRAME UP - clicking it')
            # get iframe rect and click center
            rect_s = ev("""(() => {
                var f = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
                if (!f) return null;
                var r = f.getBoundingClientRect();
                return JSON.stringify({x: r.x + r.width/2, y: r.y + r.height/2});
            })()""")
            print('  iframe center:', rect_s)
            if rect_s:
                rc = json.loads(rect_s)
                send('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': rc['x'], 'y': rc['y']})
                quiet(0.3)
                send('Input.dispatchMouseEvent', {'type': 'mousePressed', 'x': rc['x'], 'y': rc['y'], 'button': 'left', 'clickCount': 1})
                quiet(0.2)
                send('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'x': rc['x'], 'y': rc['y'], 'button': 'left', 'clickCount': 1})
                print('  clicked iframe center')
            break
        # if no iframe but turnstile div exists, click it
        if ts:
            rect_s = ev("""(() => {
                var el = document.getElementById('cf-turnstile');
                var r = el.getBoundingClientRect();
                return JSON.stringify({x: r.x + r.width/2, y: r.y + r.height/2});
            })()""")
            if rect_s:
                rc = json.loads(rect_s)
                send('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': rc['x'], 'y': rc['y']})
                quiet(0.2)
                send('Input.dispatchMouseEvent', {'type': 'mousePressed', 'x': rc['x'], 'y': rc['y'], 'button': 'left', 'clickCount': 1})
                quiet(0.2)
                send('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'x': rc['x'], 'y': rc['y'], 'button': 'left', 'clickCount': 1})
                print(f'  clicked cf-turnstile div at {rc["x"]},{rc["y"]}')

    # wait for token
    for i in range(15):
        quiet(1)
        token = ev('document.querySelector(\'input[name="bot_detection_token"]\') ? document.querySelector(\'input[name="bot_detection_token"]\').value : ""')
        url = ev('location.href') or ''
        print(f'[wait {i}s] token={token[:20] if token else ""} url={url[:90]}')
        if token:
            print('  >>> BOT TOKEN OBTAINED!')
            break
        if 'signin' not in url:
            print('  >>> NAVIGATED AWAY!')
            break

    quiet(2)
    html = ev('document.documentElement.outerHTML') or ''
    with open(r'D:\PRO\ollama-register\captures\cdp-flow5.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print('final url:', ev('location.href'))
    print('final text:', (ev('document.body ? document.body.innerText.slice(0,400) : "")') or ''))
    print('=== done ===')

if __name__ == '__main__':
    main()
