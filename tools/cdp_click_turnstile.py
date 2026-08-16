# -*- coding: utf-8 -*-
"""Click the turnstile widget with real mouse events via CDP."""
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

    # get widget clickable area - find the actual checkbox inside cf-turnstile
    rect = ev("""(() => {
        var el = document.getElementById('cf-turnstile');
        if (!el) return null;
        var r = el.getBoundingClientRect();
        // find clickable child
        var clickable = el.querySelector('div, button, iframe');
        var cr = clickable ? clickable.getBoundingClientRect() : r;
        return JSON.stringify({x: cr.x + cr.width/2, y: cr.y + cr.height/2, w: cr.width, h: cr.height});
    })()""")
    print('widget center:', rect)
    if not rect:
        print('no rect')
        return
    rc = json.loads(rect)
    x, y = rc['x'], rc['y']

    # dispatch real mouse events
    send('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': x, 'y': y})
    time.sleep(0.3)
    send('Input.dispatchMouseEvent', {'type': 'mousePressed', 'x': x, 'y': y, 'button': 'left', 'clickCount': 1})
    time.sleep(0.2)
    send('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'x': x, 'y': y, 'button': 'left', 'clickCount': 1})
    print('clicked at', x, y)

    # wait and check for iframe
    for i in range(15):
        time.sleep(2)
        iframe = ev("""(() => {
            var f = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
            return f ? f.src.slice(0, 140) : null;
        })()""")
        token = ev('window.__ts_token ? window.__ts_token.slice(0,30) : null')
        print(f'[{i*2}s] iframe={iframe is not None} token={token}')
        if iframe and token:
            print('  >>> TURNSTILE COMPLETED!')
            break
        if iframe:
            # maybe need to click again inside iframe? just wait
            pass

    print('final token:', ev('window.__ts_token ? window.__ts_token.slice(0,50) : "none"'))
    ws.close()

if __name__ == '__main__':
    main()
