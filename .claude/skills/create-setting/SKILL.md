---
name: "create-setting"
description: "Drive a freshly-cloned wyrd-setting-* repository from extracted library sources through to a playable setting: extraction, orientation prompts, gap-derived step list, grounded content generation, and validation. Self-contained -- no kord, no GitHub issues, no epic/feature machinery."
argument-hint: "[path to the wyrd engine repo checkout, if not alongside this repo]"
user-invocable: true
disable-model-invocation: false
---

## What this skill does

Walks an operator (or an agent acting for one) through populating a `wyrd-setting-*` repository
end to end: extraction, two orientation questions, a gap report the engine computes, writing each
gap in dependency order, then validating what was written. It does not hard-code the list of
files a setting needs -- it asks the engine for that list every time, because a hand-copied
checklist and the engine's own requirements are exactly the kind of two-list drift this project's
own CLAUDE.md warns about.

This skill has one governing rule, stated once here so every phase below can just point back to
it:

> **Never invent a specific claim -- a name, a quote, a statistic, a faction, an NPC detail --
> that has no basis in this setting's own `corpus/` text or in the operator's explicit stated
> direction from Phase 1.** If neither source supports a detail you want to write, either leave
> it out, mark it as an invented placeholder the operator should confirm, or (if permitted) go
> get it from the web and say so.

---

## Known gotchas (read this before Phase 4, not after you hit them)

These have each cost real time on real runs. Do not rediscover them the hard way.

1. **Validator paths take the `setting/` subdirectory, not the repo root or a single file
   for the whole-surface check.**
   - `python3 <engine-repo>/tools/check_gear.py <setting-repo>/setting/gear.yaml`
   - `python3 <engine-repo>/tools/check_bestiary.py <setting-repo>/setting/bestiary.yaml`
   - `python3 <engine-repo>/tools/check_character_creation_data.py <setting-repo>/setting`
     (the **directory**, not a file inside it -- it reads `careers.yaml`, `loyalties.yaml`,
     `drives.yaml`, `misfortunes.yaml`, `names.yaml` and, if present, `ancestries.yaml` together)
   - `python3 <engine-repo>/tools/check_setting.py <setting-repo>/setting.yaml`

   Passing the setting repo root to `check_character_creation_data.py` looks like it should
   work and instead fails to find any of the files it needs. This has happened twice.

2. **The engine's YAML reader (`tools/check_bestiary.py`'s `read_yaml`, reused by every other
   `check_*.py`) does not support `>` or `|` block scalars.** A `key:` line must carry its
   scalar value on the same line, or the parser reads it as a nested block/`None` and every
   validator downstream reports confusing, unrelated-looking failures. Concretely:

   ```yaml
   # WRONG -- silently misparsed, not a load error you'll immediately recognise
   description: >
     One paragraph about the world.

   # RIGHT -- single-line, quoted if it contains a colon or other YAML-significant character
   description: "One paragraph about the world."
   ```

   This applies to every multi-line prose field across every setting file: `setting.yaml`'s
   `description`, `drives.yaml`/`misfortunes.yaml` `text`, gear/bestiary `notes`, everything.
   Write prose as one quoted line, however long.

3. **Two different engine-repo scripts matter here and they are not interchangeable.**
   `tools/setting_pass0.py` catalogues `library/` and reports the gap list; `tools/setting_build.py`
   runs Pass 0 *and* then builds the corpus text indexes (`index/documents.json`,
   `nouns.json`, `terms.json`, `tables.json`) from whatever `corpus/*.txt` extraction has
   already produced -- reading from `corpus/`, never from `library/`, for the actual text.
   Either gives you `index/gap_report.json`; prefer `setting_build.py` since it also refreshes
   the corpus indexes this skill's later phases search against.

---

## Phase 0 -- extraction

Before anything else, `corpus/` must hold extracted plain text for every source PDF under
`library/`. From the setting repo root:

```bash
corpus/extract.sh
```

This mirrors every PDF under `library/` to a `.txt` file at the same relative path under
`corpus/`, is safe to interrupt, and skips a file whose corpus counterpart already exists and is
non-empty -- re-running it is always safe and cheap. If `library/` is empty (a setting with no
material sourced yet, or one drawing only on operator direction and permitted web research), note
that plainly and continue -- Phase 2's gap-derivation and Phase 3's writing steps still work, they
simply have less grounding text to draw on and lean more on Phase 1's answers.

Confirm before moving on: `ls corpus/**/*.txt` (or equivalent) shows extracted text, or you have
explicitly noted there is none.

## Phase 1 -- two orientation questions, asked before any content is written

Ask both, in this order, before generating anything:

1. **"May I research the public web to supplement this setting's own library sources?"**
   Default to **no** if the operator does not answer. If the answer is yes, every later phase's
   output must say, for each specific claim, whether it came from the library (`corpus/`) or
   from the web -- do not blend the two silently. If the answer is no (or unanswered), every
   claim must trace to `corpus/` text or to the operator's own Phase 1 answer below; do not use
   general world-building knowledge to fill a gap the sources don't cover.

2. **"Do you have any additional creative direction or changes you want included, beyond what
   the library material alone would produce?"** Open-ended -- do not present it as a checklist
   or a form. If the operator has nothing to add, say so and move on silently; do not press for
   an answer that isn't there.

Record both answers (the web-research permission, and any stated direction) -- they govern every
phase that follows.

## Phase 2 -- derive the step list from the engine's own gap report

