---
script: wiki-morning
time-limit-minutes: 20
---
# Task: morning message

Queued every day at 06:00 (`examples/cron/wiki-jobs`); wikiglue posts the reply to the announce
room. `wiki-morning` (next to the job runner) does it in steps, so the model judges one thing at
a time:

1. Picks the trips in `wiki/trips/` that are under way or start within 90 days, and lists every
   night of each.
2. Runs `_tasks/trip-check.md` once per trip: every night needs a stay, and every leg (home →
   first place → … → home) a booked flight, train, bus or ferry, or a drive.
3. Runs `_tasks/morning-message.md`: open to-dos (and household service due within 14 days),
   gift cards and credits expiring within 7 days, and needs, with the trip results added.

To change what the message says, edit those two task files.
