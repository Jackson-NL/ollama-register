# -*- coding: utf-8 -*-
"""GET-only capture for Ollama/WorkOS AuthKit pages.

No POST, no form submit, no registration, no email side effects.
"""
from __future__ import annotations

import hashlib
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTDIR = ROOT / "captures" / "live_get"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
BASE = "https://signin.ollama.com"
CLIENT_ID = "client_01JX0QMHD43PFFCCNXH82A6K8B"
REDIRECT_URI = "https://ollama.com/auth/callback"

ctx = ssl.create_default_context()


def fetch(url: str) -> tuple[int, str, dict[str, str], bytes]:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    })
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            return resp.status, resp.geturl(), dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.geturl(), dict(e.headers), e.read()


def save(name: str, status: int, final_url: str, headers: dict[str, str], body: bytes) -> dict:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")
    html_path = OUTDIR / f"{safe}.html"
    meta_path = OUTDIR / f"{safe}.meta.json"
    html_path.write_bytes(body)
    meta = {
        "name": name,
        "status": status,
        "final_url": final_url,
        "headers": headers,
        "size": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "saved": str(html_path.relative_to(ROOT)),
        "captured_at_ms": int(time.time() * 1000),
        "auth_session_input": re.findall(rb'name="authorization_session_id" value="([^"]+)"', body.decode("utf-8", "ignore").encode()),
        "page_kind": (re.search(r'data-hak-page="([^"]+)"', body.decode("utf-8", "ignore")) or [None, None])[1],
        "title": (re.search(r"<title>([^<]+)</title>", body.decode("utf-8", "ignore")) or [None, None])[1],
    }
    # convert bytes regex result if any
    meta["auth_session_input"] = [x.decode("ascii", "ignore") for x in meta["auth_session_input"]]
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def main() -> int:
    qs = urllib.parse.urlencode({"client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI, "screen_hint": "sign-up"})
    urls = {
        "sign-up-screen-hint": f"{BASE}/sign-up?{qs}",
        "sign-in-screen-hint": f"{BASE}/?{qs}",
        "root-with-client": f"{BASE}/?" + urllib.parse.urlencode({"client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI}),
    }
    summary = []
    for name, url in urls.items():
        st, final, headers, body = fetch(url)
        meta = save(name, st, final, headers, body)
        summary.append({k: meta[k] for k in ["name", "status", "final_url", "size", "sha256", "saved", "page_kind", "title", "auth_session_input"]})
        print(json.dumps(summary[-1], ensure_ascii=False))
    out = ROOT / "exports" / "ollama_live_get_summary.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
