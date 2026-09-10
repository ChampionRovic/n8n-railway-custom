"""Minimal GoHighLevel API helper for the chapter link audit.

Auth is injected by the Claude Code environment proxy; no token is handled here.
Set GHL_LOCATION_ID in the environment (the repo's .claude/settings.json does this).
"""
import json, os, sys, time, urllib.request, urllib.error

BASE = "https://services.leadconnectorhq.com"
HEADERS = {"Version": "2021-07-28", "Accept": "application/json",
           "Content-Type": "application/json", "User-Agent": "scn-link-audit/1.0"}
LOCATION = os.environ.get("GHL_LOCATION_ID", "")


def call(method, path, body=None, retries=4):
    """Return (status, json_or_None). Retries on 429; never raises on HTTP errors."""
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(retries):
        req = urllib.request.Request(BASE + path, data=data, headers=HEADERS, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 * (attempt + 1)); continue
            try: return e.code, json.load(e)
            except Exception: return e.code, None
        except Exception:
            time.sleep(1)
    return 0, None


def get(path):
    return call("GET", path)


def require_location():
    if not LOCATION:
        sys.exit("GHL_LOCATION_ID is not set")
    return LOCATION
