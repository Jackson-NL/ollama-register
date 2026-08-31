# -*- coding: utf-8 -*-
"""Watch turnstile state for auto-completion over 60s."""
import json
import time
import urllib.request
import websocket

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

    def ev(expr, timeout=8):
        m = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
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
                return msg.get('result', {}).get('result', {}).get('value')
        return None

    def quiet(sec):
        end = time.time() + sec
        while time.time() < end:
            try:
                ws.settimeout(0.3)
                ws.recv()
            except Exception:
                continue

    send('Runtime.enable')
    quiet(1)

    for i in range(30):
        quiet(2)
        iframe = ev("""(() => { var f = document.querySelector('iframe[src*="challenges.cloudflare.com"]'); return f ? f.src.slice(0,110) : null; })()""")
        token = ev('document.querySelector(\'input[name="bot_detection_token"]\') ? document.querySelector(\'input[name="bot_detection_token"]\').value : ""')
        ts = ev('!!document.getElementById(\'cf-turnstile\')')
        resp = ev("""(() => { try { return window.turnstile ? (window.turnstile.getResponse() || 'empty') : 'no-api'; } catch(e) { return 'err'; } })()""")
        status = 'IFRAME' if iframe else ('TOKEN!' if token else ('RESP:' + (resp or '')[:15]))
        print(f'[{i*2}s] turnstile={ts} {status}')
        if token:
            print('>>> TOKEN! Form will submit automatically or we can submit manually.')
            break
    ws.close()

if __name__ == '__main__':
    main()
