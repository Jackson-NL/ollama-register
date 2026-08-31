# -*- coding: utf-8 -*-
"""Try to complete Turnstile: click widget or execute API, then submit."""
import json
import time
import urllib.request
import websocket

DEBUG_PORT = 9335
SIGNIN_TARGET_PREFIX = '37A2DBA43752A37FB0E7776798A9FCDF'

def main():
    r = urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json/list', timeout=3)
    targets = json.loads(r.read().decode())
    tgt = None
    for t in targets:
        if SIGNIN_TARGET_PREFIX in t.get('webSocketDebuggerUrl', ''):
            tgt = t
            break
    if not tgt:
        print('!! target gone')
        return
    ws = websocket.create_connection(tgt['webSocketDebuggerUrl'], timeout=20)
    print('connected')

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

    send('Runtime.enable')
    time.sleep(0.5)
    end = time.time() + 2
    while time.time() < end:
        try:
            ws.settimeout(0.2)
            ws.recv()
        except Exception:
            break

    print('--- current bot check DOM ---')
    print(ev("""(() => {
        var out = [];
        document.querySelectorAll('*').forEach(function(el) {
            var cls = typeof el.className === 'string' ? el.className : '';
            if (cls.indexOf('turnstile') >= 0 || cls.indexOf('cf-') === 0 || (el.id||'').indexOf('turnstile') >= 0) {
                out.push(el.tagName + '#' + el.id + '.' + cls.slice(0,60));
            }
        });
        return out.slice(0, 20).join('\\n') || 'no turnstile elements';
    })()"""))

    print('--- iframe list ---')
    print(ev("""(() => {
        var r = [];
        document.querySelectorAll('iframe').forEach(function(f) { r.push((f.src||'').slice(0,130)); });
        return r.join('\\n') || 'none';
    })()"""))

    print('--- try clicking any visible turnstile widget ---')
    print(ev("""(() => {
        var els = document.querySelectorAll('[class*="turnstile"] iframe, iframe[src*="challenges"], .cf-turnstile, #cf-turnstile');
        var found = [];
        els.forEach(function(el) {
            var r = el.getBoundingClientRect();
            found.push(el.tagName + ' rect=' + Math.round(r.x) + ',' + Math.round(r.y) + ' ' + Math.round(r.width) + 'x' + Math.round(r.height) + ' visible=' + (r.width > 0));
        });
        return found.join('\\n') || 'none found';
    })()"""))

    # try turnstile.execute on the widget
    print('--- turnstile.execute attempt ---')
    print(ev("""(async () => {
        if (typeof window.turnstile === 'undefined') return 'no turnstile api';
        try {
            // find widget id from container
            var container = document.querySelector('.cf-turnstile, #cf-turnstile, [data-turnstile-widget]');
            if (!container) return 'no container';
            var token = await window.turnstile.execute(container);
            return 'token: ' + (token ? token.slice(0, 30) : 'null');
        } catch(e) { return 'err: ' + e.message; }
    })()"""))

    ws.close()

if __name__ == '__main__':
    main()
