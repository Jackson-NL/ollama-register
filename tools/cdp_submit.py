# -*- coding: utf-8 -*-
"""CDP full register attempt: fill email, click submit, capture all network requests.
Attaches to existing signin.ollama.com page, enables Network domain, then submits.
"""
import json
import time
import urllib.request
import websocket
import threading
import re
import uuid

DEBUG_PORT = 9335
events = []
ws = None
msg_id = 0
lock = threading.Lock()

def send(method, params=None):
    global msg_id
    with lock:
        msg_id += 1
        mid = msg_id
    payload = {'id': mid, 'method': method}
    if params:
        payload['params'] = params
    ws.send(json.dumps(payload))
    return mid

def wait_response(mid, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            ws.settimeout(0.5)
            raw = ws.recv()
        except Exception:
            continue
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except Exception:
            continue
        if msg.get('id') == mid:
            return msg
    return None

def ev(expr, timeout=10):
    m = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
    r = wait_response(m, timeout)
    if r and 'result' in r and 'result' in r['result']:
        return r['result']['result'].get('value')
    return None

def collector():
    global ws
    while True:
        try:
            ws.settimeout(1.0)
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
        if m.startswith('Network.') or m.startswith('Page.'):
            events.append(msg)
            if m == 'Network.requestWillBeSent':
                req = msg['params']['request']
                url = req.get('url', '')
                if 'ollama.com' in url and 'signals' not in url:
                    print(f">>> {req.get('method')} {url[:150]}")
                    ph = req.get('postData', '')
                    if ph:
                        print(f"    POSTDATA: {ph[:400]}")
            elif m == 'Network.responseReceived':
                resp = msg['params']['response']
                url = resp.get('url', '')
                if 'ollama.com' in url:
                    print(f"<<< {resp.get('status')} {url[:150]}")

def find_signin_target():
    r = urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json/list', timeout=3)
    targets = json.loads(r.read().decode())
    for t in targets:
        if 'signin.ollama.com' in t.get('url', ''):
            return t
    return None

def main():
    global ws
    target = find_signin_target()
    if not target:
        print('!! no signin target')
        return
    ws = websocket.create_connection(target['webSocketDebuggerUrl'], timeout=30)
    print('connected')
    threading.Thread(target=collector, daemon=True).start()
    for dom in ['Network', 'Page', 'Runtime']:
        wait_response(send(f'{dom}.enable'))

    # fill email
    email = 'regtest.' + uuid.uuid4().hex[:8] + '@mailinator.com'
    print('email:', email)
    ok = ev(f'''(() => {{
        var el = document.querySelector('input[name="email"]');
        if (!el) return 'no email input';
        var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, '{email}');
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
        return 'filled: ' + el.value;
    }})()''')
    print('fill result:', ok)
    time.sleep(1)

    # click the submit button (Continue with email)
    btn = ev('''(() => {
        var btns = document.querySelectorAll('button[type="submit"]');
        if (!btns.length) return 'no submit button';
        return btns.length + ' submit buttons: ' + Array.from(btns).map(b => b.innerText.trim().slice(0,30)).join(' | ');
    })()''')
    print('buttons:', btn)

    clicked = ev('''(() => {
        var btn = document.querySelector('button[type="submit"]');
        if (!btn) return 'no button';
        btn.click();
        return 'clicked';
    })()''')
    print('click:', clicked)

    # wait for network activity / page change
    print('waiting for response...')
    for i in range(30):
        time.sleep(2)
        url = ev('location.href') or ''
        txt = ev('document.body ? document.body.innerText.slice(0,200) : ""') or ''
        print(f'[{i*2}s] url={url[:100]}')
        if 'code' in url or 'otp' in url or 'password' in url.lower() or 'set-password' in url:
            break
        if 'signin' not in url and 'ollama' not in url:
            break
        # check for error/next-step text
        if txt.strip():
            pass
    time.sleep(3)

    # dump everything
    html = ev('document.documentElement.outerHTML') or ''
    with open(r'D:\PRO\ollama-register\captures\cdp-after-submit.html', 'w', encoding='utf-8') as f:
        f.write(html)
    with open(r'D:\PRO\ollama-register\captures\cdp-network-submit.json', 'w', encoding='utf-8') as f:
        json.dump(events, f, indent=1, default=str)
    print('saved html + network events:', len(events))
    print('final URL:', ev('location.href'))
    print('final TEXT:', (ev('document.body ? document.body.innerText.slice(0,400) : ""') or ''))

if __name__ == '__main__':
    main()
