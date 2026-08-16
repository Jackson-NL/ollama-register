# -*- coding: utf-8 -*-
"""Screenshot via CDP + check turnstile container internals."""
import json
import time
import urllib.request
import websocket
import base64
import os

DEBUG_PORT = 9335
OUT = r'D:\PRO\ollama-register\captures\cdp-check3.png'

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
    if r and 'result' in r and 'data' in r['result']:
        with open(OUT, 'wb') as f:
            f.write(base64.b64decode(r['result']['data']))
        print('screenshot saved:', os.path.getsize(OUT))
    else:
        print('screenshot failed:', r)

    # turnstile container internal
    expr = """(() => {
        const el = document.getElementById('cf-turnstile');
        if (!el) return 'no container';
        const r = el.getBoundingClientRect();
        const children = Array.from(el.querySelectorAll('*')).map(c => c.tagName + '.' + (c.className||'').toString().slice(0,30)).slice(0,10);
        const elAtCenter = document.elementFromPoint(r.x + r.width/2, r.y + r.height/2);
        return JSON.stringify({
            rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
            innerHTML: el.innerHTML.slice(0, 300),
            children: children,
            elAtCenter: elAtCenter ? elAtCenter.tagName + '.' + (elAtCenter.className||'').toString().slice(0,30) : 'null'
        });
    })()"""
    m = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
    r = recv_until(m, 8)
    if r:
        print('container:', r.get('result', {}).get('result', {}).get('value'))
    ws.close()

if __name__ == '__main__':
    main()
