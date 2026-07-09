"""
attachments.py
--------------
Turns files uploaded via /upload into content the agent can actually reason
over. The /upload endpoint only SAVES the file; this module reads it back and
converts it to a provider-agnostic bundle:

  - Excel / CSV  -> a compact text preview (shape, columns, sample rows,
                    numeric summary) so the model can analyse/summarise it
  - PDF          -> extracted text (capped); flagged if it's a scanned image PDF
  - Images       -> base64 blocks for a vision-capable model (Scout / Gemini /
                    Claude all support vision)

process_attachments(attachments) -> {
    "text":   "<combined text context for all doc/sheet files>",
    "images": [ {"media_type": "image/png", "data": "<base64>"}, ... ],
    "notes":  [ "<per-file problems>", ... ],
}

Each backend renders `text` into the prompt and `images` into its own
multimodal message format (see groq/gemini/anthropic _backend.py).
"""

import base64
import glob
import io
import os
import re

UPLOAD_DIR = os.path.join("outputs", "uploads")

# A valid file_id is exactly what /upload mints: uuid4().hex = 32 hex chars.
# Anything else (a glob like "*", a prefix, or a path-traversal attempt) is
# rejected BEFORE it reaches glob(), so one user can't read another user's
# uploads by passing "*" or a partial id in the /chat attachments field.
_FILE_ID_RE = re.compile(r"^[0-9a-fA-F]{32}$")

# Keep token cost sane on the free tier.
MAX_ROWS = 50           # sample rows per sheet shown to the model
MAX_COLS = 40           # columns listed before we truncate
MAX_PDF_CHARS = 12_000  # ~3k tokens of PDF text
MAX_IMAGE_DIM = 1536    # downscale bigger images before base64
READ_CAP = 5_000        # max rows READ into memory per sheet (DoS guard)
# Reject a spreadsheet whose DECOMPRESSED contents exceed this: a small (<15MB)
# xlsx is a zip and can decompress to gigabytes ("zip bomb"), OOM-ing the worker
# if pandas reads it whole.
MAX_DECOMPRESSED = 60 * 1024 * 1024  # 60 MB

_IMAGE_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _resolve(file_id: str) -> str | None:
    """Find the saved upload for a file_id (stored as <file_id><ext>)."""
    # SECURITY: only accept the exact 32-hex-char id shape /upload mints. This
    # blocks glob wildcards ("*"), prefixes, and path traversal - so a user
    # can't read another user's uploads via the /chat attachments field.
    if not file_id or not _FILE_ID_RE.match(file_id):
        return None
    matches = glob.glob(os.path.join(UPLOAD_DIR, f"{glob.escape(file_id)}.*"))
    if not matches:
        bare = os.path.join(UPLOAD_DIR, file_id)  # uploaded with no extension
        if os.path.exists(bare):
            return bare
        return None
    return matches[0]


def _too_big_decompressed(path: str) -> bool:
    """True if this xlsx (a zip) decompresses beyond MAX_DECOMPRESSED - a zip-bomb
    guard so a small file can't OOM the worker when pandas reads it whole."""
    import zipfile
    try:
        with zipfile.ZipFile(path) as z:
            return sum(i.file_size for i in z.infolist()) > MAX_DECOMPRESSED
    except (zipfile.BadZipFile, OSError):
        return False  # not a zip (e.g. legacy .xls) - let the reader handle it


def _tabular_text(path: str, filename: str, kind: str) -> str:
    """Excel/CSV -> a readable preview + numeric summary. Reads at most READ_CAP
    rows per sheet into memory (the model only needs a preview, and an unbounded
    read is a DoS vector)."""
    import pandas as pd

    if kind == "csv":
        try:
            sheets = {"data": pd.read_csv(path, nrows=READ_CAP)}
        except UnicodeDecodeError:
            sheets = {"data": pd.read_csv(path, encoding="latin-1", nrows=READ_CAP)}
    else:
        if _too_big_decompressed(path):
            return (
                f"FILE: {filename} — spreadsheet is too large to analyse safely "
                "(its decompressed contents exceed the size limit). Please send a "
                "smaller extract."
            )
        sheets = pd.read_excel(path, sheet_name=None, nrows=READ_CAP)  # dict

    parts = [f"FILE: {filename}"]
    for name, df in sheets.items():
        parts.append(
            f"\n--- Sheet '{name}': {df.shape[0]} rows x {df.shape[1]} columns ---"
        )
        cols = [str(c) for c in df.columns]
        if len(cols) > MAX_COLS:
            parts.append(
                "Columns: " + ", ".join(cols[:MAX_COLS]) + f", ... (+{len(cols) - MAX_COLS} more)"
            )
        else:
            parts.append("Columns: " + ", ".join(cols))

        head = df.head(MAX_ROWS)
        parts.append("Sample rows:")
        parts.append(head.to_string(index=False, max_cols=MAX_COLS))
        if df.shape[0] > MAX_ROWS:
            parts.append(f"...(+{df.shape[0] - MAX_ROWS} more rows not shown)")

        num = df.select_dtypes("number")
        if not num.empty:
            parts.append("Numeric summary:")
            parts.append(num.describe().to_string(max_cols=MAX_COLS))
    return "\n".join(parts)


