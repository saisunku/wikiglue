---
thinking: off
---
# Task: update a trip page

Input: $INPUT

The input is either a trip note from chat (ends with who sent it and when), or a source folder
under `raw/` whose source is a travel booking (from the ingest task, which wrote its
`wiki/sources/<slug>.md` page already).

1. **Find the trip.** Read each page in `wiki/trips/`. The input belongs to the trip whose dates
   (`start`–`end`) overlap its own, whatever the city: one trip can cover several places (a rental
   car at home, then a stay in Banff), and a different city isn't a conflict to flag. Update
   that trip's title, `destination` and summary to cover every place. It's a separate trip only
   when both name family members and nobody in common (one in Napa while the other is in Austin);
   unnamed travellers ("6 adults") don't make it separate. Input without dates goes by place
   (`destination` or a city in a trip's Itinerary or Bookings).
   - A chat note without dates ("day 5", "in Kyoto") belongs to the upcoming trip that goes there;
     "day N" is the Nth day from `start`. The date the note was sent is not a trip date.
   - No trip fits and the input is a booking: create `wiki/trips/<YYYY-MM>-<place>.md` from
     `_config/templates/trip.md` (`<place>`: the country or region if it covers several cities).
   - No trip fits and it's a chat note: create a trip only if the note gives its dates and place.
     Otherwise, or if you can't tell which trip it is, change nothing and reply asking.
   - **Home**: where each traveller lives is in `_config/family_data.md`. Home is where a trip starts
     and ends, not a destination: name the trip after where it goes, show travel days as leaving
     or returning home, and head nights spent at home `— Home`.
   - **The year**: use the year written with the trip's own dates in the booking (the email,
     PDF or image), such as "Sun, Aug 1, 2027"; an issue, booking or payment date doesn't count.
     If it isn't there, don't guess: add the booking to no trip, and reply with a line
     `Question: which year is <the booking and its dates> (sources/<slug>)? Answer with
     "trip: sources/<slug> is in <year>"`.
   - A chat note "sources/<slug> is in <year>" answers that question: read that source page and
     its `raw/` source, and add the booking in that year, as for any booking.
2. **Add what's new**, editing only the sections it belongs in:
   - **Bookings**: one bullet per booking under its heading: what, provider, confirmation number,
     dates and local times, address or airports/terminals, travellers, cost, cancellation
     deadline. Cite it: `([[sources/<slug>]])`, or `(<who>, <date>)` for a chat note.
   - **Itinerary**: a section for every day from `start` to `end`, headed like `### Sun 6 Dec — Bend`,
     in date order. `<city>` is where you sleep that night (from Lodging, or the arrival city on
     a travel day); leave it out if unknown. A stay covers every night from check-in to the
     night before check-out: the check-in day gets `- <time> Check in: <place>`, each day after
     it until check-out gets `- Staying at <place>`, and the check-out day gets
     `- <time> Check out: <place>`. Leave a day with nothing else on it at that; never write
     "nothing booked" or "nothing planned". Under each day, every timed item,
     sorted by time: flights (departure and arrival in local time, flight number, airports;
     an arrival on a later day goes under that day), check-in and check-out, reservations,
     tickets, and planned activities. Brief; details stay in Bookings.
   - Ideas without a day go under **Ideas**; things to do before leaving under **To do** as
     `- [ ] ...`.
   - **Travellers' pages**, even when the trip page itself needs no change: for each traveller
     listed in `_config/family_data.md`, their page links this trip under Trips, and any loyalty
     number in the input (SkyMiles, MileagePlus, Marriott Bonvoy, Known Traveler…) is under
     its frequent flyer section, cited.
   - If a booking falls outside `start`–`end`, extend them. If a booking changes or cancels an
     earlier one, update that one and say so; don't keep both.
3. Update front matter: `destination` (every city, e.g. "Tokyo and Kyoto, Japan"), `travelers`
   (first names). Also update `sources` (add the slug), `updated`, and `summary`
   (dates, where, who, what's booked so far; one line).
4. Re-read the Itinerary: exactly one heading per date, in order, each city matching Lodging,
   and every night of each stay shown. Fix what doesn't.
5. Add to the top of `wiki/log.md`, right under `# Log`: `## <today> trip <page>` and one bullet on what changed.

Reply with one line: the trip page and what changed (or your question).
