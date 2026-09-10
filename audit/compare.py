"""Compare collected GoHighLevel data against Zoom and produce findings.json + report.html.

Expects audit/out/zoom.json, written by the Claude session from the Zoom connector:
  {"<meeting_id>": {"found": true, "topic": "...", "meeting_type": "RECURRING_MEETING",
                    "schedule_start_time": "2026-09-09T14:00:00Z", "last_occurrence": "2026-09-09"}, ...}
A meeting id that Zoom cannot see is {"found": false}.
"""
import json, os, re, html, collections
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

OUT = os.path.join(os.path.dirname(__file__), "out")
ZONES = {"CT": "America/Chicago", "ET": "America/New_York", "MT": "America/Denver", "PT": "America/Los_Angeles", "Arizona": "America/Phoenix"}
ALIASES = {"crushingcarolinas": "Crushing Carolina", "dragonrising": "Dragons Rising",
           "metroplexbusinessinfluencerse": "Metroplex Business Influencers", "businessboostersalliance": "Business Booster Alliance"}
# Meetings hosted on other people's Zoom accounts; Zoom search cannot see them, and that is expected.
EXTERNAL_HOSTED = {"81315202074": "Pacific Pipeline (Chris Wessling's account)"}


def load(n):
    with open(os.path.join(OUT, n)) as f: return json.load(f)


def norm(s): return re.sub(r"[^a-z]", "", (s or "").lower())


def make_chap(chapters):
    keys = {norm(c["chapter"]): c["chapter"] for c in chapters}; keys.update(ALIASES)
    def chap(text):
        n = norm(text); best = None
        for k, v in keys.items():
            if k and k in n and (best is None or len(k) > len(best[0])): best = (k, v)
        return best[1] if best else None
    return chap


def parse_time(t):
    m = re.match(r"\s*(\d{1,2}):(\d{2})\s*(am|pm)?\s*([A-Za-z]+)", t or "", re.I)
    if not m: return None
    h, mi, ap, zn = int(m[1]), int(m[2]), (m[3] or "").lower(), m[4]
    if ap == "pm" and h != 12: h += 12
    if ap == "am" and h == 12: h = 0
    return h, mi, zn


def check_chapters(chapters, zoom, today):
    rows = []
    for c in chapters:
        z = zoom.get(c["zoom_id"]) or {}
        row = {"chapter": c["chapter"], "ghl": f"{c['day']} {c['time']}", "zoom_id": c["zoom_id"], "zoom": "—", "status": "ok", "note": "Matches Zoom."}
        if c["chapter"].startswith("Test Chapter"):
            row.update(status="test", note="Test entry; safe to ignore.")
        elif z.get("error"):
            row.update(status="check", zoom="not checked", note=f"Zoom lookup unavailable this run ({z['error']}). GoHighLevel-side checks still ran.")
        elif not z.get("found"):
            if c["zoom_id"] in EXTERNAL_HOSTED:
                row.update(status="ok", zoom="not visible", note=f"Hosted on another Zoom account: {EXTERNAL_HOSTED[c['zoom_id']]}. Confirmed manually.")
            else:
                row.update(status="flag", note="Meeting ID not found in Zoom. Link may be dead.")
        elif z.get("meeting_type") != "RECURRING_MEETING" or not z.get("schedule_start_time"):
            row.update(status="check", zoom="no fixed time", note="Zoom meeting has no fixed schedule; day and time cannot be verified. ID matches.")
        else:
            p = parse_time(c["time"])
            if not p:
                row.update(status="check", note=f"Could not parse GHL time '{c['time']}'.")
            else:
                h, mi, zn = p
                local = datetime.fromisoformat(z["schedule_start_time"].replace("Z", "+00:00")).astimezone(ZoneInfo(ZONES.get(zn, "America/Chicago")))
                row["zoom"] = local.strftime("%A %-I:%M %p ") + zn
                if local.strftime("%A") != c["day"] or (local.hour, local.minute) != (h, mi):
                    row.update(status="flag", note="Day or time in GHL differs from Zoom's schedule.")
                last = z.get("last_occurrence")
                if last and (today - datetime.fromisoformat(last).date()).days > 21:
                    row.update(status="check", note=f"Schedule matches, but last Zoom occurrence was {last}. Meeting may have moved or paused.")
        rows.append(row)
    return rows


def check_contacts(contact_rows, chapters, zoom):
    by_zoom = {c["zoom_id"]: c["chapter"] for c in chapters}
    good = {c["chapter"]: c for c in chapters}
    out = []
    for r in contact_rows["rows"]:
        owner = by_zoom.get(r["zoom_id"])
        if owner == r["chapter"]: continue
        if r["zoom_id"] and not (zoom.get(r["zoom_id"]) or {}).get("found") and owner is None:
            problem = "Stored link is not a current chapter meeting"
        elif owner is None:
            problem = "Stored link belongs to no chapter"
        else:
            problem = f"Stored link belongs to {owner}"
        fix = good.get(r["chapter"])
        out.append({"contact": r["id"], "chapter": r["chapter"], "stored_zoom_id": r["zoom_id"], "problem": problem,
                    "updated": r["updated"], "fix_link": fix["zoom_link"] if fix else None})
    return out


