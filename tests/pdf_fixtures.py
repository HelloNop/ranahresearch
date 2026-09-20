"""Deterministic PDF fixtures.

Builds small but structurally valid PDFs with real, extractable text, so parser
tests assert against actual extraction rather than a mocked parser. Text is
encoded as Latin-1 because the fixtures use the standard Helvetica font; a
non-Latin script would need an embedded CID font, which these fixtures do not
cover.
"""


def _escape(text: str) -> bytes:
    escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    return escaped.encode("latin-1", errors="replace")


def _content_stream(lines: list[str]) -> bytes:
    body = [b"BT", b"/F1 12 Tf", b"72 720 Td", b"16 TL"]
    for index, line in enumerate(lines):
        if index:
            body.append(b"T*")
        body.append(b"(" + _escape(line) + b") Tj")
    body.append(b"ET")
    return b"\n".join(body)


def build_pdf(pages: list[list[str]]) -> bytes:
    """One PDF where page N contains exactly the given lines."""
    objects: list[bytes] = []
    page_count = len(pages)
    page_ids = [3 + index * 2 for index in range(page_count)]

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = b" ".join(f"{pid} 0 R".encode() for pid in page_ids)
    objects.append(
        b"<< /Type /Pages /Kids [" + kids + b"] /Count " + str(page_count).encode() + b" >>"
    )
    for index, lines in enumerate(pages):
        content_id = page_ids[index] + 1
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents "
            + str(content_id).encode()
            + b" 0 R /Resources << /Font << /F1 "
            + str(2 + page_count * 2 + 1).encode()
            + b" 0 R >> >> >>"
        )
        stream = _content_stream(lines)
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
    # WinAnsiEncoding so Latin-1 bytes render as the characters they encode;
    # the default StandardEncoding maps the accented range to other glyphs.
    objects.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, payload in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(number).encode() + b" 0 obj\n" + payload + b"\nendobj\n"

    xref_offset = len(out)
    out += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n"
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        b"trailer\n<< /Size "
        + str(len(objects) + 1).encode()
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(xref_offset).encode()
        + b"\n%%EOF\n"
    )
    return bytes(out)


ACADEMIC_PAPER = [
    [
        "Generative AI and university learning outcomes",
        "Abstract",
        "We report a randomised trial of a generative AI tutor in higher education.",
        "Introduction",
        "Generative AI tools are increasingly used by university students.",
    ],
    [
        "Methods",
        "Participants",
        "We recruited 214 undergraduate students at two universities in Indonesia",
        "between March 2023 and November 2023. Participants were randomised to an",
        "intervention arm (107 students) or a control arm (107 students).",
        "Outcomes",
        "The primary outcome was final course score, measured at 12 weeks.",
    ],
    [
        "Results",
        "Mean final score was 78.4 (SD 6.1) in the intervention arm and 74.2 (SD 6.8)",
        "in the control arm. The difference was 4.2 points (95% CI 2.1 to 6.3).",
        "Discussion",
        "The effect was consistent across both sites.",
        "References",
        "1. Example A. A prior study. Journal of Learning. 2022.",
    ],
]
