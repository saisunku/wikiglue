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

## Topics

<!-- pages: topics/ -->

## Tools

<!-- pages: tools/ -->

## Summaries

<!-- pages: summaries/ -->

## Papers (newest first)

<!-- pages: sources/ kind=paper tags!=out-of-scope sort=-published -->

## Posts and articles

<!-- pages: sources/ kind=post tags!=out-of-scope sort=-published -->

## Videos and talks

<!-- pages: sources/ kind=video,talk tags!=out-of-scope sort=-published -->

## Books and docs

<!-- pages: sources/ kind=book,docs tags!=out-of-scope -->

## Other sources

<!-- pages: sources/ kind!=paper,post,video,talk,book,docs tags!=out-of-scope sort=-added_at -->

## Out of scope

<!-- pages: sources/ tags=out-of-scope sort=-added_at -->

## People and organisations

<!-- pages: entities/ -->

## Weekly digests

<!-- pages: digests/ sort=-path -->

## Everything else

<!-- pages: rest -->
