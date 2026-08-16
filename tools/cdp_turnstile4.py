# -*- coding: utf-8 -*-
"""Inspect cf-turnstile div and render widget explicitly."""
import json
import time
import urllib.request
import websocket

DEBUG_PORT = 9335
TARGET = '37A2DBA43752A37FB0E7776798A9FCDF'

def main():
    r = urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json/list', timeout=3)
    targets = json.loads(r.read().decode())
    tgt = None
    for t in targets:
        if TARGET in t.get('webSocketDebuggerUrl', ''):
            tgt = t
            break
    if not tgt:
        print('!! target gone')
        return
    ws = websocket.create_connection(tgt['webSocketDebuggerUrl'], timeout=20)

    mid = 0
    def send(method, params=None):
        nonlocal mid
        mid += 1
        ws.send(json.dumps({'id': mid, 'method': method, 'params': params or {}}))
        return mid

    def ev(expr, timeout=10):
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
                    return 'EXC: ' + json.dumps(v['exceptionDetails'])[:200]
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

    print('--- cf-turnstile div outerHTML ---')
    print(ev("""(() => {
        var el = document.getElementById('cf-turnstile');
        return el ? el.outerHTML.slice(0, 500) : 'none';
    })()"""))

    print('--- explicit render attempt ---')
    print(ev("""(() => {
        if (typeof window.turnstile === 'undefined') return 'no api';
        var el = document.getElementById('cf-turnstile');
        if (!el) return 'no el';
        try {
            var wid = window.turnstile.render(el, {
                sitekey: '0x4AAAAAAAMNIvC45A4Wjjln',
                action: 'sign-in',
                appearance: 'interaction-only',
                callback: function(token) { window.__ts_token = token; },
                'error-callback': function() { window.__ts_err = true; }
            });
            return 'widget id: ' + wid;
        } catch(e) { return 'err: ' + e.message; }
    })()"""))

    time.sleep(4)
    print('--- after render ---')
    print('iframe count:', ev("""(() => {
        var r = [];
        document.querySelectorAll('iframe').forEach(function(f) { r.push((f.src||'').slice(0,120)); });
        return r.join('\\n') || 'none';
    })()"""))
    print('token:', ev('window.__ts_token ? window.__ts_token.slice(0,40) : "none"'))
    print('err:', ev('window.__ts_err ? "yes" : "no"'))

    ws.close()

if __name__ == '__main__':
    main()
