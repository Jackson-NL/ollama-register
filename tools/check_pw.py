# -*- coding: utf-8 -*-
"""Check playwright-driven page state via CDP if available, else via UI screenshot."""
import json
import time
import urllib.request
import websocket
import base64
import os
import glob

DEBUG_PORT = 9335

def main():
    # Try to find any page on 9335 that is sign-in (old one)
    r = urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json/list', timeout=3)
    targets = json.loads(r.read().decode())
    for t in targets:
        if t.get('type') == 'page' and 'signin.ollama.com' in t.get('url', ''):
            print('old target still:', t.get('url', '')[:110])
            break

    # The playwright browser has no debug port. Use UI automation instead:
    # use pywinauto-like approach via powershell screenshot of the window
    print('--- playwright browser window check ---')
    os.system('powershell -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Screen]::PrimaryScreen.Bounds"')

if __name__ == '__main__':
    main()
