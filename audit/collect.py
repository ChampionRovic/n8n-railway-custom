"""Collect everything the audit needs from GoHighLevel into audit/out/.

Outputs (IDs only, no names or email addresses):
  chapters.json      one row per bridge-page custom value: chapter, day, time, zoom_id, link
  contact_zoom.json  contacts whose "Zoom Link" field is set: id, chapter field, stored zoom id
  emails.json        outbound emails in the last N days: trigger link ids, raw zoom ids, subject, template
  appointments.json  appointments for contacts that received trigger-link emails
  objects.json       SCN Chapters custom object records, or {"error": status} if not readable
"""
import argparse, base64, json, os, re, sys, time, collections
import concurrent.futures as cf
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, parse_qs
import ghl

OUT = os.path.join(os.path.dirname(__file__), "out")
ZOOM_LINK_FIELD = "E73qJCYOBKzffEn8KD4n"      # contact.zoom_link
CHAPTER_FIELD = "du876na6qgnkdIuhAfvj"        # contact.chapter
ATTENDEE_CHAPTER_FIELD = "SpJNOMfVqNC1NisJZ4zw"  # contact.chapter_name (attendee form)
ZOOM_RE = re.compile(r"zoom\.us/j/(\d+)")
HREF_RE = re.compile(r'href="([^"]+)"')
TEMPLATE_RE = re.compile(r"template_id=([A-Za-z0-9]+)")


def save(name, obj):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w") as f:
        json.dump(obj, f, indent=1)


def chapters(L):
    st, d = ghl.get(f"/locations/{L}/customValues")
    if st != 200: sys.exit(f"custom values: HTTP {st}")
    rows = []
    for cv in d["customValues"]:
        v = cv.get("value", "")
        if "bridge-page" not in v: continue
        q = parse_qs(urlparse(v).query)
        link = q.get("link", [""])[0]
        m = ZOOM_RE.search(link)
        rows.append({"custom_value_id": cv["id"], "custom_value_name": cv["name"], "field_key": cv["fieldKey"],
                     "chapter": q.get("scn_chapter_-_long_name", [""])[0], "day": q.get("chdate", [""])[0],
                     "time": q.get("chtime", [""])[0], "chair": q.get("chname", [""])[0],
                     "zoom_id": m.group(1) if m else None, "zoom_link": link, "value": v})
    save("chapters.json", rows)
    return rows


def contacts_zoom(L):
    after = ""; rows = []; n = 0
    while True:
        st, d = ghl.get(f"/contacts/?locationId={L}&limit=100{after}")
        cs = (d or {}).get("contacts") or []
        if not cs: break
        for c in cs:
            f = {x["id"]: x.get("value") for x in c.get("customFields", [])}
            z = f.get(ZOOM_LINK_FIELD)
            if z:
                m = ZOOM_RE.search(str(z))
                rows.append({"id": c["id"], "chapter": f.get(CHAPTER_FIELD), "attendee_chapter": f.get(ATTENDEE_CHAPTER_FIELD),
                             "zoom_id": m.group(1) if m else None, "zoom_link": str(z), "updated": (c.get("dateUpdated") or "")[:10]})
        n += len(cs)
        meta = (d or {}).get("meta") or {}
        if not meta.get("startAfterId") or len(cs) < 100: break
        after = f"&startAfterId={meta['startAfterId']}&startAfter={meta.get('startAfter', '')}"
    save("contact_zoom.json", {"contacts_scanned": n, "rows": rows})
    return rows


def decode_jwt(tok):
    try:
        p = tok.split(".")[1]; p += "=" * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p))
    except Exception:
        return {}