You need a checkout of the `wyrd` engine repository. If its path wasn't given as this skill's
argument, ask the operator where it is, or check the obvious sibling location
(`../wyrd` relative to this setting repo).

Run, from the setting repo root:

```bash
python3 <engine-repo>/tools/setting_build.py . --format json
```

This writes/refreshes `index/gap_report.json` (via Pass 0) and, where corpus text exists,
`index/documents.json`, `index/nouns.json`, `index/terms.json`, `index/tables.json`. Read
`index/gap_report.json` directly -- it lists, under a `gaps` key, exactly which of these
requirement categories the library does not yet evidence coverage for:

- `setting-identity` -- `setting.yaml`-shaped identity/tone coverage
- `voice` -- `voice.md`-shaped register/tone guidance
- `careers` -- `careers.yaml`-shaped career-graph coverage
- `gear` -- `gear.yaml`-shaped weapons/armour coverage
- `bestiary` -- `bestiary.yaml`-shaped adversary-block coverage
- `names` -- `names.yaml`-shaped naming coverage
- `calendar` -- `calendar.yaml`-shaped calendar coverage
- `loyalties` -- `loyalties.yaml`-shaped Loyalty coverage
- `drives` -- `drives.yaml`-shaped Drive coverage
- `misfortunes` -- `misfortunes.yaml`-shaped Misfortune coverage

**Do not treat this list as fixed.** It is reproduced here only so you know what to expect the
first time; the report you actually read may list more, fewer, or differently-named gaps if the
engine's requirements have changed since this file was written, or if some of this setting's
files already exist and satisfy a requirement. Walk what `gap_report.json` says today, not this
list.

## Phase 3 -- write each gap, in dependency order

Order matters because later files read the register and structures earlier ones establish. Use
this order for whatever subset of gaps Phase 2 actually reported:

1. **`setting.yaml`** (identity, tone contract) and **`voice.md`** (register, vocabulary,
   institutions, what danger and failure sound like) -- everything else is written in this
   voice, so get it right first. See `docs/design/24-authoring-a-setting.md`'s "voice.md is the
   hard part" section for what a good one contains.
2. **`names.yaml`** and **`calendar.yaml`** -- low-dependency world texture other files
   reference incidentally (a career's flavour, a Drive's phrasing).
3. **`careers.yaml`** -- the career graph. At least one entry with `entry: true`; every
   `prerequisites` entry names another career in the same file; the graph must be acyclic.
4. **`gear.yaml`** and **`bestiary.yaml`** -- weapons/armour and adversary blocks; these often
   reference careers and named factions once those exist.
5. **`loyalties.yaml`**, **`drives.yaml`**, **`misfortunes.yaml`** -- character-creation data
   that benefits from the world and career graph already existing to draw specific, grounded
   options from, rather than generic ones.
6. Anything else the gap report names beyond this list (e.g. a `deities.yaml`,
   `conversion.yaml` for a derived setting, or an `ancestries.yaml`) -- write it following the
   shape `docs/design/24-authoring-a-setting.md` in the engine repo gives for that file.

**For every specific claim -- a name, a quote, a statistic, a named faction, an NPC detail --
ground it in this setting's actual `corpus/` text or the operator's Phase 1 direction.** This is
the skill's one governing rule (stated at the top), repeated here because Phase 3 is where it is
most tempting to break: do not pad out a table with plausible-sounding invented names just to
hit a round number. A shorter, grounded table beats a longer, fabricated one.

Write prose fields as single-line quoted strings (gotcha 2, above) -- not `>` or `|` block
scalars.

## Phase 4 -- validate and review before calling anything final

For each file just written, run its validator (all from the engine repo, all take the paths
described in "Known gotchas" above):

| File | Validator |
|---|---|
| `setting.yaml` | `tools/check_setting.py <setting-repo>/setting.yaml` |
| `setting/gear.yaml` | `tools/check_gear.py <setting-repo>/setting/gear.yaml` |
| `setting/bestiary.yaml` | `tools/check_bestiary.py <setting-repo>/setting/bestiary.yaml` |
| `careers.yaml`, `loyalties.yaml`, `drives.yaml`, `misfortunes.yaml`, `names.yaml`, `ancestries.yaml` (together) | `tools/check_character_creation_data.py <setting-repo>/setting` |

Fix every reported failure before moving on -- each validator reports every problem it finds, not
just the first, so address the whole list in one pass rather than one failure at a time.

**Separately, for any named entity, quote, or statistic you claimed came from the source
material**, spot-check it with a direct grep against `corpus/` before treating it as final:

```bash
grep -rn "the exact name or phrase" corpus/
```

Do not trust your own earlier claim that something came from the library -- verify it landed
there, the same discipline this skill asked of Phase 3's writing. If a grep turns up nothing,
either the claim is actually from the web (and must be labelled as such per Phase 1) or it was
invented and must be removed, softened to an explicit placeholder, or replaced with something the
corpus does support.

## Summary checklist

- [ ] Phase 0: `corpus/extract.sh` run, or its absence explicitly noted
- [ ] Phase 1: both orientation questions asked and answers recorded, before any writing
- [ ] Phase 2: `setting_build.py` run against this setting dir; `index/gap_report.json` read
      directly, not assumed from memory
- [ ] Phase 3: every gap written, in dependency order, every specific claim traceable to
      `corpus/` or stated operator direction (or, if permitted, labelled as web-sourced)
- [ ] Phase 4: every written file's validator run and clean; source claims spot-checked with a
      direct `corpus/` grep
