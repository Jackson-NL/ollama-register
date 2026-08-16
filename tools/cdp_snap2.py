# -*- coding: utf-8 -*-
"""Screenshot + dump state to check if user completed turnstile."""
import json
import time
import urllib.request
import websocket
import base64

DEBUG_PORT = 9335

def main():
    r = urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json/list', timeout=3)
    targets = json.loads(r.read().decode())
    tgt = None
    for t in targets:
        if t.get('type') == 'page' and 'signin.ollama.com' in t.get('url', ''):
            tgt = t
            break
    if not tgt:
        print('no target')
        return
    ws = websocket.create_connection(tgt['webSocketDebuggerUrl'], timeout=20)

    mid = 0
    def send(method, params=None):
        nonlocal mid
        mid += 1
        ws.send(json.dumps({'id': mid, 'method': method, 'params': params or {}}))
        return mid

    def recv_until(mid_, timeout=10):
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
            if msg.get('id') == mid_:
                return msg
        return None

    send('Page.enable')
    send('Runtime.enable')
    time.sleep(1)
    # drain
    end = time.time() + 2
    while time.time() < end:
        try:
            ws.settimeout(0.2)
            ws.recv()
        except Exception:
            break

    # screenshot
    m = send('Page.captureScreenshot', {'format': 'png'})
    r = recv_until(m, 10)
    if r and 'result' in r:
        with open(r'D:\PRO\ollama-register\captures\cdp-check2.png', 'wb') as f:
            f.write(base64.b64decode(r['result']['data']))
        print('screenshot saved')

    # state
    expr = "JSON.stringify({url: location.href, title: document.title, token: (document.querySelector('input[name=bot_detection_token]')||{}).value||'', email: (document.querySelector('input[name=email]')||{}).value||'', tsDiv: !!document.getElementById('cf-turnstile'), tsIframe: !!document.querySelector('iframe[src*=challenges]'), bodyText: document.body.innerText.slice(0,300)})"
    m = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
    r = recv_until(m, 8)
    if r:
        print(r.get('result', {}).get('result', {}).get('value'))
    ws.close()

if __name__ == '__main__':
    main()
