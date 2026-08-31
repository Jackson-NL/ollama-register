# -*- coding: utf-8 -*-
"""Deep inspect: console logs, all elements with turnstile/challenge, shadow DOM."""
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
    logs = []
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
            if msg.get('method') == 'Runtime.consoleAPICalled':
                try:
                    args = [a.get('value', a.get('description', '')) for a in msg['params']['args']]
                    logs.append('[console.' + msg['params']['type'] + '] ' + ' '.join(str(a) for a in args)[:200])
                except Exception:
                    pass
            if msg.get('method') == 'Runtime.exceptionThrown':
                try:
                    logs.append('[EXCEPTION] ' + json.dumps(msg['params']['exceptionDetails'])[:300])
                except Exception:
                    pass
        return None

    def quiet(sec):
        end = time.time() + sec
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
            if msg.get('method') == 'Runtime.consoleAPICalled':
                try:
                    args = [a.get('value', a.get('description', '')) for a in msg['params']['args']]
                    logs.append('[console.' + msg['params']['type'] + '] ' + ' '.join(str(a) for a in args)[:200])
                except Exception:
                    pass
            if msg.get('method') == 'Runtime.exceptionThrown':
                try:
                    logs.append('[EXCEPTION] ' + json.dumps(msg['params']['exceptionDetails'])[:300])
                except Exception:
                    pass

    send('Runtime.enable')
    send('Log.enable')
    quiet(1)

    print('--- all elements containing turnstile/challenge in tag/id/class/src ---')
    print(ev("""(() => {
        var out = [];
        var all = document.querySelectorAll('*');
        all.forEach(function(el) {
            var id = el.id || '';
            var cls = typeof el.className === 'string' ? el.className : '';
            var src = el.src || '';
            if (id.indexOf('turnstile') >= 0 || cls.indexOf('turnstile') >= 0 || cls.indexOf('cf-') >= 0 || src.indexOf('challenges') >= 0) {
                out.push(el.tagName + '#' + id + '.' + cls.slice(0,50) + ' src=' + src.slice(0,60) + ' html=' + el.innerHTML.slice(0,100));
            }
        });
        return out.slice(0, 25).join('\\n') || 'none';
    })()"""))

    print('--- check shadow roots ---')
    print(ev("""(() => {
        var out = [];
        var all = document.querySelectorAll('*');
        all.forEach(function(el) {
            if (el.shadowRoot) out.push(el.tagName + '#' + (el.id||'') + ' has shadowRoot, children=' + el.shadowRoot.childNodes.length);
        });
        return out.join('\\n') || 'no shadow roots';
    })()"""))

    print('--- turnstile script tag state ---')
    print(ev("""(() => {
        var s = document.getElementById('cf-turnstile-script');
        return s ? 'exists, readyState=' + (s.readyState||'n/a') + ', src=' + (s.src||'').slice(0,80) : 'no script tag';
    })()"""))

    print('--- window.turnstile.render called? patch check ---')
    print(ev("""(() => {
        if (typeof window.turnstile === 'undefined') return 'no api';
        return 'render exists: ' + (typeof window.turnstile.render);
    })()"""))

    print('--- body text full ---')
    print((ev('document.body ? document.body.innerText : "")') or ''))

    print('--- console logs ---')
    for l in logs[-25:]:
        print(' ', l)
    if not logs:
        print('  (no console logs captured)')

    ws.close()

if __name__ == '__main__':
    main()
