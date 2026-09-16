---
name: "create-setting"
description: "Drive a freshly-cloned wyrd-setting-* repository from extracted library sources through to a playable setting: extraction, orientation prompts, gap-derived step list, grounded content generation, and validation. Self-contained -- no kord, no GitHub issues, no epic/feature machinery."
argument-hint: "[path to the wyrd engine repo checkout, if not alongside this repo]"
user-invocable: true
disable-model-invocation: false
model: sonnet
---

## What this skill does

Walks an operator (or an agent acting for one) through populating a `wyrd-setting-*` repository
end to end: extraction, two orientation questions, deriving what's still missing by checking
`setting/` and `entities/` file existence directly, writing each missing category in dependency
order, then validating what was written. It does not hard-code the list of files a setting needs
-- it asks the engine's `docs/design/24-authoring-a-setting.md` for that list every time, because
a hand-copied checklist and the engine's own requirements are exactly the kind of two-list drift
this project's own CLAUDE.md warns about. It also knows how to re-run cleanly against a setting
that's already fully populated, rather than mistaking "nothing changed" for "nothing done."

This skill has one governing rule, stated once here so every phase below can just point back to
it:

> **Never invent a specific claim -- a name, a quote, a statistic, a faction, an NPC detail --
> that has no basis in this setting's own `corpus/` text or in the operator's explicit stated
> direction from Phase 1.** If neither source supports a detail you want to write, either leave
> it out, mark it as an invented placeholder the operator should confirm, or (if permitted) go
> get it from the web and say so.
>
> **The one narrow exception:** if Phase 1 Q3 was explicitly granted, original elaboration with
> no basis in `corpus/`, the web, or the operator's stated direction may be invented, gated
> instead on consistency with this setting's established tone, register, and existing facts --
> re-read `voice.md` and the setting's existing `entities/`/`setting/` files before inventing
> anything, and reject an invented detail that contradicts what's already established, the same
> rigor Phase 4 applies to a web-sourced claim that fails its corpus-fact-finder spot-check. This exception applies only when
> Q3 was actually granted -- it is never assumed by default, and it does not loosen the rule
> above for anyone who didn't grant it. Anything written under it is labelled distinctly (e.g.
> "invented, per Phase 1 Q3"), never blended with library- or web-sourced claims.

