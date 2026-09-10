"""Apply safe corrections from findings.json. Dry run by default; pass --apply to write.

Only one kind of change is made automatically:
  contact Zoom Link field -> the verified link of the chapter named in that contact's Chapter field.
A contact is only touched when its Chapter field maps to a chapter whose custom value link was
verified against Zoom in this run (status ok or check, not flag). Custom values and the SCN
Chapters object are never modified here; those are edited deliberately, not on a schedule.
"""
import argparse, json, os, sys
import ghl

OUT = os.path.join(os.path.dirname(__file__), "out")
ZOOM_LINK_FIELD = "E73qJCYOBKzffEn8KD4n"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); a = ap.parse_args()
    f = json.load(open(os.path.join(OUT, "findings.json")))
    verified = {r["chapter"] for r in f["chapters"] if r["status"] in ("ok", "check")}
    applied = []; skipped = []
    for c in f["contacts"]:
        if not c["fix_link"] or c["chapter"] not in verified:
            skipped.append(f"{c['contact']}: chapter '{c['chapter']}' has no verified link"); continue
        desc = f"contact {c['contact']} Zoom Link -> {c['chapter']} link"
        if not a.apply:
            applied.append("DRY RUN " + desc); continue
        st, d = ghl.call("PUT", f"/contacts/{c['contact']}", {"customFields": [{"id": ZOOM_LINK_FIELD, "field_value": c["fix_link"]}]})
        applied.append(f"{desc} (HTTP {st})" if st == 200 else f"FAILED {desc} (HTTP {st})")
    if a.apply:
        json.dump(applied, open(os.path.join(OUT, "fixes_applied.json"), "w"), indent=1)
    for x in applied + skipped: print(x)
    print(f"{'applied' if a.apply else 'would apply'}: {len([x for x in applied if not x.startswith('FAILED')])}, skipped: {len(skipped)}")


if __name__ == "__main__":
    ghl.require_location(); main()
