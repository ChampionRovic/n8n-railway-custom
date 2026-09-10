You are running the weekly SCN chapter link audit for Success Champion Networking. Work autonomously; nobody is watching. Finish every step and end with a short summary suitable for a phone notification.

Repository: ChampionRovic/n8n-railway-custom, branch claude/ghl-connection-test-7ds7k2 (or main once merged). The audit tooling is in audit/ and audit/README.md explains it. GHL_LOCATION_ID comes from .claude/settings.json; the GoHighLevel token is injected by the environment proxy, never print it.

Steps:
1. `git fetch origin && git checkout` the branch above, then `python3 audit/collect.py --days 7`. Set a User-Agent as the scripts do; GoHighLevel's Cloudflare blocks default Python clients.
2. Read audit/out/zoom_ids_to_check.json. For each meeting ID, use the Zoom connector's search tool with datasource zoom_meeting and filter meeting_number eq <id> (page_size 3). Record found, topic, meeting_type, the most recent schedule_start_time, and the date of the most recent occurrence. If nothing is returned, record {"found": false}. Write the result to audit/out/zoom.json in the shape documented in audit/README.md. Never click or fetch any link.successchampionnetworking.com trigger link; decoding them is fine, following them registers a visitor click.
3. `python3 audit/compare.py`, then `python3 audit/fix.py --apply`, then `python3 audit/compare.py` again so the report lists what was written. fix.py only rewrites contact Zoom Link fields to their own chapter's verified link; do not modify custom values or the SCN Chapters object on this run.
4. Publish audit/out/report.html to the existing artifact at https://claude.ai/code/artifact/c8c65852-3dcf-4168-85f1-ba4a0041e84f: first `read` that URL with the Artifact tool, then publish with `url` set to it so the link stays the same. Do not create a new artifact.
5. Commit nothing; audit/out/ is gitignored. If a script fails, say exactly which step and the error, and still publish whatever report exists.

Final message format (this becomes the push notification): one line verdict, then at most five bullets: chapters flagged (name + why), stale or cross-wired contact records fixed, email routing mismatches, anything the token could not read, and the artifact link. If everything is clean, say "All 30 chapters clear" and stop.
