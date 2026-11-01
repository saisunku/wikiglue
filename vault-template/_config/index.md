---
title: Index
type: index
---
# Index

<!--
This file is the template for wiki/index.md, which is rebuilt from it after every
wiki job (runner/wiki-index). Write any text, links and headings you want; they're
copied as is. A "pages:" line becomes one line per matching page, using its
title and summary:

  pages: trips/                pages in wiki/trips/
  pages: tags=dogs             pages tagged dogs (any front matter key works: type=topic)
  pages: trips/ end>=today     compare with today (also > < <=, and != to exclude)
  pages: sources/ sort=-added_at   sort by a key; "-" for newest first (default: title)
  pages: rest                  everything no other "pages:" line listed

(A comment like this one, between lines of just \<\!\-\- and \-\-\>, isn't copied.)
-->

## Family

<!-- pages: tags=family -->

## Household

- [[lists/needs|Needs]] — things to buy, added from chat
- [[lists/pantry|Pantry]] — staples and what's running low
<!-- pages: type=credits -->
<!-- pages: type=returns -->

## Upcoming trips

<!-- pages: trips/ end>=today sort=start -->

## Past trips

<!-- pages: trips/ end<today sort=-start -->

## Things we own

<!-- pages: household/ -->

### Next service (earliest first)

<!-- pages: household/ next_service>0 sort=next_service -->

## Summaries

<!-- pages: summaries/ -->

## Topics

<!-- pages: topics/ -->

## People, places and things

<!-- pages: entities/ tags!=family -->

## Weekly digests

<!-- pages: digests/ sort=-path -->

## Everything else

<!-- pages: rest -->
