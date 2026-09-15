"""Tests for corpus/extract.sh and corpus/clean.py.

Runs the real pipeline (pdftotext/pdfinfo/tesseract) against synthetic fixture PDFs built by
make_fixture_pdf.py -- never against real copyrighted content, per issue #1's constraint.
Text-layer extraction is exercised end to end; the OCR fallback path is exercised via
corpus/clean.py directly (unit-level) since driving a real OCR run in CI is slow and the
noise-stripping logic is what actually needs covering.
"""

import pathlib
import shutil
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tests"))
from make_fixture_pdf import make_text_pdf  # noqa: E402

EXTRACT = REPO_ROOT / "corpus" / "extract.sh"
CLEAN = REPO_ROOT / "corpus" / "clean.py"


def _run(*args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def test_extract_writes_to_corpus_and_leaves_library_untouched(tmp_path):
    """A PDF under library/ stays exactly where it is; the extracted text lands under corpus/
    at the same relative path, with a .txt extension."""
    repo = tmp_path / "setting"
    shutil.copytree(REPO_ROOT / "corpus", repo / "corpus")
    shutil.copytree(REPO_ROOT / "tools", repo / "tools")
    (repo / "library").mkdir(parents=True)
    pdf = repo / "library" / "sourcebook.pdf"
    make_text_pdf(
        pdf,
        [
            "This is a real paragraph of extractable prose text.",
            "It spans more than one line so the probe finds it.",
        ],
    )
    pdf_bytes_before = pdf.read_bytes()

    result = _run("bash", str(repo / "corpus" / "extract.sh"), cwd=repo)
    assert result.returncode == 0, result.stderr

    assert pdf.exists(), "source PDF must never be deleted"
    assert pdf.read_bytes() == pdf_bytes_before, "source PDF must never be modified"

    out = repo / "corpus" / "sourcebook.txt"
    assert out.exists(), result.stdout + result.stderr
    text = out.read_text(encoding="utf-8")
    assert "real paragraph of extractable prose" in text
    assert "spans more than one line" in text


def test_extract_is_resumable(tmp_path):
    """A file whose corpus/-mirrored .txt already exists is skipped -- re-running does not
    touch it, and does not touch the source PDF either."""
    repo = tmp_path / "setting"
    shutil.copytree(REPO_ROOT / "corpus", repo / "corpus")
    shutil.copytree(REPO_ROOT / "tools", repo / "tools")
    library = repo / "library"
    library.mkdir(parents=True)

    already_done = repo / "corpus" / "done.txt"
    already_done.write_text("already extracted, untouched\n", encoding="utf-8")
    # A PDF whose corpus/-mirrored .txt already exists should be left entirely alone.
    stray_pdf = library / "done.pdf"
    make_text_pdf(stray_pdf, ["should never be read"])
    stray_pdf_bytes = stray_pdf.read_bytes()

    before = already_done.read_text(encoding="utf-8")
    result = _run("bash", str(repo / "corpus" / "extract.sh"), cwd=repo)
    assert result.returncode == 0, result.stderr

    assert already_done.read_text(encoding="utf-8") == before
    # extract.sh keys resumability off corpus/<rel>.txt; done.pdf's mirrored .txt already
    # existed, so it must be skipped without touching done.pdf.
    assert stray_pdf.exists()
    assert stray_pdf.read_bytes() == stray_pdf_bytes


def test_extract_mirrors_nested_directories_under_corpus(tmp_path):
    """A PDF nested under library/ gets its extracted text at the same nested path under
    corpus/, and the PDF stays exactly where it was under library/."""
    repo = tmp_path / "setting"
    shutil.copytree(REPO_ROOT / "corpus", repo / "corpus")
    shutil.copytree(REPO_ROOT / "tools", repo / "tools")
    library = repo / "library"
    (library / "sub").mkdir(parents=True)
    pdf = library / "sub" / "book.pdf"
    make_text_pdf(
        pdf,
        ["Nested directory extraction also needs to work correctly here."],
    )

    result = _run("bash", str(repo / "corpus" / "extract.sh"), cwd=repo)
    assert result.returncode == 0, result.stderr

    assert pdf.exists(), "nested source PDF must never be deleted"
    assert any(library.rglob("*.pdf")), "library/ must still contain its source PDFs"

    out = repo / "corpus" / "sub" / "book.txt"
    assert out.exists()
    assert "Nested directory extraction" in out.read_text(encoding="utf-8")


def test_extract_ocr_fallback_recovers_text(tmp_path):
    """When the text-layer probe is forced below the OCR threshold, tesseract still recovers
    the rendered page text and clean.py's noise-stripping still applies to it.
    """
    repo = tmp_path / "setting"
    shutil.copytree(REPO_ROOT / "corpus", repo / "corpus")
    shutil.copytree(REPO_ROOT / "tools", repo / "tools")
    (repo / "library").mkdir(parents=True)
    make_text_pdf(
        repo / "library" / "scan.pdf",
        [
            "This line should be recovered purely via OCR rendering.",
            "A second line of visible page text for the fallback path.",
        ],
    )

    env = {**subprocess.os.environ, "EXTRACT_PROBE_THRESHOLD": "999999999"}
    result = subprocess.run(
        ["bash", str(repo / "corpus" / "extract.sh")],
        cwd=repo, capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr

    out = repo / "corpus" / "scan.txt"
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "recovered purely via OCR" in text
    assert "second line of visible page text" in text
    progress = (repo / "corpus" / "progress.log").read_text(encoding="utf-8")
    assert "OCR" in progress


def test_clean_py_directly(tmp_path):
    src = tmp_path / "raw.txt"
    dst = tmp_path / "clean.txt"
    src.write_text(
        "This is a genuine sentence of readable prose.\n"
        "%%%$$$ ###!!! ***\n"  # art/symbol noise
        "x\n"  # too short
        "Another perfectly readable line of real text here.\n",
        encoding="utf-8",
    )
    result = _run(sys.executable, str(CLEAN), str(src), str(dst), cwd=REPO_ROOT)
    assert result.returncode == 0, result.stderr
    cleaned = dst.read_text(encoding="utf-8")
    assert "genuine sentence of readable prose" in cleaned
    assert "Another perfectly readable line" in cleaned
    assert "%%%" not in cleaned
    assert "\nx\n" not in cleaned


def test_clean_py_module_keep_function():
    sys.path.insert(0, str(REPO_ROOT / "corpus"))
    import importlib

    clean_mod = importlib.import_module("clean")
    assert clean_mod.keep("This is a real sentence with real words.")
    assert not clean_mod.keep("%%%$$$###")
    assert not clean_mod.keep("x")
    assert not clean_mod.keep("")
