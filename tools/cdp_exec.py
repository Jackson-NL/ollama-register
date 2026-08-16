# -*- coding: utf-8 -*-
"""Check turnstile.getResponse() - if token exists, inject and submit."""
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

    def ev(expr, timeout=10, await_promise=False):
        m = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True, 'awaitPromise': await_promise})
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

    print('--- turnstile getResponse (no arg = all widgets) ---')
    print('resp:', ev("""(() => {
        if (typeof window.turnstile === 'undefined') return 'no api';
        try { return window.turnstile.getResponse() || 'empty'; } catch(e) { return 'err: ' + e.message; }
    })()"""))

    # check if token input exists; if not, check React state via form
    print('bot token input:', ev('!!document.querySelector(\'input[name="bot_detection_token"]\')'))

    # try to get widget id list
    print('widgets:', ev("""(() => {
        if (typeof window.turnstile === 'undefined') return 'no api';
        var out = [];
        var all = document.querySelectorAll('.cf-turnstile, #cf-turnstile, [data-turnstile-widget]');
        all.forEach(function(el) { out.push(el.id || el.className); });
        return out.join(',') || 'no containers';
    })()"""))

    # Execute turnstile programmatically: render and wait for token via callback
    print('--- programmatic execute ---')
    result = ev("""(async () => {
        if (typeof window.turnstile === 'undefined') return 'no api';
        return new Promise(function(resolve) {
            var el = document.getElementById('cf-turnstile');
            if (!el) { resolve('no container'); return; }
            try {
                var wid = window.turnstile.render(el, {
                    sitekey: '0x4AAAAAAAMNIvC45A4Wjjln',
                    action: 'sign-in',
                    callback: function(token) { resolve('TOKEN:' + token.slice(0, 60)); },
                    'error-callback': function(code) { resolve('ERROR:' + code); },
                    'expired-callback': function() { resolve('EXPIRED'); },
                    'timeout-callback': function() { resolve('TIMEOUT'); },
                });
                window.__wid = wid;
                // also set a timeout fallback
                setTimeout(function() { resolve('WAITING... widget=' + wid); }, 15000);
            } catch(e) { resolve('render err: ' + e.message); }
        });
    })()""", await_promise=True)
    print('execute result:', result)

    quiet(2)
    print('iframe now:', ev("""(() => { var f = document.querySelector('iframe[src*="challenges.cloudflare.com"]'); return f ? f.src.slice(0,100) : 'none'; })()"""))
    ws.close()

if __name__ == '__main__':
    main()
