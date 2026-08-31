# -*- coding: utf-8 -*-
"""Check automation fingerprints in playwright browser."""
import json
import time
import urllib.request
import websocket

DEBUG_PORT = 9337

def main():
    r = urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json/list', timeout=3)
    targets = json.loads(r.read().decode())
    tgt = None
    for t in targets:
        if t.get('type') == 'page':
            tgt = t
            break
    if not tgt:
        print('no page')
        return
    ws = websocket.create_connection(tgt['webSocketDebuggerUrl'], timeout=15)
    mid = 0
    def send(method, params=None):
        nonlocal mid
        mid += 1
        ws.send(json.dumps({'id': mid, 'method': method, 'params': params or {}}))
        return mid
    def ev(expr, timeout=6):
        m = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
        end = time.time() + timeout
        while time.time() < end:
            try:
                ws.settimeout(0.3)
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
    send('Runtime.enable')
    time.sleep(0.5)
    end = time.time() + 2
    while time.time() < end:
        try:
            ws.settimeout(0.2)
            ws.recv()
        except Exception:
            break

    checks = {
        'navigator.webdriver': 'navigator.webdriver',
        'window.chrome': 'typeof window.chrome',
        'window.chrome.runtime': 'typeof (window.chrome && window.chrome.runtime)',
        'navigator.plugins.length': 'navigator.plugins.length',
        'navigator.languages': 'JSON.stringify(navigator.languages)',
        'userAgent': 'navigator.userAgent',
        'appVersion': 'navigator.appVersion',
        'cdc_ props': """(() => { var n=0; for (var k in window) { if (k.startsWith('$cdc_') || k.startsWith('cdc_')) n++; } return n; })()""",
        '__playwright props': """(() => { var n=0; for (var k in window) { if (k.indexOf('playwright')>=0 || k.indexOf('__pw')>=0) n++; } return n; })()""",
        'permissions': """(() => { try { return typeof navigator.permissions; } catch(e) { return 'err'; } })()""",
        'hardwareConcurrency': 'navigator.hardwareConcurrency',
    }
    for name, expr in checks.items():
        print(f'{name}: {ev(expr)}')
    ws.close()

if __name__ == '__main__':
    main()