def emails(L, days):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    convs = []; after = ""
    while True:
        st, d = ghl.get(f"/conversations/search?locationId={L}&limit=100&sort=desc&sortBy=last_message_date{after}")
        cs = (d or {}).get("conversations") or []
        if not cs: break
        convs += cs
        last = cs[-1].get("lastMessageDate") or 0
        if datetime.fromtimestamp(last / 1000, timezone.utc) < since or len(cs) < 100: break
        after = f"&startAfterDate={last}"

    def work(c):
        out = []
        st, m = ghl.get(f"/conversations/{c['id']}/messages?limit=100")
        msgs = ((m or {}).get("messages") or {}).get("messages") or []
        appts = [((x.get("dateAdded") or "")[:10], (x.get("body") or "").split(",")[0][:60])
                 for x in msgs if x.get("messageType") == "TYPE_ACTIVITY_APPOINTMENT"]
        for x in msgs:
            if x.get("messageType") != "TYPE_EMAIL" or x.get("direction") != "outbound": continue
            sent = x.get("dateAdded") or ""
            if sent and datetime.fromisoformat(sent.replace("Z", "+00:00")) < since: continue
            eid = ((x.get("meta") or {}).get("email") or {}).get("messageIds", [None])[0] or x.get("id")
            st2, e = ghl.get(f"/conversations/messages/email/{eid}")
            e = (e or {}).get("emailMessage") or {}
            body = e.get("body") or ""
            trig = []; zoom = set(); bridge = []
            for h in HREF_RE.findall(body):
                if "link.successchampionnetworking.com" in h and "/r/" in h:
                    j = decode_jwt(h.rsplit("/", 1)[-1]); trig.append(j.get("link_id"))
                elif "bridge-page" in h:
                    bridge.append(parse_qs(urlparse(h).query).get("scn_chapter_-_long_name", [""])[0])
                mm = ZOOM_RE.search(h)
                if mm: zoom.add(mm.group(1))
            t = TEMPLATE_RE.search(body)
            out.append({"conversation": c["id"], "contact": c.get("contactId"), "date": sent[:10], "subject": e.get("subject"),
                        "template": t.group(1) if t else None, "trigger_links": trig, "zoom_ids": sorted(zoom),
                        "bridge_chapters": bridge, "appointment_activity": appts})
            time.sleep(0.05)
        return out

    rows = []
    with cf.ThreadPoolExecutor(4) as ex:
        for r in ex.map(work, convs): rows += r
    save("emails.json", {"conversations": len(convs), "since": since.date().isoformat(), "rows": rows})
    return rows


def appointments(email_rows):
    ids = sorted({r["contact"] for r in email_rows if r["trigger_links"] and r["contact"]})

    def work(c):
        st, d = ghl.get(f"/contacts/{c}/appointments")
        return c, [{"start": e.get("startTime"), "calendar_id": e.get("calendarId"),
                    "status": e.get("appointmentStatus") or e.get("status"), "title": (e.get("title") or "")[:80]}
                   for e in ((d or {}).get("events") or [])]
    out = {}
    with cf.ThreadPoolExecutor(4) as ex:
        for c, a in ex.map(work, ids): out[c] = a
    save("appointments.json", out)
    return out


def objects(L):
    st, d = ghl.call("POST", "/objects/custom_objects.scn_chapters/records/search",
                     {"locationId": L, "page": 1, "pageLimit": 100, "searchAfter": []})
    if st != 200:
        save("objects.json", {"error": st, "note": "needs objects/schema.readonly and objects/record.readonly"}); return None
    recs = [{"id": r.get("id"), "properties": r.get("properties")} for r in d.get("records", [])]
    save("objects.json", {"records": recs}); return recs


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--days", type=int, default=7); a = ap.parse_args()
    L = ghl.require_location()
    ch = chapters(L); print("chapters:", len(ch))
    cz = contacts_zoom(L); print("contacts with Zoom Link field:", len(cz))
    em = emails(L, a.days); print("outbound emails in window:", len(em))
    ap_ = appointments(em); print("contacts with appointments pulled:", len(ap_))
    ob = objects(L); print("SCN Chapters object:", "readable" if ob is not None else "not readable (scope)")
    zoom_ids = sorted({r["zoom_id"] for r in ch if r["zoom_id"]} | {z for r in em for z in r["zoom_ids"]} | {r["zoom_id"] for r in cz if r["zoom_id"]})
    save("zoom_ids_to_check.json", zoom_ids); print("Zoom meeting IDs to look up:", len(zoom_ids))
