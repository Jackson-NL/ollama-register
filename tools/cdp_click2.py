# -*- coding: utf-8 -*-
"""Click turnstile with realistic mouse gestures, retry until iframe/token appears."""
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

    def quiet(sec):
        end = time.time() + sec
        while time.time() < end:
            try:
                ws.settimeout(0.3)
                ws.recv()
            except Exception:
                continue

    send('Page.enable')
    send('Runtime.enable')
    quiet(1)

    # find all visible elements that could be the turnstile checkbox
    for attempt in range(6):
        print(f'--- attempt {attempt} ---')
        # look at cf-turnstile internals
        inner = ev("""(() => {
            var el = document.getElementById('cf-turnstile');
            if (!el) return 'none';
            return el.innerHTML.slice(0, 800);
        })()""")
        print('cf-turnstile inner:', (inner or '')[:300])

        # find clickable area: get elementFromPoint for various points in widget
        points = ev("""(() => {
            var el = document.getElementById('cf-turnstile');
            if (!el) return '[]';
            var r = el.getBoundingClientRect();
            var pts = [];
            for (var fy = 0.2; fy <= 0.9; fy += 0.35) {
                for (var fx = 0.1; fx <= 0.9; fx += 0.4) {
                    var x = r.x + r.width * fx, y = r.y + r.height * fy;
                    var elAt = document.elementFromPoint(x, y);
                    pts.push({x: Math.round(x), y: Math.round(y), tag: elAt ? elAt.tagName : 'null', cls: elAt && elAt.className ? String(elAt.className).slice(0,40) : ''});
                }
            }
            return JSON.stringify(pts);
        })()""")
        print('points:', points)

        # try clicking center of widget with hover first
        center = ev("""(() => {
            var el = document.getElementById('cf-turnstile');
            var r = el.getBoundingClientRect();
            return JSON.stringify({x: r.x + r.width/2, y: r.y + r.height/2});
        })()""")
        if center:
            c = json.loads(center)
            x, y = c['x'], c['y']
            # hover
            send('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': x - 40, 'y': y - 20})
            quiet(0.2)
            for i in range(6):
                send('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': x - 40 + i * 12, 'y': y - 20 + i * 6})
                quiet(0.05)
            send('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': x, 'y': y})
            quiet(0.3)
            send('Input.dispatchMouseEvent', {'type': 'mousePressed', 'x': x, 'y': y, 'button': 'left', 'clickCount': 1})
            quiet(0.15)
            send('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'x': x, 'y': y, 'button': 'left', 'clickCount': 1})
            print(f'clicked center {x},{y}')

        quiet(3)
        iframe = ev("""(() => { var f = document.querySelector('iframe[src*="challenges.cloudflare.com"]'); return f ? f.src.slice(0,100) : null; })()""")
        token = ev('document.querySelector(\'input[name="bot_detection_token"]\') ? document.querySelector(\'input[name="bot_detection_token"]\').value : ""')
        print(f'iframe={iframe} token={token[:20] if token else ""}')
        if token:
            print('>>> TOKEN OBTAINED!')
            break
        if iframe:
            print('>>> IFRAME PRESENT - clicking inside it')
            rect_s = ev("""(() => {
                var f = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
                var r = f.getBoundingClientRect();
                return JSON.stringify({x: r.x + r.width/2, y: r.y + r.height/2});
            })()""")
            if rect_s:
                rc = json.loads(rect_s)
                send('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': rc['x'], 'y': rc['y']})
                quiet(0.2)
                send('Input.dispatchMouseEvent', {'type': 'mousePressed', 'x': rc['x'], 'y': rc['y'], 'button': 'left', 'clickCount': 1})
                quiet(0.15)
                send('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'x': rc['x'], 'y': rc['y'], 'button': 'left', 'clickCount': 1})
                print('clicked iframe center')
        quiet(2)

    # final check
    print('--- final ---')
    print('token:', ev('document.querySelector(\'input[name="bot_detection_token"]\') ? document.querySelector(\'input[name="bot_detection_token"]\').value.slice(0,30) : "none"'))
    print('url:', ev('location.href'))
    print('submit disabled:', ev('document.querySelector(\'button[type="submit"]\') ? document.querySelector(\'button[type="submit"]\').disabled : "no btn"'))
    ws.close()

if __name__ == '__main__':
    main()
