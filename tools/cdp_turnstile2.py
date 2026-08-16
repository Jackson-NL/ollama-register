# -*- coding: utf-8 -*-
"""Check turnstile render state and widget visibility."""
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
        if 'signin.ollama.com' in t.get('url', ''):
            tgt = t
            break
    if not tgt:
        print('no signin target')
        return
    ws = websocket.create_connection(tgt['webSocketDebuggerUrl'], timeout=15)

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

    print('--- turnstile container ---')
    print(ev("""(() => {
        var el = document.querySelector('.cf-turnstile');
        if (!el) return 'none';
        return 'id=' + (el.id||'') + ' innerHTML.len=' + el.innerHTML.length + ' html=' + el.outerHTML.slice(0, 400);
    })()"""))

    print('--- window.turnstile functions ---')
    print(ev("""(() => {
        if (typeof window.turnstile === 'undefined') return 'no turnstile';
        return Object.keys(window.turnstile).join(',');
    })()"""))

    print('--- widget count via turnstile API ---')
    print(ev("""(() => {
        if (typeof window.turnstile === 'undefined') return 'no api';
        try {
            var w = window.turnstile.getResponse();
            return 'getResponse=' + (w ? w.slice(0,20) : 'empty');
        } catch(e) { return 'err: ' + e.message; }
    })()"""))

    print('--- submit button state ---')
    print(ev("""(() => {
        var b = document.querySelector('button[type="submit"]');
        if (!b) return 'no btn';
        return 'disabled=' + b.disabled + ' text=' + (b.innerText||'').trim().slice(0,30) + ' data=' + (b.getAttribute('data-loading')||'');
    })()"""))

    print('--- email field value ---')
    print(ev('document.querySelector(\'input[name="email"]\') ? document.querySelector(\'input[name="email"]\').value : "no email"'))

    ws.close()

if __name__ == '__main__':
    main()