def _pdf_text(path: str, filename: str) -> str:
    """PDF -> extracted text (capped). Flags scanned/image-only PDFs."""
    from pypdf import PdfReader

    reader = PdfReader(path)
    chunks, total = [], 0
    for i, page in enumerate(reader.pages):
        t = (page.extract_text() or "").strip()
        if t:
            chunks.append(f"[Page {i + 1}]\n{t}")
            total += len(t)
        if total > MAX_PDF_CHARS:
            chunks.append("...(remaining pages truncated)")
            break
    text = "\n\n".join(chunks).strip()
    if not text:
        return (
            f"FILE: {filename} (PDF, {len(reader.pages)} pages) — no extractable "
            "text. This looks like a scanned/image-only PDF; ask the user to send "
            "it as an image instead so it can be read visually."
        )
    return f"FILE: {filename} (PDF, {len(reader.pages)} pages)\n{text}"


def _image_block(path: str, media_type: str) -> dict:
    """Read an image, downscale if large, return {media_type, base64 data}."""
    try:
        from PIL import Image

        img = Image.open(path)
        if max(img.size) > MAX_IMAGE_DIM:
            img.thumbnail((MAX_IMAGE_DIM, MAX_IMAGE_DIM))
            buf = io.BytesIO()
            fmt = "PNG" if media_type == "image/png" else "JPEG"
            if fmt == "JPEG" and img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(buf, format=fmt)
            data = buf.getvalue()
            media_type = "image/png" if fmt == "PNG" else "image/jpeg"
        else:
            with open(path, "rb") as fh:
                data = fh.read()
    except Exception:
        with open(path, "rb") as fh:
            data = fh.read()
    return {"media_type": media_type, "data": base64.b64encode(data).decode("ascii")}


def process_attachments(attachments: list[dict] | None) -> dict:
    """Convert uploaded files into a {text, images, notes} bundle for the agent."""
    text_parts: list[str] = []
    images: list[dict] = []
    notes: list[str] = []
    has_doc = False  # did any DOCUMENT (sheet/pdf/text) contribute real content?

    for att in attachments or []:
        file_id = att.get("file_id") or att.get("fileId")
        name = att.get("filename") or att.get("name") or file_id or "file"
        path = _resolve(file_id)
        if not path:
            notes.append(f"{name}: upload not found on server")
            continue

        ext = os.path.splitext(path)[1].lower()
        try:
            if ext in (".xlsx", ".xls"):
                text_parts.append(_tabular_text(path, name, "excel"))
                has_doc = True
            elif ext == ".csv":
                text_parts.append(_tabular_text(path, name, "csv"))
                has_doc = True
            elif ext == ".pdf":
                text_parts.append(_pdf_text(path, name))
                has_doc = True
            elif ext in _IMAGE_EXT:
                images.append(_image_block(path, _IMAGE_EXT[ext]))
                text_parts.append(f"FILE: {name} (image — see attached image below)")
            else:
                # Best effort: treat unknown types as UTF-8 text.
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    body = fh.read(MAX_PDF_CHARS)
                text_parts.append(f"FILE: {name}\n{body}")
                has_doc = True
        except Exception as exc:
            notes.append(f"{name}: could not read ({type(exc).__name__}: {exc})")

    return {
        "text": "\n\n".join(text_parts).strip(),
        "images": images,
        "notes": notes,
        "has_doc": has_doc,
    }


def has_content(bundle: dict | None) -> bool:
    """True if the bundle carries anything the model can actually analyse
    (document text OR an image). Used to decide whether to build a multimodal
    message at all."""
    return bool(bundle and (bundle.get("text") or bundle.get("images")))


def grounds_data(bundle: dict | None) -> bool:
    """True only if the attachment supplies DOCUMENT text/data that can legitimately
    ground a numeric answer (sheet/CSV/PDF/text). An IMAGE-only upload does NOT:
    a random attached image must not exempt a fabricated data table from the anti-
    fabrication guard. (Image VISION prose is unaffected - prose triggers no guard;
    only a data table/visual with no run_sql behind it is caught.)"""
    return bool(bundle and bundle.get("has_doc"))


def build_preamble(bundle: dict) -> str:
    """The text block prepended to the user's question when files are attached."""
    header = (
        "The user attached the following file(s). Analyse this content to answer "
        "their question. This is REAL user-provided data — treat it as grounded "
        "(you do NOT need the database for it unless the question also asks for "
        "database info). Do not claim you lack data when it is provided here.\n\n"
    )
    body = bundle.get("text") or "(the attached file(s) are images shown below)"
    notes = bundle.get("notes") or []
    note_txt = ("\n\nNOTE: " + "; ".join(notes)) if notes else ""
    return f"{header}{body}{note_txt}\n\n--- END OF ATTACHED FILES ---\n"