**A second thing stated once here, for the same reason:** this skill itself runs on the capable
(Sonnet) tier -- see its frontmatter -- but not every step in it needs that tier. Locating a
specific quote or fact in `corpus/` to check whether it supports a claim has a checkable right
answer (the text either says it or it doesn't); writing `voice.md`'s register, composing
career/gear/bestiary/entity content, and deciding what belongs or how to hedge on a thin source do
not. `docs/design/27-tooling.md` section 5 in the engine repo calls the first kind "mechanical
language work with a right answer" (Haiku-tier) and keeps the second kind ("judgement about what a
result means") on the capable model. Phases 3 and 4 below act on that split: every corpus
fact-grounding or verification lookup is delegated to the `corpus-fact-finder` subagent
(`.claude/agents/corpus-fact-finder.md`, `model: haiku`) rather than read or searched inline; every
actual writing and register/content-judgement decision stays here, on this skill's own Sonnet-tier
invocation. If you find yourself reading `corpus/` text directly to decide whether a claim holds,
stop -- that lookup belongs to the subagent.

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

## Phase 1 -- three orientation questions, asked before any content is written

Ask all three, in this order, before generating anything:

1. **"May I research the public web to supplement this setting's own library sources?"**
   Default to **no** if the operator does not answer. A yes here is an active instruction to go
   use the web, not a dormant permission that only matters if something else happens to trigger
   writing:
   - **On a first run** (categories being written for the first time), Phase 3 is already going
     to write every missing category regardless of this answer. A yes simply means that, while
     writing those categories, web-sourced material may supplement `corpus/` wherever the
     library falls short, with every such claim labelled as web-sourced -- see Phase 3. There is
     nothing further to trigger here: the permission is exercised as part of the writing Phase 3
     was always going to do.
   - **On a re-run of an already-complete setting** (Phase 2 Step 4, where every required
     category already has a file, so nothing else is about to trigger a writing pass), a yes is
     its **own** trigger for action -- Step 4 gives it an explicit question and path, distinct
     from "does the operator have their own direction." See Step 4, question 3, below.

   Either way: every later phase's output must say, for each specific claim, whether it came from
   the library (`corpus/`) or from the web -- do not blend the two silently. If the answer is no
   (or unanswered), every claim must trace to `corpus/` text or to the operator's own Phase 1
   answer below; do not use general world-building knowledge to fill a gap the sources don't
   cover.

2. **"Do you have any additional creative direction or changes you want included, beyond what
   the library material alone would produce?"** Open-ended -- do not present it as a checklist
   or a form. If the operator has nothing to add, say so and move on silently; do not press for
   an answer that isn't there.

3. **"May I invent original material of my own -- names, minor characters, texture, incidental
   world detail -- with no basis in the library, the web, or your own stated direction, as long
   as it stays consistent with this setting's established tone and existing facts?"** Default to
   **no** if the operator does not answer, same as Q1. This is a distinct, third kind of
   permission -- not a variant of Q1 (real external material) or Q2 (the operator's own ideas) --
   it is the skill's own creative judgment, gated only on consistency rather than on tracing to
   any source. A yes grants the governing rule's narrow exception (stated at the top of this
   file, and restated in Phase 3): invented content may be written, but only after re-reading
   `voice.md` and the setting's existing `entities/`/`setting/` files, and only where it does not
   contradict an established name, fact, or register choice. Every claim written under this
   permission is labelled distinctly from library- and web-sourced claims (e.g. "invented, per
   Phase 1 Q3") -- see Phase 3. Like Q1, a yes here matters on both a first run (Phase 3 may draw
   on it while writing missing categories) and a re-run of an already-complete setting (Phase 2
   Step 4 gives it its own explicit trigger, question 4, since nothing else on a re-run would
   invoke it).

Record all three answers (the web-research permission, any stated direction, and the
original-invention permission) -- they govern every phase that follows.

## Phase 2 -- derive the step list from what's actually on disk

**Progress is what files exist, not what `gap_report.json` says.** `gap_report.json` (written by
the engine's `tools/setting_pass0.py`, via `build_gap_report`) reports whether this setting's
`library/` material *evidences* a requirement category -- it never looks at `setting/` or
`entities/` at all, so it cannot tell "nothing written yet" from "fully written, library
unchanged since." Read `index/gap_report.json` as a pre-flight check on the library, never as the
list of what to write.

You need a checkout of the `wyrd` engine repository. If its path wasn't given as this skill's
argument, ask the operator where it is, or check the obvious sibling location
(`../wyrd` relative to this setting repo).

### Step 1 -- refresh the indexes

Run, from the setting repo root:

```bash
python3 <engine-repo>/tools/setting_build.py . --format json
```

This writes/refreshes `index/gap_report.json` (via Pass 0) and, where corpus text exists,
`index/documents.json`, `index/nouns.json`, `index/terms.json`, `index/tables.json`,
`index/corpus_build_cache.json`.

### Step 2 -- check file existence directly for every category

Check each of these categories by whether its file already exists on disk. **Do not treat this
list as fixed** -- it is reproduced so you know what to expect, but confirm against
`docs/design/24-authoring-a-setting.md` in the engine repo if a setting has files this list
doesn't name:

| Category | Check |
|---|---|
| `setting-identity` | `setting.yaml` exists |
| `voice` | `setting/voice.md` exists |
| `careers` | `setting/careers.yaml` exists |
| `gear` | `setting/gear.yaml` exists |
| `bestiary` | `setting/bestiary.yaml` exists |
| `names` | `setting/names.yaml` exists |
| `calendar` | `setting/calendar.yaml` exists |
| `loyalties` | `setting/loyalties.yaml` exists |
| `drives` | `setting/drives.yaml` exists |
| `misfortunes` | `setting/misfortunes.yaml` exists |
| `organisations` | at least one `entities/**/*.yaml` file with frontmatter `type: organisation` |
| `threat-arc` | at least one `entities/**/*.yaml` with `type: arc` that has at least one `type: beat` file naming it as `parent` |

The last two are never in Pass 0's `SETTING_REQUIREMENTS` -- they were never covered by the gap
report even before this fix -- so they must be checked directly, always. **Check by frontmatter
`type:` field, not by directory name.** A setting's `entities/` directory layout may predate the
engine's current ten-type model (`character`, `place`, `organisation`, `arc`, `beat`, `creature`,
`item`, `tracker`, `thread`, `lore` -- see `docs/design/25-entities.md`) -- an `organisation`
entity may live under a legacy directory like `entities/faction/`, and an `arc` may live under
`entities/scenario/` or similar. Grep frontmatter, don't assume the directory name:

```bash
grep -rl '^type: organisation$' entities/
grep -rl '^type: arc$' entities/
grep -rl '^type: beat$' entities/
```

### Step 3 -- for any category still missing a file, consult the gap report

For each category from Step 2 with no file yet, check whether `index/gap_report.json`'s `gaps`
list includes the matching requirement (`organisations` and `threat-arc` will never appear there
-- Pass 0 doesn't track them, so for those two, judge grounding directly from `corpus/` instead).
If the library doesn't evidence a category the operator still wants written, say so plainly
rather than writing it ungrounded -- an explicit "the library doesn't support this; here's what's
missing" is a valid Phase 2 outcome, not a failure.

### Step 4 -- if every required category already has a file

This is a genuine re-run against an already-complete setting. **Do not silently stop, and do not
regenerate anything by default.** Ask the operator four questions -- these are four separately
actionable yeses, not one "anything to add?" catch-all, so ask all four even if an earlier one
was already answered yes:

1. **Has new library material been added since the last run?** Read Step 1's own
   `setting_build.py . --format json` output -- its `processed` and `removed` list fields, computed
   from Pass 0's content-hash idempotence check. If both are empty, nothing has genuinely changed;
   say so, full stop. If either is non-empty, a source document was genuinely added, changed, or
   removed -- report exactly what `processed`/`removed` name and ask whether to incorporate it.
2. **Do they want to expand or add to any existing category beyond what's there today** -- more
   careers, another organisation, a second arc, and so on -- independent of new library material?
   This is the operator's own stated creative direction (Phase 1 Q2's channel): "I have my own
   ideas."
3. **If Phase 1's web-research question was answered yes, actively perform (or clearly propose)
   web research for this setting's existing categories.** This is not the same question as #2 and
   is not answered by a "no" to it -- it is the downstream effect of Phase 1 Q1's permission
   ("go find things for me"), and on a re-run it has no other trigger, so it must be asked and
   acted on explicitly here. Search for supplementary, tie-in, or texture-adding material for
   categories that already exist: named lore connected to what's already written, related media
   or source works, setting-specific facts the library doesn't cover. Bring back **concrete
   findings** -- specific names, facts, or passages found, each with its source -- for the
   operator's approval before writing anything; do not just report "I could search the web" as if
   raising the possibility were the deliverable. If web-research permission was not granted
   (Phase 1 Q1 was no or unanswered), skip this question -- do not ask it, and do not perform web
   research anyway.
4. **If Phase 1's original-invention question (Q3) was answered yes, actively propose original,
   tone-consistent elaboration for this setting's existing categories.** This is not the same
   question as #2 or #3 and is not answered by a "no" to either of them -- it is the downstream
   effect of Phase 1 Q3's permission, and on a re-run it has no other trigger, so it must be
   asked and acted on explicitly here, the same shape #11 established for question 3. Before
   proposing anything, re-read `voice.md` and the setting's existing `entities/`/`setting/`
   files. Propose **concrete invented additions** -- specific names, minor characters, texture,
   incidental detail -- each checked against established tone and existing facts, for the
   operator's approval before writing anything; do not just report "I could invent something" as
   if raising the possibility were the deliverable. Reject any candidate that contradicts an
   existing name, fact, or register choice. If this permission was not granted (Phase 1 Q3 was no
   or unanswered), skip this question -- do not ask it, and do not invent original content
   anyway.

If any answer is yes, determine what to write from newly-extracted `corpus/` text (diffed against
what the existing files already draw on, where feasible), the operator's stated direction, the
concrete web findings from question 3, and/or the concrete invented additions from question 4 --
never re-derive content for an already-existing file from `gap_report.json`'s binary signal,
which cannot express "already covered, but incompletely." Every claim drawn from question 3's web
research is labelled as web-sourced per Phase 1's rule, the same as any other web-sourced claim;
every addition drawn from question 4's invention permission is labelled distinctly (e.g.
"invented, per Phase 1 Q3"), never blended with library- or web-sourced claims.

