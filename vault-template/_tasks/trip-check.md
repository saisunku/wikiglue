---
tools: read,grep,find,ls
time-limit-minutes: 5
---
# Task: check one trip's bookings

Input: $INPUT

The input names one trip page and lists every night of the trip. Don't change any file.

1. Read the trip page (and `_config/family_data.md` for where the travellers live: home).
2. **Nights.** Go through the listed nights one at a time. For each, find the stay that covers it
   in the page's Lodging bookings: a stay covers the nights from its check-in date up to, not
   including, its check-out date. A night is covered only by such a booking that isn't marked as
   still to reserve or book, or when the page says they stay at home or with family or friends
   that night. Every other night is missing.
3. **Travel.** The trip goes from home to its first place, between its places in order, and back
   home. Each of those legs needs a booked flight, train, bus or ferry, or the page saying they
   drive it (a rental car or their own car for that leg counts). A leg the page doesn't cover is
   missing.

Reply with only `OK` if nothing is missing. Otherwise one line per missing night or leg, and
nothing else:
`- no lodging the night of <Fri 4 Dec> in <place, if known>`
`- no <flight> <from> → <to> on <Sun 29 Nov>`
