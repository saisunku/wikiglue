---
# Measured with a 35B-A3B model: 2.7x faster than low, no facts lost.
thinking: off
# A reasonable source takes 20-90 s; a stuck job shouldn't hold the queue for long.
time-limit-minutes: 5
---
# Task: ingest a source

Source folder: `$INPUT`

1. Read `meta.json` and the source (`source.md`, and look at any images) in that folder.
   If the folder has `part-1.md`, the source is long and is ingested in parts: read `part-1.md`
   instead of `source.md` (later parts are separate tasks), add `Covers: part 1 of <total>` under
   the summary of the source page, and log `## <today> ingest <slug> (part 1 of <total>)`.
2. Read `wiki/index.md`. If `wiki/sources/<slug>.md` already exists, this is a **re-ingest**: the
   source has been updated since. Compare it line by line with the source page and the pages that
   cite it, and fold in every fact that's missing (steps 3–6 apply to those facts only). Don't stop
   at "already ingested". Log it as `## <today> re-ingest <slug>`.
3. Write `wiki/sources/<slug>.md` (slug = the folder name). Frontmatter `type: source`, plus `url`,
   `added_by`, `added_at` from meta.json. Body: 2–4 sentence summary, "Key points" (bullets),
   "Raw" link to the folder (`[[raw/YYYY/MM/<slug>/source|original]]`).
4. If the source is a travel booking or itinerary (flight, hotel, rental, train, tickets, a
   reservation), follow `_tasks/trip.md` with this source folder as its input, instead of this
   step and the next one. Then continue at step 5b.
   Otherwise, decide which topic/entity pages this source should change: update existing ones that it adds to,
   create new ones only for subjects it covers substantially (usually 1–4 pages total).
   `grep -ril` the wiki for key names before creating anything.
5. Edit each of those pages: add the new facts with citations to `[[sources/<slug>]]`, add the slug to
   frontmatter `sources`, bump `updated`, and add `Related` links both ways.
5b. Facts about someone listed in `_config/family_data.md` (by any of their names) go on their page,
   under the matching section of `_config/templates/person.md` (food, health, sizes and gifts,
   dates, frequent flyer and travel programmes, trips, notes), cited like any other fact.
5c. Facts about something the household owns and looks after (a car, computer, appliance, furniture,
   tool): a receipt, order confirmation, warranty, manual, service or repair record, or a note about
   it. They go on its page in `wiki/household/` (`grep -ril` for its make, model or serial number
   first), or a new `wiki/household/<make>-<model>.md` from `_config/templates/item.md`, under the
   matching section, cited. Keep `purchased`, `warranty_until` and `next_service` in the front
   matter up to date (YYYY-MM-DD; leave out what isn't known), and add each service or repair to
   Service history with its date.
5d. A gift card, flight or travel credit, store credit or voucher, or a credit card offer to use at
   a retailer (Amex Offers, Chase Offers...): a row on `wiki/credits.md` (create it from
   `_config/templates/credits.md` if it doesn't exist), in its section, cited. Keep each table
   sorted by Expires: insert a new row above the first row that expires later.
   If the source changes one already there (a new balance, used up, extended), update that row.
   Follow the notes in the page's comments: never a full gift card number or a PIN.
5e. A return (a return code, return label or return authorisation, mostly Amazon): a row on
   `wiki/returns.md` (create it from `_config/templates/returns.md` if it doesn't exist), cited,
   sorted by Return by like credits. A drop-off receipt or refund for one already there: delete its
   row and add a line under "Done", as the page's comments say.
5f. An event, activity or place to visit near home (where the family lives, in
   `_config/family_data.md`, or a day trip from it): a festival, concert, show, market, class,
   exhibition, park, hike, museum, attraction. It goes on `wiki/nearby.md` (create it from
   `_config/templates/nearby.md` if it doesn't exist), cited: a dated event as a row in Events,
   sorted by Date; anything undated under Places and activities. One already there: update it.
   Do this as well as steps 4–5, not instead. An event or place far from home doesn't go here.
6. Give each page you created a `summary:` in its front matter (one line, for the index), and
   update the `summary:` of pages whose scope changed. Don't edit `wiki/index.md`: it's generated.
7. Add to the top of `wiki/log.md`, right under `# Log`: `## <today> ingest <slug>` then one bullet per page touched.
8. If the source refers to values that aren't anywhere in it (a rating scale's two ends, like
   `IndependentLovey-Dovey`, with no score for it in the text or under "Details from the page";
   a chart or table mentioned with no numbers; a figure that isn't in the folder), don't guess
   them from the labels. Append one line to
   `_review/missing-from-sources.md`:
   `- <today> [[raw/YYYY/MM/<slug>/source|<slug>]] — <what's missing, e.g. "6 trait ratings shown only as scale ends">`

Reply with the list of pages created/updated, and any `Question:` line from `_tasks/trip.md`
as it is (it's posted to the family chat). Start no other line with `Question:`.