If every answer is no (including question 3 and/or question 4 being skipped because their
permissions were never granted), **report the setting complete and stop.** This is a legitimate,
expected outcome, not a failure to find something to do.

## Phase 3 -- write each missing category, in dependency order

Order matters because later files read the register and structures earlier ones establish. Use
this order for whatever subset of categories Phase 2 found missing -- on a first run that's
likely everything; on a re-run of an already-complete setting (Phase 2 Step 4) it's only what the
operator's answers actually call for, from newly-extracted material and/or their stated
direction, never a wholesale rewrite of files that already exist:

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
6. **`entities/` organisations and Threat/arc** -- at least one `organisation` entity and at
   least one `arc` entity with a supporting `beat` entity, in whatever directory this repo's
   `entities/` convention actually uses (check the live layout, don't assume `entities/organisation/`
   or `entities/arc/` -- see Phase 2 Step 2). Follow `docs/design/25-entities.md`'s frontmatter
   shape and `docs/design/18-arcs-and-beats.md` for how an arc and its beats relate.
7. Anything else Phase 2 found missing beyond this list (e.g. a `deities.yaml`,
   `conversion.yaml` for a derived setting, or an `ancestries.yaml`) -- write it following the
   shape `docs/design/24-authoring-a-setting.md` in the engine repo gives for that file.

