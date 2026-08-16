# -*- coding: utf-8 -*-
"""CDP submit v2: single-threaded message pump with event buffering."""
import json
import time
import urllib.request
import websocket
import re
import uuid
import queue

DEBUG_PORT = 9335
q = queue.Queue()   # all incoming messages
msg_id = 0

def pump():
    """Run in main thread: route incoming ws messages to queue."""
    global ws
    while True:
        try:
            ws.settimeout(0.5)
            raw = ws.recv()
        except Exception:
            continue
        if raw:
            try:
                q.put(json.loads(raw))
            except Exception:
                pass

def send(method, params=None):
    global msg_id
    msg_id += 1
    mid = msg_id
    payload = {'id': mid, 'method': method}
    if params:
        payload['params'] = params
    ws.send(json.dumps(payload))
    return mid

def wait_response(mid, timeout=15):
    """Read from queue until response with mid arrives; buffer events."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            msg = q.get(timeout=0.5)
        except queue.Empty:
            continue
        if msg.get('id') == mid:
            return msg
        if msg.get('method', '').startswith(('Network.', 'Page.')):
            events.append(msg)
    return None

def ev(expr, timeout=10):
    m = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
    r = wait_response(m, timeout)
    if r and 'result' in r and 'result' in r['result']:
        return r['result']['result'].get('value')
    return None

events = []
ws = None

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
    print('connected to', target['url'][:80])
    import threading
    threading.Thread(target=pump, daemon=True).start()
    for dom in ['Network', 'Page', 'Runtime']:
        wait_response(send(f'{dom}.enable'))

    email = 'regtest.' + uuid.uuid4().hex[:8] + '@mailinator.com'
    print('email:', email)
    ok = ev("""(() => {
        var el = document.querySelector('input[name="email"]');
        if (!el) return 'no email input';
        var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, arguments[0]);
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
        return 'filled: ' + el.value;
    })()""", )
    print('fill:', ok)
    time.sleep(1)

    btn = ev("""(() => {
        var btns = document.querySelectorAll('button[type="submit"]');
        if (!btns.length) return 'no submit button';
        return Array.from(btns).map(b => (b.innerText||'').trim().slice(0,30)).join(' | ');
    })()""")
    print('buttons:', btn)

    clicked = ev("""(() => {
        var btn = document.querySelector('button[type="submit"]');
        if (!btn) return 'no button';
        btn.click();
        return 'clicked';
    })()""")
    print('click:', clicked)

    print('waiting...')
    for i in range(25):
        time.sleep(2)
        url = ev('location.href') or ''
        print(f'[{i*2}s] url={url[:110]}')
        if 'ollama' in url and 'signin' not in url:
            break
        if 'password' in url or 'code' in url or 'otp' in url:
            break
    time.sleep(2)

    html = ev('document.documentElement.outerHTML') or ''
    with open(r'D:\PRO\ollama-register\captures\cdp-after-submit2.html', 'w', encoding='utf-8') as f:
        f.write(html)
    with open(r'D:\PRO\ollama-register\captures\cdp-network-submit2.json', 'w', encoding='utf-8') as f:
        json.dump(events, f, indent=1, default=str)
    print('events:', len(events))
    print('final url:', ev('location.href'))
    print('final text:', (ev('document.body ? document.body.innerText.slice(0,500) : ""') or ''))

if __name__ == '__main__':
    main()
