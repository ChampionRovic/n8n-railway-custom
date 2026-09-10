# Routine: SCN chapter link audit (Mondays 8:00 AM Central)

Schedule (cron, UTC): `0 13 * * 1` during Central Daylight Time. Change to `0 14 * * 1` after the November clock change if 8:00 AM sharp matters.
Fresh session per run, connector "Zoom for Claude", notifications push + email.

## Prompt

You are running the weekly SCN chapter link audit for Success Champion Networking. Work autonomously; nobody is watching. Finish every step and end with a short summary suitable for a phone notification.

Repository: ChampionRovic/n8n-railway-custom, branch claude/ghl-connection-test-7ds7k2 (fall back to main if that branch no longer exists). The audit tooling is in audit/ and audit/README.md explains it. GHL_LOCATION_ID comes from .claude/settings.json (value akX9j7JqdOpjcs3tS4WI if the file is missing); the GoHighLevel token is injected by the environment proxy. Never print any token.

Steps:
1. `git fetch origin` and check out the branch above, then run `GHL_LOCATION_ID=akX9j7JqdOpjcs3tS4WI python3 audit/collect.py --days 7`. The scripts set their own User-Agent because GoHighLevel's Cloudflare blocks default Python clients; do not remove it.
2. Read audit/out/zoom_ids_to_check.json. For each meeting ID, call the Zoom for Claude connector's `search` tool with datasource_filters [{"datasource":"zoom_meeting","filters":{"eq":{"key":"meeting_number","value":<id as integer>}}}] and page_size 3. Record found (true if any record came back), topic, meeting_type, the most recent schedule_start_time, and last_occurrence as the date (YYYY-MM-DD) of the most recent record. If nothing is returned, record {"found": false}. Write audit/out/zoom.json as {"<id>": {...}, ...}. Never click or fetch any link.successchampionnetworking.com trigger link; decoding them is fine, following them registers a visitor click.
3. Run `python3 audit/compare.py`, then `python3 audit/fix.py --apply`, then `python3 audit/compare.py` again so the report lists what was written (all with GHL_LOCATION_ID set). fix.py only rewrites contact Zoom Link fields to their own chapter's verified link. Do not modify custom values or the SCN Chapters object on this run.
4. Publish audit/out/report.html to the existing artifact https://claude.ai/code/artifact/c8c65852-3dcf-4168-85f1-ba4a0041e84f: first call the Artifact tool with action "read" and that url, then publish the file with `url` set to the same address so the link stays the same. Do not create a new artifact and do not pass a favicon.
5. Commit nothing; audit/out/ is gitignored. If a script fails, say which step and quote the error, and still publish whatever report exists.

Final message format (this becomes the push notification): one line verdict, then at most five bullets: chapters flagged (name and why), contact records corrected, email routing mismatches, anything the token could not read, and the artifact link. If nothing needs attention, the first line is "All chapters clear" followed only by the artifact link.
