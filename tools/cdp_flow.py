# -*- coding: utf-8 -*-
"""Full flow with DOM observation: navigate fresh -> fill -> requestSubmit -> watch bot check appear."""
import json
import time
import urllib.request
import websocket
import uuid

DEBUG_PORT = 9335
SIGNUP_URL = ('https://signin.ollama.com/sign-up?client_id=client_01JX0QMHD43PFFCCNXH82A6K8B'
              '&redirect_uri=https%3A%2F%2Follama.com%2Fauth%2Fcallback&screen_hint=sign-up')

def find_target():
    r = urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json/list', timeout=3)
    targets = json.loads(r.read().decode())
    for t in targets:
        if t.get('type') == 'page':
            return t
    return None

def main():
    tgt = find_target()
    if not tgt:
        print('no target')
        return
    ws = websocket.create_connection(tgt['webSocketDebuggerUrl'], timeout=30)
    print('connected to', tgt['url'][:80])

    mid = 0
    def send(method, params=None):
        nonlocal mid
        mid += 1
        ws.send(json.dumps({'id': mid, 'method': method, 'params': params or {}}))
        return mid

    def ev(expr, timeout=10):
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

    def wait_quiet(seconds):
        end = time.time() + seconds
        while time.time() < end:
            try:
                ws.settimeout(0.5)
                ws.recv()
            except Exception:
                continue

    send('Page.enable')
    send('Runtime.enable')
    wait_quiet(1)

    print('navigating...')
    send('Page.navigate', {'url': SIGNUP_URL})
    wait_quiet(4)

    # wait for page load
    for i in range(20):
        url = ev('location.href') or ''
        if 'signin.ollama.com' in url and 'Just a moment' not in (ev('document.title') or ''):
            break
        wait_quiet(2)
    print('url:', ev('location.href'))
    print('title:', ev('document.title'))

    # wait for email input
    for i in range(10):
        if ev('!!document.querySelector(\'input[name="email"]\')'):
            break
        wait_quiet(2)
    print('email input ready')

    # fill email
    email = 'regtest.' + uuid.uuid4().hex[:8] + '@mailinator.com'
    print('email:', email)
    print('fill:', ev(f"""(() => {{
        var el = document.querySelector('input[name="email"]');
        var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, '{email}');
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
        return 'OK';
    }})()"""))

    print('signals:', ev('document.querySelector(\'input[name="signals"]\') ? "len=" + document.querySelector(\'input[name="signals"]\').value.length : "none"'))

    # requestSubmit
    print('submit:', ev("""(() => {
        var form = document.querySelector('form');
        form.requestSubmit();
        return 'done';
    })()"""))

    # watch for the bot check widget to appear and turnstile iframe
    for i in range(20):
        wait_quiet(1)
        ts = ev("""(() => {
            var el = document.querySelector('.cf-turnstile');
            return el ? el.outerHTML.slice(0, 200) : null;
        })()""")
        iframe = ev("""(() => {
            var f = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
            return f ? f.src.slice(0, 120) : null;
        })()""")
        btns = ev("""(() => {
            var r = [];
            document.querySelectorAll('button').forEach(function(b) {
                if (b.offsetParent !== null) r.push((b.innerText||'').trim().slice(0,30) + '|disabled=' + b.disabled);
            });
            return r.join('\\n');
        })()""")
        print(f'[{i}s] turnstile={ts is not None} iframe={iframe is not None} btns={btns.replace(chr(10), " / ")}')
        if iframe:
            print('  TURNSTILE IFRAME APPEARED!')
            break

    # if turnstile iframe appeared, try clicking the checkbox
    if ev('!!document.querySelector(\'iframe[src*="challenges.cloudflare.com"]\')'):
        print('--- clicking turnstile checkbox ---')
        print(ev("""(() => {
            var f = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
            var r = f.getBoundingClientRect();
            return 'iframe rect: ' + JSON.stringify({x: r.x, y: r.y, w: r.width, h: r.height});
        })()"""))

    # dump page
    html = ev('document.documentElement.outerHTML') or ''
    with open(r'D:\PRO\ollama-register\captures\cdp-botcheck.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print('html saved:', len(html))

    # collect text
    print('text:', (ev('document.body ? document.body.innerText.slice(0,500) : ""') or ''))
    print('=== done ===')

if __name__ == '__main__':
    main()
