#!/bin/bash
# Turn every PDF under library/ into plain text at the same relative path, then delete the
# PDF. Streaming: one PDF resident on disk at a time, so disk stays bounded regardless of
# corpus size. Fully resumable -- a file whose .txt already exists (non-empty) is skipped, so
# interrupting and re-running never redoes finished work.
#
# Adapted from wyrd-research/corpus/run.sh (that repo is retired; this is the reference
# implementation this pipeline ports -- see corpus/README.md).
#
# Two sourcing modes:
#   1. (default) Every PDF already sits on disk under library/. Just run this script.
#   2. A remote-listed corpus not checked into git (e.g. OneDrive). Pass a LIST file: one
#      relative library/ path per line, each fetched on demand via tools/pull.py before
#      extraction, so no more than one source PDF is resident on disk at a time. See
#      tools/pull.py's own header for the remote it expects to be configured against.
#
# Usage:
#   corpus/extract.sh                  # scan library/ for *.pdf already present
#   corpus/extract.sh path/to/list.txt # fetch each listed relative path via tools/pull.py first
set -u
export OMP_THREAD_LIMIT=1        # tesseract grabs every core per process without this
cd "$(dirname "$0")/.."          # repo root

LIST=${1:-}
LIBRARY=library
WORK=corpus/work
WORKERS=${EXTRACT_WORKERS:-4}
PROBE_THRESHOLD=${EXTRACT_PROBE_THRESHOLD:-800}
mkdir -p "$WORK"

log() { echo "$1" >> corpus/progress.log; }
fail() { echo "$1" >> corpus/failures.log; }

# Extract text from one on-disk PDF at $pdf into plain text at $out (already-cleaned).
# Deletes $pdf on success or genuine-empty-result; leaves it for a retry on a hard failure.
extract_one() {
  local pdf=$1 out=$2 rel=$3
  local pages
  pages=$(pdfinfo "$pdf" 2>/dev/null | awk '/^Pages/{print $2}')
  if [ -z "$pages" ]; then
    fail "BADPDF $rel"
    return 1
  fi

  # probe: sample up to 5 pages spread through the doc to see whether a text layer exists
  local probe=0 f c
  for f in 2 $((pages/4)) $((pages/2)) $((pages*3/4)) $((pages-1)); do
    [ "$f" -lt 1 ] && f=1; [ "$f" -gt "$pages" ] && f=$pages
    c=$(pdftotext -f "$f" -l "$f" "$pdf" - 2>/dev/null | tr -d '[:space:]' | wc -c)
    probe=$((probe + c))
  done

  local raw="$WORK/raw.txt"
  rm -f "$raw"
  if [ "$probe" -gt "$PROBE_THRESHOLD" ]; then
    pdftotext -layout "$pdf" "$raw" 2>/dev/null
    log "TEXT   $pages p  $rel"
  else
    rm -rf "$WORK/pg"; mkdir -p "$WORK/pg"
    local chunk=$(( (pages + WORKERS - 1) / WORKERS ))
    local w st en
    for ((w = 0; w < WORKERS; w++)); do
      st=$(( w*chunk + 1 )); en=$(( (w+1)*chunk )); [ "$en" -gt "$pages" ] && en=$pages
      [ "$st" -gt "$pages" ] && break
      (
        for ((p = st; p <= en; p++)); do
          t="$WORK/pg/$(printf '%05d' "$p")"
          pdftoppm -r 200 -gray -png -f "$p" -l "$p" "$pdf" "$t" 2>/dev/null
          img=$(ls "${t}"-*.png 2>/dev/null | head -1)
          [ -n "$img" ] && tesseract "$img" "$t" --psm 3 -l eng 2>/dev/null
          rm -f "${t}"-*.png
        done
      ) &
    done
    wait
    # shellcheck disable=SC2046  # intentional word-splitting of the sorted page-file list
    cat $(ls "$WORK/pg"/*.txt 2>/dev/null | sort) > "$raw" 2>/dev/null
    rm -rf "$WORK/pg"
    if [ -s "$raw" ]; then
      log "OCR    $pages p  $rel"
    else
      # genuine content, not a pipeline fault: OCR ran and found no text (e.g. an art-only
      # page). Record it explicitly so the resumability check (which requires non-empty
      # output) doesn't re-OCR it forever.
      fail "EMPTY  $rel"
      : > "$raw"
    fi
  fi

  mkdir -p "$(dirname "$out")"
  python3 corpus/clean.py "$raw" "$out"
  rm -f "$raw"
}

process_pdf() {
  local pdf=$1                         # absolute or repo-relative path to a resident PDF
  local rel=${pdf#"$LIBRARY"/}
  local out="${pdf%.pdf}.txt"
  [ -s "$out" ] && return 0            # resumable: already extracted

  extract_one "$pdf" "$out" "$rel"
  # Replace the PDF with its extracted text: matches wyrd-research/corpus/run.sh's own
  # behaviour and is what tools/setting_pass0.py and tools/setting_build.py expect --
  # every file under library/ must be UTF-8-readable text (see corpus/README.md).
  [ -s "$out" ] && rm -f "$pdf"
}

if [ -n "$LIST" ]; then
  while IFS= read -r rel; do
    [ -z "$rel" ] && continue
    out="$LIBRARY/${rel%.pdf}.txt"
    [ -s "$out" ] && continue          # resumable, skip the fetch entirely

    pdf="$WORK/cur.pdf"
    rm -f "$pdf"
    if ! python3 tools/pull.py "$rel" "$pdf" >/dev/null 2>&1; then
      fail "PULLFAIL $rel"
      continue
    fi
    mkdir -p "$(dirname "$LIBRARY/$rel")"
    extract_one "$pdf" "$out" "$rel"
    rm -f "$pdf"
  done < "$LIST"
else
  find "$LIBRARY" -name '*.pdf' -type f -print | sort | while IFS= read -r pdf; do
    process_pdf "$pdf"
  done
fi

echo "extract.sh complete"
