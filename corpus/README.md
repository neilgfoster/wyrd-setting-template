# Corpus extraction

Turns raw PDFs under `library/` into plain text under `corpus/`, ready for `wyrd`'s
`tools/setting_pass0.py` and `tools/setting_build.py` to consume.

## Run it

```
corpus/extract.sh
```

From a fresh clone of a setting repo, this walks `library/`, and for every `*.pdf` it finds:

1. extracts the text layer with `pdftotext` if one exists (probed by sampling a few pages);
   otherwise falls back to `tesseract` OCR over rendered page images
2. strips OCR noise with `corpus/clean.py`
3. writes the result to `corpus/`, at the same relative path (with a `.txt` extension) that the
   PDF has under `library/`

`library/` itself is never modified -- the source PDF stays exactly where it was.

Re-running is safe and cheap: a PDF whose `corpus/`-mirrored `.txt` output already exists is
skipped, so an interrupted run picks back up without redoing finished work.

### Requirements

`pdftotext`, `pdfinfo`, `pdftoppm` (poppler-utils) and `tesseract` on `PATH`, plus Python
3.11+. None of this is stdlib-only -- unlike the engine repo (`wyrd`), this repo is not bound
by that constraint (see `neilgfoster/wyrd/CLAUDE.md`'s repository table and issue #1).

## Where extracted text lands, and why

**`corpus/` mirrors `library/`'s own directory structure**: `library/foo/bar.pdf`'s extracted
text lands at `corpus/foo/bar.txt`. The PDF is never deleted or moved -- `library/` is the
setting's permanent source library, and `corpus/` is a derived, regenerable tree alongside it.

This mirrors `library/`'s own layout for the same reason the earlier "replace in place" design
tried to satisfy: `tools/setting_pass0.py`'s catalogue step and `tools/setting_build.py`'s read
step both need a plain-text tree they can walk, with no PDFs mixed in. Pointing them at
`corpus/` instead of `library/` gets that without deleting anything (see
`neilgfoster/wyrd#393`, the engine-side change that reads from `corpus/`).

An earlier version of this pipeline deleted each PDF from `library/` once it was extracted,
ported directly from `wyrd-research/corpus/run.sh`. That behaviour existed to bound disk usage
during a *streaming remote-pull run*, where a PDF was fetched, extracted and discarded one at a
time so an entire remote corpus never had to sit on disk at once -- a scratch-directory
concern, not a repo-content policy. Once a PDF is already resident (and, in a private setting
repo, committed), there is no disk-pressure reason to discard it, and deleting it destroyed
data a re-run or an editorial re-extraction might need. `library/` is now never mutated by this
script, in either sourcing mode.

## Sourcing modes

Most settings will have their PDFs already sitting on disk under `library/` when this script
runs -- just run `corpus/extract.sh` with no arguments.

If a setting instead sources its library from a remote not checked into git (e.g. OneDrive),
pass a list file of relative `library/` paths:

```
corpus/extract.sh path/to/list.txt
```

Each listed path is fetched on demand via `tools/pull.py` into a scratch copy under
`corpus/work/`, extracted, and that scratch copy is deleted right after -- so disk usage stays
bounded to one source PDF at a time regardless of corpus size, the same streaming property
`wyrd-research/corpus/run.sh` had. This is unchanged by the PDF-deletion fix above: a PDF
fetched this way was never written into `library/` in the first place, so there is nothing
resident to preserve -- the fetch-and-discard behaviour is deliberate for a setting that keeps
its library remote rather than checked in. `tools/pull.py` talks to Microsoft Graph through an
rclone-managed OneDrive token; configure `PULL_RCLONE_REMOTE` and `PULL_RCLONE_ROOT` if your
remote isn't named `onedrive` or isn't rooted where the defaults assume. If your library isn't
OneDrive-backed, ignore `pull.py` entirely and use the default (no-list) mode once the PDFs are
locally present.

## Never commit real content

`wyrd-setting-template` is public. Do not run this tool here against a real library and
commit the result -- ship the tool only. Each setting repo (private, per
`neilgfoster/wyrd`'s repository table) is where it actually gets run against real PDFs.

## Failure log

Problems are appended to `corpus/failures.log` rather than stopping the run:

- `BADPDF <path>` -- `pdfinfo` couldn't read the file at all.
- `EMPTY <path>` -- OCR ran and found no usable text (e.g. an art-only page). Recorded so
  resumability (which requires non-empty output) doesn't retry it forever.
- `PULLFAIL <path>` -- the list-file fetch mode couldn't retrieve the file.

Successful extractions are logged to `corpus/progress.log` as `TEXT` (text-layer extraction)
or `OCR` (OCR fallback used).

Both log files, and the `corpus/work/` scratch directory, are gitignored.

## Testing

`tests/test_extract.py` drives the real pipeline (pdftotext/pdfinfo/pdftoppm/tesseract) against
synthetic fixture PDFs built by `tests/make_fixture_pdf.py` -- never against real content.

```
python3 -m pytest tests/
```
