# -*- coding: utf-8 -*-
"""CDP drive v2: wait out the Cloudflare managed challenge, then capture the real page."""
import json
import time
import subprocess
import urllib.request
import websocket
import threading
import re
import os

EDGE = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
USER_DATA = os.path.join(os.environ.get('TEMP', r'C:\Windows\Temp'), 'dsh-ollama-edge2')
DEBUG_PORT = 9334
SIGNUP_URL = ('https://signin.ollama.com/sign-up?client_id=client_01JX0QMHD43PFFCCNXH82A6K8B'
              '&redirect_uri=https%3A%2F%2Follama.com%2Fauth%2Fcallback&screen_hint=sign-up')

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

def eval_js(expr, timeout=10):
    mid = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
    r = wait_response(mid, timeout)
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
        if m == 'Network.requestWillBeSent':
            req = msg['params']['request']
            p = msg['params']
            print(f">>> {p.get('type','?')} {req.get('method')} {req.get('url','')[:130]}")
        elif m == 'Network.responseReceived':
            resp = msg['params']['response']
            print(f"<<< {resp.get('status')} {msg['params'].get('type','?')} {resp.get('url','')[:130]}")
        if m.startswith('Network.') or m.startswith('Page.'):
            events.append(msg)

def main():
    global ws
    # kill stale
    os.system('taskkill /F /IM msedge.exe /FI "WINDOWTITLE eq *" >nul 2>&1')
    # remove old profile
    import shutil
    if os.path.exists(USER_DATA):
        shutil.rmtree(USER_DATA, ignore_errors=True)

    print('=== launching Edge ===')
    subprocess.Popen([
        EDGE,
        f'--remote-debugging-port={DEBUG_PORT}',
        f'--user-data-dir={USER_DATA}',
        '--remote-allow-origins=*',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-popup-blocking',
        'about:blank',
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    target = None
    for i in range(40):
        try:
            r = urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json/list', timeout=2)
            targets = json.loads(r.read().decode())
            for t in targets:
                if t.get('type') == 'page' and t.get('url', '').startswith('about'):
                    target = t
                    break
            if not target:
                for t in targets:
                    if t.get('type') == 'page':
                        target = t
                        break
            if target:
                break
        except Exception:
            pass
        time.sleep(1)
    if not target:
        print('!! no target')
        return

    ws = websocket.create_connection(target['webSocketDebuggerUrl'], timeout=30)
    print('ws connected')
    threading.Thread(target=collector, daemon=True).start()
    for dom in ['Network', 'Page', 'Runtime']:
        wait_response(send(f'{dom}.enable'))
    print('domains enabled')

    mid = send('Page.navigate', {'url': SIGNUP_URL})
    wait_response(mid, 20)
    print('navigated')

    # wait until challenge clears: poll for presence of "Just a moment" or real title
    for i in range(60):
        time.sleep(3)
        title = eval_js('document.title')
        url = eval_js('location.href')
        has_moment = eval_js('document.body && document.body.innerText.includes("Just a moment")')
        print(f'[{i*3}s] title={title!r} url={url[:80] if url else None!r} has_moment={has_moment}')
        if title and 'Just a moment' not in title and has_moment is False:
            break

    # dump final state
    html = eval_js('document.documentElement.outerHTML') or ''
    with open(r'D:\PRO\ollama-register\captures\cdp-page2.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print('final html saved:', len(html))
    m = re.search(r'name="authorization_session_id" value="([^"]+)"', html)
    print('AUTH_SID in DOM:', m.group(1) if m else None)
    txt = eval_js('document.body ? document.body.innerText : ""') or ''
    print('PAGE TEXT:', txt[:600])

    time.sleep(2)
    with open(r'D:\PRO\ollama-register\captures\cdp-network2.json', 'w', encoding='utf-8') as f:
        json.dump(events, f, indent=1)
    print('events saved:', len(events))
    print('=== done. Edge stays open on port', DEBUG_PORT, '===')

if __name__ == '__main__':
    main()
