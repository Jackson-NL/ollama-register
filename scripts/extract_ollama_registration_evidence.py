# -*- coding: utf-8 -*-
"""Extract local evidence for the Ollama/WorkOS auth registration reverse report.

This script is intentionally offline-only: it reads captured HTML/JS and existing
probe scripts from this workspace and does not make network requests.
"""
from __future__ import annotations

import hashlib
import json
import re
from html import unescape
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CAPTURES = ROOT / "captures"
TOOLS = ROOT / "tools"
OUT = ROOT / "exports" / "ollama_registration_evidence.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def unique(seq):
    seen = set()
    out = []
    for item in seq:
        key = json.dumps(item, sort_keys=True, ensure_ascii=False) if isinstance(item, (dict, list)) else item
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def extract_html_basics(html: str) -> dict[str, Any]:
    inputs = []
    for tag in re.findall(r"<input\b[^>]*>", html, flags=re.I):
        fixed = {}
        for m in re.finditer(r"([:\w-]+)=(\"([^\"]*)\"|'([^']*)')", tag):
            fixed[m.group(1)] = unescape(m.group(3) or m.group(4) or "")
        inputs.append(fixed)

    links = []
    for tag in re.findall(r"<a\b[^>]*href=(?:\"[^\"]*\"|'[^']*')[^>]*>", html, flags=re.I):
        href_m = re.search(r"href=(?:\"([^\"]*)\"|'([^']*)')", tag, flags=re.I)
        if href_m:
            links.append(unescape(href_m.group(1) or href_m.group(2) or ""))

    auth_input_ids = sorted(set(i.get("value") for i in inputs if i.get("name") == "authorization_session_id" and i.get("value")))
    return {
        "page_kind": re.search(r'data-hak-page="([^"]+)"', html).group(1) if re.search(r'data-hak-page="([^"]+)"', html) else None,
        "title": re.search(r"<title>([^<]+)</title>", html).group(1) if re.search(r"<title>([^<]+)</title>", html) else None,
        "flight_server_action_ids": sorted(set(re.findall(r'"id":"([0-9a-f]{40,64})","bound":null', html))),
        "forms_count": len(re.findall(r"<form\b", html, flags=re.I)),
        "inputs": inputs,
        "oauth_login_links": [x for x in links if "/api/login" in x],
        "signup_links": [x for x in links if "/sign-up" in x],
        "client_ids": sorted(set(re.findall(r"client_[0-9A-Z]+", html))),
        "authorization_session_ids": sorted(set(re.findall(r"01[A-Z0-9]{24}", html))),
        "authorization_session_input_ids": auth_input_ids,
        "redirect_uris": sorted(set(unescape(x) for x in re.findall(r"redirect_uri=([^&\"']+)", html))),
        "script_count": len(re.findall(r"<script\b", html, flags=re.I)),
    }