**For every specific claim -- a name, a quote, a statistic, a named faction, an NPC detail --
ground it in this setting's actual `corpus/` text or the operator's Phase 1 direction.** This is
the skill's one governing rule (stated at the top), repeated here because Phase 3 is where it is
most tempting to break -- including on a re-run: content written to answer Phase 2 Step 4's
expansion questions is still bound by this rule, whether it comes from newly-extracted `corpus/`
text or the operator's fresh direction. Do not pad out a table with plausible-sounding invented
names just to hit a round number. A shorter, grounded table beats a longer, fabricated one.

**Do the grounding lookup itself by invoking the `corpus-fact-finder` subagent, not by reading or
grepping `corpus/` yourself.** Before writing a specific claim, state the claim plainly and hand
it to the subagent along with the relevant `corpus/` location (a whole-setting search when you
don't yet know where to look, a narrower file/directory once you do); it reports back one of three
outcomes -- supported (with the exact quote and its source location), contradicted (with the
exact contradicting quote and location), or not found. Write from what it reports:

- **Supported** -- write the claim, and keep the subagent's quote/location on hand for Phase 4's
  spot-check.
- **Contradicted** -- do not write the original claim; either drop it, or write what the corpus
  actually says instead.
- **Not found** -- the claim has no library grounding. Leave it out, mark it as an invented
  placeholder for the operator to confirm, or (if Phase 1 Q1 was granted) go get it from the web
  and label it as such -- the same choices the governing rule already offers, just reached via the
  subagent's report instead of your own reading.

This is a mechanical retrieval step, not a judgement call -- see the frontmatter note near the top
of this file for why it is delegated. What to do with the result (write it, soften it, drop it,
label it) is still this skill's own decision, made here in Phase 3, not the subagent's.

**The one narrow exception** is Phase 1 Q3, when explicitly granted: original elaboration with no
basis in `corpus/`, the web, or the operator's stated direction may be written, gated instead on
consistency with this setting's established tone, register, and existing facts. It is never
assumed by default -- only write under it when Q3 (or Step 4 question 4, on a re-run) was actually
answered yes. Before writing anything under it, re-read `voice.md` and the setting's existing
`entities/`/`setting/` files, and reject any candidate that contradicts an established name, fact,
or register choice, with the same rigor Phase 4 applies when a web-sourced claim fails its
corpus-fact-finder spot-check. Every claim written under this permission is labelled distinctly (e.g. "invented, per
Phase 1 Q3") -- never blended with library- or web-sourced claims.

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
material**, spot-check it before treating it as final -- by invoking the `corpus-fact-finder`
subagent again, the same way Phase 3 did, with the exact claim as written and `corpus/` as the
location to search. This is the same mechanical retrieval call, run a second time as a check
rather than a first-draft lookup; do not grep `corpus/` yourself inline.

Do not trust your own earlier claim that something came from the library -- verify it landed
there, the same discipline this skill asked of Phase 3's writing. If the subagent reports
not-found (or contradicted), either the claim is actually from the web (and must be labelled as
such per Phase 1) or it was invented and must be removed, softened to an explicit placeholder, or
replaced with something the corpus does support.

## Summary checklist

- [ ] Phase 0: `corpus/extract.sh` run, or its absence explicitly noted
- [ ] Phase 1: all three orientation questions asked and answers recorded, before any writing
      (web-research permission, operator direction, original-invention permission)
- [ ] Phase 2: `setting_build.py` run; every category checked by file existence on disk
      (`setting/`, `entities/` by frontmatter `type:`, including organisations and Threat/arc);
      `gap_report.json` consulted only as a pre-flight check for categories still missing a file;
      if everything already exists, all four re-run questions were asked (new material?, own
      direction?, -- if web research was permitted -- active web elaboration with concrete
      findings offered, and -- if original invention was permitted -- concrete invented additions
      proposed) rather than silently stopping, regenerating, or treating "no" to one question as
      covering another
- [ ] Phase 3: every category Phase 2 found missing (or that the operator asked to expand) is
      written, in dependency order, every specific claim's corpus grounding looked up via the
      `corpus-fact-finder` subagent rather than read inline, and traceable to `corpus/` or stated
      operator direction (or, if permitted, labelled as web-sourced, or, if permitted under the
      narrow Q3 exception, labelled as invented and checked against `voice.md` and existing
      facts)
- [ ] Phase 4: every written file's validator run and clean; source claims spot-checked via the
      `corpus-fact-finder` subagent, not a direct inline grep