def check_emails(em, appts, chapters):
    chap = make_chap(chapters)
    rows = em["rows"]
    mat = collections.defaultdict(collections.Counter)
    for r in rows:
        c = chap(r["subject"])
        if c:
            for t in r["trigger_links"]: mat[t][c] += 1
    link2chap = {k: v.most_common(1)[0][0] for k, v in mat.items()}
    shared = {k: dict(v) for k, v in mat.items() if len(v) > 1}
    cal = collections.defaultdict(collections.Counter)
    for a in appts.values():
        for e in a:
            c = chap(e["title"])
            if c: cal[e["calendar_id"]][c] += 1
    cal2chap = {k: v.most_common(1)[0][0] for k, v in cal.items()}
    checked = ok = 0; bad = []
    for r in rows:
        if not r["trigger_links"] or not chap(r["subject"]): continue  # re-invites have no chapter in subject; skip
        d = datetime.fromisoformat(r["date"])
        cand = {cal2chap.get(e["calendar_id"]) for e in appts.get(r["contact"], [])
                if e["start"] and timedelta(days=-1) <= datetime.fromisoformat(e["start"][:10]) - d <= timedelta(days=90)} - {None}
        if not cand: continue
        for t in r["trigger_links"]:
            checked += 1
            if link2chap.get(t) in cand: ok += 1
            else: bad.append({"date": r["date"], "contact": r["contact"], "subject": r["subject"], "link_chapter": link2chap.get(t), "booked": sorted(cand)})
    by_zoom = {c["zoom_id"]: c["chapter"] for c in chapters}
    raw = []
    for r in rows:
        for z in r["zoom_ids"]:
            raw.append({"date": r["date"], "contact": r["contact"], "subject": r["subject"], "zoom_id": z, "chapter": by_zoom.get(z), "current": z in by_zoom})
    return {"emails_scanned": len(rows), "trigger_link_emails": sum(1 for r in rows if r["trigger_links"]),
            "links_seen": len(mat), "links_shared_between_chapters": shared, "checked": checked, "matched": ok, "mismatches": bad,
            "raw_zoom_emails": raw, "stale_zoom_emails": [x for x in raw if not x["current"]]}


PILL = {"ok": "OK", "fixed": "Fixed", "check": "Check", "test": "Test", "flag": "Flag"}


