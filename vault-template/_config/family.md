# Family

The family list is in `_config/family_data.md`, one line per person:

    - <Name as shown> — [[entities/<first-name>]] — lives in: <city, region, country> — also: <other names>

- Everyone listed gets a page in `wiki/entities/` (tagged `family`), started from
  `_config/templates/person.md`. The wiki agent adds facts about them there and never makes a
  second page for them.
- Where they live is home for trips: where trips start and end.
- Other names (full name, nicknames) let the agent recognise them in sources; leave out
  `— also: ...` if there are none.
- Add someone by editing the list. The agent can't change it.

This file is the same for every wiki (copied from vault-template/);
the list itself is this wiki's own and isn't in the repo.
