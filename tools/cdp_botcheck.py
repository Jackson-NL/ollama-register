# -*- coding: utf-8 -*-
"""Inspect bot-check / turnstile render state in live DOM."""
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

    print('--- full page structure around bot check ---')
    print(ev("""(() => {
        var out = [];
        var all = document.querySelectorAll('div, section, form');
        all.forEach(function(el) {
            var cls = el.className || '';
            if (typeof cls === 'string' && (cls.indexOf('ak-') === 0 || cls.indexOf('BotCheck') >= 0 || cls.indexOf('bot') >= 0)) {
                out.push(el.tagName + '.' + cls.slice(0, 80));
            }
        });
        return out.slice(0, 30).join('\\n');
    })()"""))

    print('--- visible text blocks ---')
    print(ev("""(() => {
        var out = [];
        document.querySelectorAll('p, h1, h2, span').forEach(function(el) {
            if (el.offsetParent !== null) {
                var t = (el.innerText || '').trim();
                if (t && t.length > 1) out.push(t.slice(0, 60));
            }
        });
        return out.slice(0, 25).join('\\n');
    })()"""))

    print('--- turnstile widget element ---')
    print('cf-turnstile div:', ev('!!document.querySelector(\'.cf-turnstile, [id="cf-turnstile"]\')'))
    print('all iframes:', ev("""(() => { var r=[]; document.querySelectorAll('iframe').forEach(function(f){ r.push((f.src||'').slice(0,100)); }); return r.join('\\n') || 'none'; })()"""))
    print('bot_detection_token input:', ev('!!document.querySelector(\'input[name="bot_detection_token"]\')'))

    # get site key from page data if present
    print('sitekey in dom:', ev("""(() => {
        var m = document.documentElement.outerHTML.match(/siteKey[^,]{0,60}/g);
        return m ? m.slice(0,5).join('\\n') : 'none';
    })()"""))

    ws.close()

if __name__ == '__main__':
    main()
