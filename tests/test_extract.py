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


def test_extract_replaces_pdf_with_text_in_place(tmp_path):
    """A PDF under library/ becomes a .txt at the same relative path, and the PDF is gone."""
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

    result = _run("bash", str(repo / "corpus" / "extract.sh"), cwd=repo)
    assert result.returncode == 0, result.stderr

    out = repo / "library" / "sourcebook.txt"
    assert out.exists(), result.stdout + result.stderr
    assert not pdf.exists(), "source PDF should be deleted once extraction succeeds"
    text = out.read_text(encoding="utf-8")
    assert "real paragraph of extractable prose" in text
    assert "spans more than one line" in text


def test_extract_is_resumable(tmp_path):
    """A file whose .txt already exists is skipped -- re-running does not touch it."""
    repo = tmp_path / "setting"
    shutil.copytree(REPO_ROOT / "corpus", repo / "corpus")
    shutil.copytree(REPO_ROOT / "tools", repo / "tools")
    library = repo / "library"
    library.mkdir(parents=True)

    already_done = library / "done.txt"
    already_done.write_text("already extracted, untouched\n", encoding="utf-8")
    # A PDF sitting next to an already-produced .txt should be left alone (and not deleted --
    # resumability must not destroy data on a re-run of a file it decides to skip).
    stray_pdf = library / "done.pdf"
    make_text_pdf(stray_pdf, ["should never be read"])

    before = already_done.read_text(encoding="utf-8")
    result = _run("bash", str(repo / "corpus" / "extract.sh"), cwd=repo)
    assert result.returncode == 0, result.stderr

    assert already_done.read_text(encoding="utf-8") == before
    # extract.sh keys resumability off <same-stem>.txt; done.pdf's sibling .txt already
    # existed, so it must be skipped without deleting done.pdf.
    assert stray_pdf.exists()


def test_extract_produces_every_file_under_library_readable_as_utf8(tmp_path):
    """Whatever extract.sh leaves under library/ must satisfy setting_build.py's read step:
    library_dir.rglob("*") -> every file .read_text(encoding="utf-8") must not raise.
    """
    repo = tmp_path / "setting"
    shutil.copytree(REPO_ROOT / "corpus", repo / "corpus")
    shutil.copytree(REPO_ROOT / "tools", repo / "tools")
    library = repo / "library"
    (library / "sub").mkdir(parents=True)
    make_text_pdf(
        library / "sub" / "book.pdf",
        ["Nested directory extraction also needs to work correctly here."],
    )

    result = _run("bash", str(repo / "corpus" / "extract.sh"), cwd=repo)
    assert result.returncode == 0, result.stderr

    for f in library.rglob("*"):
        if f.is_file():
            f.read_text(encoding="utf-8")  # raises UnicodeDecodeError if this ever regresses
    assert not any(library.rglob("*.pdf"))


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

    out = repo / "library" / "scan.txt"
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
