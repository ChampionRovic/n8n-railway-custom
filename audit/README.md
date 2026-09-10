# SCN chapter link audit

Weekly check that every Success Champion Networking chapter sends visitors to the right Zoom meeting.
It runs as a Claude Code Routine every Monday at 8:00 AM Central and republishes the
"SCN Chapter Link Audit" page, then sends a push and email summary.

## What it checks

1. **Custom values vs Zoom.** Each `{{ custom_values.<chapter> }}` bridge-page URL carries a Zoom meeting ID,
   a day and a time. The meeting ID is looked up in Zoom and the schedule compared in the chapter's own zone.
2. **Email routing.** Every outbound email from the last 7 days is scanned. Visitor emails carry a per-chapter
   trigger link; the audit confirms each link maps to one chapter and matches the visitor's booked appointment.
3. **Contact Zoom Link field.** The approval welcome email sends the raw link stored on the contact
   (`contact.zoom_link`). Contacts whose stored link belongs to another chapter, or to a retired meeting, are listed.
4. **SCN Chapters object.** Read when the token has `objects/record.readonly`; otherwise reported as unreadable.

## How a run works

```
export GHL_LOCATION_ID=...          # set by .claude/settings.json in this repo
python3 audit/collect.py --days 7   # pulls GHL data into audit/out/ (no names or emails stored)
# Claude looks up every ID in audit/out/zoom_ids_to_check.json with the Zoom connector
# and writes audit/out/zoom.json  {"<id>": {"found": true, "topic": ..., "meeting_type": ...,
#                                            "schedule_start_time": ..., "last_occurrence": ...}}
python3 audit/compare.py            # writes audit/out/findings.json and audit/out/report.html
python3 audit/fix.py --apply        # corrects contact Zoom Link fields that disagree with a verified chapter link
python3 audit/compare.py            # re-render with the fixes listed
# Claude publishes audit/out/report.html to the existing artifact URL
```

`fix.py` only ever rewrites a contact's Zoom Link field, and only to the link of the chapter named on that
contact, and only when that chapter's link was verified against Zoom in the same run. Custom values and the
SCN Chapters object are never changed on a schedule.

## Scopes the private integration needs

Read: `locations/customValues.readonly`, `contacts.readonly`, `conversations.readonly`,
`conversations/message.readonly`, `locations/customFields.readonly`, `calendars/events.readonly`.
Write: `contacts.write`. Optional: `objects/schema.readonly`, `objects/record.readonly`, `links.readonly`.
