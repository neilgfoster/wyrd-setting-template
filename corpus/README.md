# Corpus extraction

Turns raw PDFs under `library/` into plain text, ready for `wyrd`'s
`tools/setting_pass0.py` and `tools/setting_build.py` to consume.

## Run it

```
corpus/extract.sh
```

From a fresh clone of a setting repo, this walks `library/`, and for every `*.pdf` it finds:

1. extracts the text layer with `pdftotext` if one exists (probed by sampling a few pages);
   otherwise falls back to `tesseract` OCR over rendered page images
2. strips OCR noise with `corpus/clean.py`
3. writes the result to the same relative path with a `.txt` extension
4. deletes the source PDF

Re-running is safe and cheap: a PDF whose `.txt` output already exists is skipped, so an
interrupted run picks back up without redoing finished work.

### Requirements

`pdftotext`, `pdfinfo`, `pdftoppm` (poppler-utils) and `tesseract` on `PATH`, plus Python
3.11+. None of this is stdlib-only -- unlike the engine repo (`wyrd`), this repo is not bound
by that constraint (see `neilgfoster/wyrd/CLAUDE.md`'s repository table and issue #1).

## Where extracted text lands, and why

**Each PDF is replaced in place**: `library/foo/bar.pdf` becomes `library/foo/bar.txt` at the
same relative path, and the PDF is deleted once extraction succeeds. No parallel tree, no
`library-text/` sibling directory.

This is a direct requirement of the two consumers this tool exists to feed:

- `tools/setting_pass0.py`'s catalogue step walks `library_dir.rglob("*")` -- *every* file
  under `library/`, with no extension filter -- and classifies each one by front matter/path
  hints.
- `tools/setting_build.py` reads every cataloged file as `library_dir / record.path`,
  `.read_text(encoding="utf-8")` -- with no fallback path for binary content.

A `library-text/` sibling tree would leave the PDFs themselves sitting under `library/`,
where `setting_pass0.py` would still catalogue them and `setting_build.py` would still throw
`UnicodeDecodeError` trying to read them as text. Replacing in place is the only option that
requires zero changes to either consumer -- which matches this issue's own scope (no changes
to `wyrd`'s tooling) and mirrors `wyrd-research/corpus/run.sh`'s own behaviour, the reference
implementation this pipeline ports.

The cost is that the original PDF bytes are gone once this runs. That is intentional and
matches the reference implementation: a setting's PDFs are its own working library, not this
repo's content, and are expected to be re-obtainable from wherever they were sourced (a
personal copy, a remote store) if ever needed again. This repo (`wyrd-setting-template`) never
holds or commits a real PDF or its extracted text -- see "Never commit real content" below.

## Sourcing modes

Most settings will have their PDFs already sitting on disk under `library/` when this script
runs -- just run `corpus/extract.sh` with no arguments.

If a setting instead sources its library from a remote not checked into git (e.g. OneDrive),
pass a list file of relative `library/` paths:

```
corpus/extract.sh path/to/list.txt
```

Each listed path is fetched on demand via `tools/pull.py` immediately before extraction, and
the fetched PDF is deleted right after -- so disk usage stays bounded to one source PDF at a
time regardless of corpus size, the same streaming property `wyrd-research/corpus/run.sh` had.
`tools/pull.py` talks to Microsoft Graph through an rclone-managed OneDrive token; configure
`PULL_RCLONE_REMOTE` and `PULL_RCLONE_ROOT` if your remote isn't named `onedrive` or isn't
rooted where the defaults assume. If your library isn't OneDrive-backed, ignore `pull.py`
entirely and use the default (no-list) mode once the PDFs are locally present.

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
