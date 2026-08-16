# -*- coding: utf-8 -*-
"""CDP submit v3: fully single-threaded, reliable."""
import json
import time
import urllib.request
import websocket
import re
import uuid
import sys

DEBUG_PORT = 9335
events = []

def connect_signin():
    r = urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json/list', timeout=3)
    targets = json.loads(r.read().decode())
    for t in targets:
        if 'signin.ollama.com' in t.get('url', ''):
            return websocket.create_connection(t['webSocketDebuggerUrl'], timeout=30)
    return None

def main():
    ws = connect_signin()
    if not ws:
        print('!! no signin target')
        return
    print('connected')

    mid = 0
    def send(method, params=None):
        nonlocal mid
        mid += 1
        payload = {'id': mid, 'method': method, 'params': params or {}}
        ws.send(json.dumps(payload))
        return mid

    def wait(mid_, timeout=15):
        """Single-threaded: recv until response with mid_ arrives; buffer Network events."""
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
            m = msg.get('method', '')
            if msg.get('id') == mid_:
                return msg
            if m.startswith('Network.') or m.startswith('Page.'):
                events.append(msg)
                if m == 'Network.requestWillBeSent':
                    req = msg['params']['request']
                    url = req.get('url', '')
                    if 'ollama.com' in url and 'data:' not in url:
                        print(f">>> {req.get('method')} {url[:140]}")
                        if req.get('postData'):
                            print(f"    BODY: {req['postData'][:500]}")
                elif m == 'Network.responseReceived':
                    resp = msg['params']['response']
                    url = resp.get('url', '')
                    if 'ollama.com' in url:
                        print(f"<<< {resp.get('status')} {url[:140]}")
        return None

    def ev(expr, timeout=10):
        m = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
        r = wait(m, timeout)
        if r and 'result' in r and 'result' in r['result']:
            return r['result']['result'].get('value')
        return None

    for dom in ['Network', 'Page', 'Runtime']:
        wait(send(f'{dom}.enable'))

    print('--- page state ---')
    print('title:', ev('document.title'))
    print('has email:', ev('!!document.querySelector(\'input[name="email"]\')'))

    email = 'regtest.' + uuid.uuid4().hex[:8] + '@mailinator.com'
    print('email to fill:', email)
    fill_expr = f"""(() => {{
        var el = document.querySelector('input[name="email"]');
        if (!el) return 'NO_INPUT';
        var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, '{email}');
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
        return 'OK:' + el.value;
    }})()"""
    print('fill:', ev(fill_expr))
    time.sleep(1)

    print('--- clicking submit ---')
    click_expr = """(() => {
        var btn = document.querySelector('button[type="submit"]');
        if (!btn) return 'NO_BUTTON';
        btn.click();
        return 'CLICKED';
    })()"""
    print('click:', ev(click_expr))

    print('--- waiting for network activity ---')
    time.sleep(6)

    print('--- final state ---')
    print('url:', ev('location.href'))
    print('text:', (ev('document.body ? document.body.innerText.slice(0,600) : ""') or ''))

    html = ev('document.documentElement.outerHTML') or ''
    with open(r'D:\PRO\ollama-register\captures\cdp-after3.html', 'w', encoding='utf-8') as f:
        f.write(html)
    with open(r'D:\PRO\ollama-register\captures\cdp-network3.json', 'w', encoding='utf-8') as f:
        json.dump(events, f, indent=1, default=str)
    print('events captured:', len(events))
    print('=== done ===')

if __name__ == '__main__':
    main()
