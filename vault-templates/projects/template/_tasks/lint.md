---
script: wiki-lint
time-limit-minutes: 30
# Folders of wiki/ whose pages should be linked from another page, and whose changed pages
# are reviewed for duplicates and contradictions.
orphan-folders: projects topics entities
review-folders: projects topics entities
---
# Task: nightly wiki cleanup

Run nightly by a schedule. `wiki-lint` (next to the job runner) does it in steps, so the model
never has to hold the whole wiki in mind:

1. Finds, without the model: links in `wiki/` that point at nothing, images loaded from the
   internet, pages missing `title:` or `summary:`, front matter the website can't read, and pages
   in the folders above that nothing links to.
2. Runs `_tasks/lint-fix.md` on those, about ten at a time.
3. Runs `_tasks/lint-review.md` on the pages changed since the last lint (duplicates,
   contradictions) and pages not updated in over a year (stale claims), a few at a time.
4. Writes one `## <today> lint` entry in `wiki/log.md` from what the jobs changed.

It stops starting jobs after 25 minutes; whatever is left is found again the next night.
To change how problems are fixed, edit those two task files.
