# -*- coding: utf-8 -*-
"""List all CDP targets on the debug port."""
import urllib.request
import json

def main():
    r = urllib.request.urlopen('http://127.0.0.1:9335/json/list', timeout=3)
    targets = json.loads(r.read().decode())
    print(f'{len(targets)} targets:')
    for t in targets:
        print(f'  type={t.get("type")} url={t.get("url", "")[:100]} ws={t.get("webSocketDebuggerUrl", "")[:60]}')

if __name__ == '__main__':
    main()