def render(f, run_date):
    e = html.escape
    ch = f["chapters"]; em = f["emails"]; ct = f["contacts"]
    counts = collections.Counter(r["status"] for r in ch)
    crow = "\n".join(f'<tr><td>{e(r["chapter"])}</td><td>{e(r["ghl"])}</td><td>{e(r["zoom"])}</td><td><span class="pill {r["status"]}">{PILL[r["status"]]}</span></td><td class="note">{e(r["note"])}</td></tr>' for r in ch)
    trow = "\n".join(f'<tr><td class="mono">{e(r["contact"])}</td><td>{e(str(r["chapter"]))}</td><td class="mono">{e(str(r["stored_zoom_id"]))}</td><td>{e(r["problem"])}</td><td>{e(r["updated"])}</td></tr>' for r in ct) or '<tr><td colspan="5">None. Every stored Zoom Link matches its chapter.</td></tr>'
    mrow = "\n".join(f'<tr><td>{e(r["date"])}</td><td class="mono">{e(r["contact"])}</td><td>{e(str(r["subject"]))}</td><td>{e(str(r["link_chapter"]))}</td><td>{e(", ".join(r["booked"]))}</td></tr>' for r in em["mismatches"]) or '<tr><td colspan="5">None.</td></tr>'
    srow = "\n".join(f'<tr><td>{e(r["date"])}</td><td class="mono">{e(r["contact"])}</td><td>{e(str(r["subject"]))}</td><td class="mono">{e(r["zoom_id"])}</td></tr>' for r in em["stale_zoom_emails"]) or '<tr><td colspan="4">None.</td></tr>'
    obj = f["objects"]
    obj_html = (f'<p>Read {len(obj["records"])} chapter records.</p>' if obj.get("records") else
                '<p>The object is readable but holds no records. The per-contact Zoom Link values are therefore set somewhere else, most likely inside the Update Chapter Info workflow, which the API cannot read.</p>') if "records" in obj else f'<p>Not readable (HTTP {obj.get("error")}). Add <code>objects/schema.readonly</code> and <code>objects/record.readonly</code> to include it.</p>'
    fixes = f.get("fixes_applied", [])
    fix_html = ("<ul>" + "".join(f'<li class="mono">{e(x)}</li>' for x in fixes) + "</ul>") if fixes else "<p>No changes were written this run.</p>"
    with open(os.path.join(os.path.dirname(__file__), "report_style.css")) as s: css = s.read()
    return f'''<title>SCN Chapter Link Audit</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>{css}</style>
<main>
<div class="eyebrow">Success Champion Networking · GoHighLevel × Zoom · weekly</div>
<h1>SCN Chapter Link Audit</h1>
<p class="lede">Every chapter’s meeting link, checked three ways: the custom value visitors are sent to, the Zoom meeting it points at, and the emails that went out this week.</p>
<div class="meta"><span>Run <b>{e(run_date)}</b></span><span>Emails scanned <b>{em["emails_scanned"]}</b> since {e(f["emails_since"])}</span><span>Contacts scanned <b>{f["contacts_scanned"]}</b></span></div>
<div class="verdict">
<div><div class="k">Chapters</div><div class="v">{len([r for r in ch if r["status"] != "test"])}</div><div class="s">{counts["ok"]} match Zoom</div></div>
<div><div class="k">Flags</div><div class="v">{counts["flag"]}</div><div class="s">{counts["check"]} to double-check</div></div>
<div><div class="k">Email routing</div><div class="v">{em["matched"]}/{em["checked"]}</div><div class="s">reminders matched the booked chapter</div></div>
<div><div class="k">Contact records wrong</div><div class="v">{len(ct)}</div><div class="s">stale or cross-wired Zoom Link field</div></div>
</div>
<h2>Chapter by chapter</h2>
<p>“GHL” is the day and time in the chapter’s custom value. “Zoom” is the scheduled start of the meeting that ID resolves to, in the chapter’s own time zone.</p>
<div class="tablewrap"><table><thead><tr><th>Chapter</th><th>GHL</th><th>Zoom</th><th>Result</th><th>Note</th></tr></thead><tbody>{crow}</tbody></table></div>
<h2>Email routing this week</h2>
<p>{em["trigger_link_emails"]} emails carried a chapter trigger link; {em["links_seen"]} distinct links were seen{", and none was shared between chapters" if not em["links_shared_between_chapters"] else ", <b>and some were shared between chapters</b>"}.</p>
<h3>Reminders whose link did not match the booked chapter</h3>
<div class="tablewrap"><table><thead><tr><th>Sent</th><th>Contact</th><th>Subject</th><th>Link chapter</th><th>Booked</th></tr></thead><tbody>{mrow}</tbody></table></div>
<h3>Emails carrying a retired Zoom link</h3>
<div class="tablewrap"><table><thead><tr><th>Sent</th><th>Contact</th><th>Subject</th><th>Zoom ID</th></tr></thead><tbody>{srow}</tbody></table></div>
<h2>Contact Zoom Link field</h2>
<p>The approval welcome email sends the raw link stored on each contact. These contacts hold a link that does not belong to their chapter.</p>
<div class="tablewrap"><table><thead><tr><th>Contact</th><th>Chapter field</th><th>Stored Zoom ID</th><th>Problem</th><th>Updated</th></tr></thead><tbody>{trow}</tbody></table></div>
<h2>SCN Chapters object</h2>{obj_html}
<h2>Changes written this run</h2>{fix_html}
<footer>Sources: GoHighLevel custom values, conversations, contacts and appointments via the API; Zoom meeting records via the Zoom connector. Trigger links are decoded, never clicked. No names or email addresses are stored.</footer>
</main>'''


if __name__ == "__main__":
    from datetime import date
    chapters = load("chapters.json"); zoom = load("zoom.json"); cz = load("contact_zoom.json")
    em = load("emails.json"); appts = load("appointments.json"); obj = load("objects.json")
    today = date.today()
    findings = {"run_date": today.isoformat(), "emails_since": em["since"], "contacts_scanned": cz["contacts_scanned"],
                "chapters": check_chapters(chapters, zoom, today), "contacts": check_contacts(cz, chapters, zoom),
                "emails": check_emails(em, appts, chapters), "objects": obj}
    fx = os.path.join(OUT, "fixes_applied.json")
    if os.path.exists(fx): findings["fixes_applied"] = json.load(open(fx))
    with open(os.path.join(OUT, "findings.json"), "w") as f: json.dump(findings, f, indent=1)
    with open(os.path.join(OUT, "report.html"), "w") as f: f.write(render(findings, today.strftime("%-d %B %Y")))
    c = collections.Counter(r["status"] for r in findings["chapters"])
    print(f"chapters: {dict(c)} | contact records wrong: {len(findings['contacts'])} | email mismatches: {len(findings['emails']['mismatches'])} | stale zoom emails: {len(findings['emails']['stale_zoom_emails'])}")
