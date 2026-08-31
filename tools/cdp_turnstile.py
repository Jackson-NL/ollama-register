# -*- coding: utf-8 -*-
"""Inspect Turnstile / bot check state on the page."""
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
    # drain
    end = time.time() + 2
    while time.time() < end:
        try:
            ws.settimeout(0.2)
            ws.recv()
        except Exception:
            break

    print('--- turnstile check ---')
    print('turnstile script:', ev('!!document.querySelector(\'script[src*="turnstile"]\')'))
    print('turnstile iframe:', ev('!!document.querySelector(\'iframe[src*="challenges.cloudflare.com"]\')'))
    print('window.turnstile:', ev('typeof window.turnstile'))
    print('bot_check text:', ev('document.body.innerText.includes("human") || document.body.innerText.includes("\\u771f\\u4eba")'))

    # find all iframes
    print('iframes:', ev("""(() => { var r=[]; document.querySelectorAll('iframe').forEach(function(f){ r.push(f.src.slice(0,120)); }); return r.join('\\n'); })()"""))

    # look for the bot check container
    print('ak-botcheck:', ev('!!document.querySelector(\'[class*="BotCheck"], [class*="bot-check"]\')'))

    # what does the page look like - find all visible buttons
    print('buttons:', ev("""(() => { var r=[]; document.querySelectorAll('button').forEach(function(b){ if (b.offsetParent !== null) r.push((b.innerText||'').trim().slice(0,40)); }); return r.join('\\n'); })()"""))

    # check form
    print('form action:', ev('document.querySelector(\'form\') ? document.querySelector(\'form\').getAttribute(\'action\') : "no form"'))
    print('form innerHTML sample:', ev('document.querySelector(\'form\') ? document.querySelector(\'form\').innerHTML.slice(0,600) : "no form"'))

    ws.close()

if __name__ == '__main__':
    main()
