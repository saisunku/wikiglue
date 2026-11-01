# Task: weekly shopping list

Inputs (any may be missing — skip those):
- `meal-plan/this-week.md` and the recipe pages it links to under `recipes/`
- `lists/needs.md` — unchecked `- [ ]` lines added during the week
- `lists/pantry.md` — staples; items marked `low` or `out`

1. Collect ingredients from the week's recipes (scale if the plan says so), the unchecked needs,
   and the low/out pantry items.
2. Merge duplicates (sum quantities where units match), drop things the pantry says are stocked.
3. Write `lists/shopping-<ISO year>-W<week>.md`:
   frontmatter `type: list`, `week:`; then sections by aisle
   (Produce, Dairy & eggs, Meat & fish, Bakery, Pantry, Frozen, Household, Other),
   each item `- [ ] item — quantity (for: recipe or who asked)`.
4. In `lists/needs.md`, change each need you included from `- [ ]` to `- [x]`.

Reply with the list itself (plain text, grouped by aisle), nothing else.