def extract_js_evidence() -> dict[str, Any]:
    js_files = sorted(CAPTURES.glob("chunk-*.js"))
    combined = "\n".join(read(p) for p in js_files)
    refs = []
    for m in re.finditer(r'createServerReference\("([0-9a-f]{40,64})"[^)]*?,"([A-Za-z0-9_$-]+)"\)', combined):
        refs.append({"id": m.group(1), "name": m.group(2)})

    # Minified chunks sometimes truncate in grep output; collect raw 40-hex IDs and map by nearby names.
    mapped = []
    for name in ["signIn", "joinWaitlist", "signFingerprint"]:
        for m in re.finditer(name, combined):
            window = combined[max(0, m.start() - 180): m.end() + 180]
            for h in re.findall(r"[0-9a-f]{40,64}", window):
                mapped.append({"id": h, "near": name})

    endpoints = sorted(set(re.findall(r'(?:(?:https?://[^"\'`\\]+)|(?:/[A-Za-z0-9_./?=&%-]+))', combined)))
    endpoints = [e for e in endpoints if any(k in e for k in ["/api/", "/workers/", "signin.ollama.com", "ollama.com/auth/callback"])]

    signals_fields = []
    for key in [
        "createdAtMs", "timezone", "language", "hardwareConcurrency", "webdriver", "userAgent",
        "appVersion", "platform", "screen", "rangeErrorLength", "evalStringLength",
        "playwrightDetected", "phantomDetected", "nightmareDetected", "seleniumDetected",
        "puppeteerDetected", "maxTouchPoints", "deviceMemory", "permissionsState",
        "notificationPermission", "devicePixelRatio", "pluginsLength", "mimeTypesCount",
        "documentHidden", "documentVisibilityState", "mediaPreferences", "minimalSurface",
        "worker", "canvasHash", "audioHash", "mathHash", "intlHash", "webGLParamsHash",
        "windowFeaturesHash", "windowFeaturesCount", "cssKeysHash", "cssKeysCount",
        "voicesHash", "voicesLocalCount", "voicesRemoteCount", "voicesLanguagesCount",
        "mediaMimeHash", "mediaMimeCount", "submittedAtMs",
    ]:
        if key in combined:
            signals_fields.append(key)

    return {
        "server_action_refs": unique(refs + mapped),
        "endpoints": endpoints,
        "radar_signal_fields_seen": signals_fields,
        "strings": {
            "uses_next_action_header": "Next-Action" in combined,
            "uses_radar_signals": "radar-signals" in combined,
            "uses_wuid_cookie": "__wuid" in combined,
            "uses_fingerprint_hash": "fingerprintHash" in combined,
            "uses_bot_detection_token": "bot_detection_token" in combined,
            "uses_signals_worker": "/workers/signals-worker.js" in combined,
        },
    }


def extract_tool_evidence() -> dict[str, Any]:
    scripts = sorted(TOOLS.glob("probe_signup*.py"))
    text_by_file = {str(p.relative_to(ROOT)): read(p) for p in scripts}
    ids = sorted(set(re.findall(r"[0-9a-f]{40,64}", "\n".join(text_by_file.values()))))
    urls = sorted(set(re.findall(r"https://[^'\"\s)]+", "\n".join(text_by_file.values()))))
    return {
        "probe_scripts": [{"path": str(p.relative_to(ROOT)), "size": p.stat().st_size, "sha256": sha256(p)} for p in scripts],
        "hardcoded_action_ids": ids,
        "urls": urls,
        "notes": "Probe scripts are historical live-test attempts; this evidence extractor does not execute them.",
    }


def main() -> None:
    html_path = CAPTURES / "signup-page.html"
    html = read(html_path)
    files = []
    for p in sorted(CAPTURES.glob("*")):
        if p.is_file():
            files.append({"path": str(p.relative_to(ROOT)), "size": p.stat().st_size, "sha256": sha256(p)})

    evidence = {
        "workspace": str(ROOT),
        "offline_only": True,
        "captures": files,
        "html": extract_html_basics(html),
        "javascript": extract_js_evidence(),
        "tools": extract_tool_evidence(),
        "key_module_exports": [
            "exports/modules/57560_chunk-3.js  # SignInForm",
            "exports/modules/49649_chunk-1.js  # WaitlistForm",
            "exports/modules/12696_chunk-5.js  # Radar signals collector",
            "exports/modules/76482_chunk-11.js # Fingerprint -> __wuid",
            "exports/modules/66989_chunk-3.js  # AuthenticationForm hidden fields",
            "exports/modules/66273_chunk-3.js  # /api/login OAuth URL builder",
            "exports/modules/72296_chunk-3.js  # bot_detection_token input",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(json.dumps({
        "page_kind": evidence["html"]["page_kind"],
        "client_ids": evidence["html"]["client_ids"],
        "auth_session_ids": evidence["html"]["authorization_session_ids"][:3],
        "server_actions": evidence["javascript"]["server_action_refs"],
        "radar_fields": len(evidence["javascript"]["radar_signal_fields_seen"]),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
