"""Build a minimal single-page text PDF for tests, with no external dependencies.

Hand-rolled PDF syntax (base-14 Helvetica, one Tj per line) -- just enough for pdftotext to
recover the text layer. Test fixture only; never used against real setting content.
"""

import pathlib

_HEADER = b"%PDF-1.4\n"


def _obj(n: int, body: bytes) -> bytes:
    return f"{n} 0 obj\n".encode() + body + b"\nendobj\n"


def make_text_pdf(path: pathlib.Path, lines: list[str]) -> None:
    """Write a one-page PDF to `path` whose text layer is `lines`."""
    content_ops = ["BT", "/F1 14 Tf", "14 TL", "72 760 Td"]
    for i, line in enumerate(lines):
        escaped = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        if i > 0:
            content_ops.append("T*")
        content_ops.append(f"({escaped}) Tj")
    content_ops.append("ET")
    stream = "\n".join(content_ops).encode()

    objects = {}
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"
    objects[3] = (
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 612 792] /Contents 5 0 R >>"
    )
    objects[4] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    objects[5] = (
        f"<< /Length {len(stream)} >>\nstream\n".encode()
        + stream
        + b"\nendstream"
    )

    out = bytearray()
    out += _HEADER
    offsets = {}
    for n in sorted(objects):
        offsets[n] = len(out)
        out += _obj(n, objects[n])

    xref_offset = len(out)
    n_objs = len(objects) + 1
    out += f"xref\n0 {n_objs}\n".encode()
    out += b"0000000000 65535 f \n"
    for n in sorted(objects):
        out += f"{offsets[n]:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {n_objs} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF"
    ).encode()

    path.write_bytes(bytes(out))
