"""Tiny helpers for Ursina / Panda3D text rendering.

Panda3D's default font ships glyphs for ASCII only. The brainrot
portrait emoji (🐊 🦢 🪵), the unicode arrow used in reliability
log lines (→), the calendar emoji on historical milestones
(📅), and other non-Latin codepoints all trip a per-frame
"No definition for character U+xxxxx" warning when fed straight
into a Text. The pygame overlay handles them fine, so the 2D
log + portrait wall + roster panel keep their emoji — but for
anything rendered through Ursina's Text widget we route the
string through panda_safe() first.

Maps a small set of well-known glyphs to ASCII equivalents and
strips everything else outside the Latin-1 supplement so the
log still parses without the warning flood."""
from __future__ import annotations

# Explicit translations. Map characters we use deliberately to
# something legible in ASCII; anything else outside Latin-1 falls
# through to a generic '?' below.
_TRANSLATIONS: dict[str, str] = {
    "→": "->",      # → right arrow (reliability deltas)
    "←": "<-",      # ← left arrow (rare, but defensive)
    "…": "...",     # … horizontal ellipsis
    "—": "--",      # — em dash
    "–": "-",       # – en dash
    "‘": "'",       # ‘ left single quote
    "’": "'",       # ’ right single quote (apostrophe)
    "“": '"',       # “ left double quote
    "”": '"',       # ” right double quote
    "\U0001f4c5": "[date]",       # 📅 calendar (historical milestones)
    "\U0001f4fb": "[radio]",      # 📻 radio (chatter prefix)
    "\U0001f4a5": "*BOOM*",       # 💥 explosion (full-up loss)
}


def panda_safe(text: str) -> str:
    """Return `text` with non-Latin-1 glyphs swapped for ASCII
    fallbacks Panda3D's default font can render. Pure function;
    safe to call from per-frame sync paths."""
    if not text:
        return text
    out: list[str] = []
    for ch in text:
        if ch in _TRANSLATIONS:
            out.append(_TRANSLATIONS[ch])
        elif ord(ch) < 0x100:
            out.append(ch)
        else:
            # Unknown extended codepoint — drop it entirely rather
            # than leak a font warning. The 2D / overlay paths
            # show the original.
            out.append("?")
    return "".join(out)


def panda_glyph(glyph: str, name: str) -> str:
    """Pick a glyph that Panda3D's default font can actually render
    for this character. ASCII glyphs pass through unchanged; emoji
    portraits fall back to the first letter of the character's
    name (uppercased), then to '?' for unnamed fallbacks. The 2D
    portrait wall + overlay roster panel keep the original emoji."""
    if glyph and glyph.isascii() and glyph.strip():
        return glyph
    cleaned = (name or "").strip()
    if cleaned:
        return cleaned[0].upper()
    return "?"
