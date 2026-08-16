# -*- coding: utf-8 -*-
"""Inspect turnstile render with explicit callbacks to capture 600010 details."""
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
    def ev(expr, timeout=8):
        m = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True, 'awaitPromise': True})
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
    send('Runtime.enable')
    time.sleep(0.5)
    end = time.time() + 2
    while time.time() < end:
        try:
            ws.settimeout(0.2)
            ws.recv()
        except Exception:
            break

    print('container:', ev("""(() => {
        const el = document.getElementById('cf-turnstile');
        return el ? el.outerHTML.slice(0, 400) : 'none';
    })()"""))
    print('script src:', ev("""(() => {
        const s = document.getElementById('cf-turnstile-script');
        return s ? s.src : 'none';
    })()"""))
    print('ts keys:', ev("""(() => {
        return typeof window.turnstile !== 'undefined' ? Object.keys(window.turnstile).join(',') : 'no api';
    })()"""))

    print('render attempt:', ev("""(() => {
        if (typeof window.turnstile === 'undefined') return 'no api';
        const el = document.getElementById('cf-turnstile');
        if (!el) return 'no el';
        try {
            const wid = window.turnstile.render(el, {
                sitekey: '0x4AAAAAAAMNIvC45A4Wjjln',
                action: 'sign-in',
                appearance: 'interaction-only',
                'error-callback': function(code) { window.__ts_err = code; },
                callback: function(token) { window.__ts_tok = token; }
            });
            return 'widget: ' + wid;
        } catch(e) { return 'render err: ' + e.message; }
    })()"""))

    time.sleep(4)
    print('err after render:', ev('window.__ts_err || "none"'))
    print('tok after render:', ev('window.__ts_tok ? window.__ts_tok.slice(0,30) : "none"'))
    ws.close()

if __name__ == '__main__':
    main()
