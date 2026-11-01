---
tools: read,grep,find,ls
time-limit-minutes: 10
---
# Task: write the morning message

Part of the morning job (`_tasks/morning.md`): the trips have been checked already. Don't change
any file: only read, then reply. Compare dates as YYYY-MM-DD against today (given above).

1. **To do.** Every unchecked `- [ ]` line in pages under `wiki/` (trips, household items and any
   other page with a "To do" section): `grep` for `- [ ]` in `wiki/`, leaving out
   `wiki/digests/` and `wiki/log.md`. Skip trips that have ended (front matter `end:` before
   today). Also household items (`wiki/household/`) whose `next_service:` is within the next 14
   days or already past: "service due <date>".
2. **Expiring soon.** Rows in `wiki/credits.md` (gift cards, travel credits, vouchers and card
   offers) whose Expires date is between today and today + 7 days: retailer, kind, value, expiry
   date, holder, and the last 4 digits or reference as the row has it.
3. **Needs.** Unchecked `- [ ]` lines in `lists/needs.md`, as written, without the checkbox.

Reply with only the message, in exactly this shape: these four headings in this order, a dash
per item, dates as "Fri 4 Dec", "Nothing." under a heading with no items, and the line `TRIPS`
alone under the second heading (the trip results replace it). No preamble, no sign-off.

**To do**
- <item> (<page title>)

**Trips to finish booking**
TRIPS

**Expiring this week**
- <retailer> <kind>, <value>, expires <date> (<holder>, <last 4 or reference>)

**Needs**
- <item>
