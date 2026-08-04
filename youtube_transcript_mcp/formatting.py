"""Turning caption fragments into something an agent can actually read.

Raw auto-captions arrive as ~7-word fragments that overlap in time and split
mid-sentence. A 2-hour lecture is ~2,955 of them. Handing that to a model wastes
context and reads badly.

So fragments are merged into timed blocks, blocks are grouped under the video's
own chapters, and every block carries a deep link so the agent can cite the
exact moment rather than paraphrasing vaguely.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .metadata import Chapter, VideoInfo, deep_link
from .transcript import Segment, Transcript

CHARS_PER_TOKEN = 4

#: Merge targets. Chosen so a block is a readable paragraph, not a sentence
#: fragment, without spanning so long that its timestamp stops being useful.
BLOCK_SECONDS = 45.0
BLOCK_MAX_WORDS = 140


@dataclass
class Block:
    start: float
    end: float
    text: str
    chapter: Chapter | None = None


def timecode(seconds: float, long_form: bool) -> str:
    seconds = int(seconds)
    h, m, s = seconds // 3600, (seconds % 3600) // 60, seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}" if long_form else f"{m:02d}:{s:02d}"


def _append(existing: str, incoming: str) -> str:
    """Join fragments, dropping the overlap rolling captions sometimes repeat."""
    if not existing:
        return incoming
    old, new = existing.split(), incoming.split()
    for overlap in range(min(6, len(old), len(new)), 0, -1):
        if [w.lower() for w in old[-overlap:]] == [w.lower() for w in new[:overlap]]:
            new = new[overlap:]
            break
    return (existing + " " + " ".join(new)).strip() if new else existing


def _chapter_at(chapters: list[Chapter], when: float) -> Chapter | None:
    current = None
    for chapter in chapters:
        if chapter.start <= when:
            current = chapter
        else:
            break
    return current


def merge_segments(
    segments: list[Segment],
    chapters: list[Chapter] | None = None,
    *,
    block_seconds: float = BLOCK_SECONDS,
    max_words: int = BLOCK_MAX_WORDS,
) -> list[Block]:
    """Collapse fragments into paragraph-sized blocks that respect chapter edges."""
    chapters = chapters or []
    blocks: list[Block] = []
    current: Block | None = None

    for segment in segments:
        chapter = _chapter_at(chapters, segment.start)
        segment_end = segment.start + segment.duration

        too_long = current is not None and segment_end - current.start >= block_seconds
        too_wordy = current is not None and len(current.text.split()) >= max_words
        new_chapter = current is not None and chapter is not current.chapter

        if current is None or too_long or too_wordy or new_chapter:
            current = Block(
                start=segment.start, end=segment_end, text=segment.text, chapter=chapter
            )
            blocks.append(current)
        else:
            current.text = _append(current.text, segment.text)
            current.end = segment_end

    return blocks


_WORD_SPLIT = re.compile(r"[^a-z0-9]+")


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, pad — so ' term ' can be matched literally.

    Auto-captions never hyphenate ("self attention") but chapter titles often do
    ("self-attention"). An agent that reads the chapter list and searches the
    term it saw there must not come back empty, so both sides are flattened to
    the same shape before matching.
    """
    return " " + " ".join(w for w in _WORD_SPLIT.split(text.lower()) if w) + " "


def _search(blocks: list[Block], query: str, context: int) -> tuple[list[Block], str]:
    """Blocks matching `query`, widened by `context`. Phrase first, then any term."""
    terms = [w for w in _WORD_SPLIT.split(query.lower()) if w]
    if not terms:
        return blocks, "none"

    normalized = [_normalize(b.text) for b in blocks]
    phrase = " " + " ".join(terms) + " "

    mode = "phrase"
    hits = [i for i, n in enumerate(normalized) if phrase in n]
    if not hits and len(terms) > 1:
        mode = "any-term"
        hits = [i for i, n in enumerate(normalized) if any(f" {t} " in n for t in terms)]
    if not hits:
        return [], "no-match"

    keep: set[int] = set()
    for i in hits:
        keep.update(range(max(0, i - context), min(len(blocks), i + context + 1)))
    return [blocks[i] for i in sorted(keep)], mode


def _render(blocks: list[Block], style: str, video_id: str, long_form: bool) -> str:
    if style == "plain":
        return "\n\n".join(b.text for b in blocks)

    lines: list[str] = []
    seen_chapter: Chapter | None = None
    for block in blocks:
        if style == "chapters" and block.chapter is not seen_chapter:
            seen_chapter = block.chapter
            if seen_chapter is not None:
                lines.append(
                    f"\n## {seen_chapter.index}. {seen_chapter.title} "
                    f"[{timecode(seen_chapter.start, long_form)}] "
                    f"{deep_link(video_id, seen_chapter.start)}\n"
                )
        lines.append(f"[{timecode(block.start, long_form)}] {block.text}")
    return "\n".join(lines).strip()


def build_response(
    transcript: Transcript,
    info: VideoInfo | None = None,
    *,
    style: str = "chapters",
    query: str | None = None,
    start: float | None = None,
    end: float | None = None,
    context_blocks: int = 1,
    max_chars: int = 40_000,
) -> dict:
    video_id = transcript.video_id
    chapters = info.chapters if info else []
    duration = (info.duration if info else None) or transcript.duration
    long_form = bool(duration and duration >= 3600)

    segments = transcript.segments
    if start is not None or end is not None:
        lo = start if start is not None else float("-inf")
        hi = end if end is not None else float("inf")
        segments = [s for s in segments if lo <= s.start <= hi]

    blocks = merge_segments(segments, chapters)
    blocks_total = len(blocks)

    matched = None
    match_mode = None
    if query:
        blocks, match_mode = _search(blocks, query, context_blocks)
        matched = len(blocks)

    truncated = False
    resume_at = None
    body = _render(blocks, style, video_id, long_form)

    if len(body) > max_chars:
        kept: list[Block] = []
        size = 0
        for block in blocks:
            size += len(block.text) + 2
            if size > max_chars:
                break
            kept.append(block)
        kept = kept or blocks[:1]
        if len(kept) < len(blocks):
            resume_at = round(blocks[len(kept)].start, 2)
        blocks, truncated = kept, True
        body = _render(blocks, style, video_id, long_form)

    response = {
        "video_id": video_id,
        "url": f"https://youtu.be/{video_id}",
        "title": (info.title if info else None) or transcript.title,
        "channel": (info.channel if info else None) or transcript.channel,
        "duration_seconds": duration,
        "duration_hms": timecode(duration, True) if duration else None,
        "language": transcript.language,
        "auto_generated": transcript.is_generated,
        "source_backend": transcript.source,
        "blocks_total": blocks_total,
        "blocks_returned": len(blocks),
        "estimated_tokens": len(body) // CHARS_PER_TOKEN,
        "truncated": truncated,
        "transcript": body,
    }

    if chapters:
        response["chapters"] = [
            {
                "index": c.index,
                "title": c.title,
                "start_seconds": c.start,
                "start": timecode(c.start, long_form),
                "url": deep_link(video_id, c.start),
            }
            for c in chapters
        ]

    if matched is not None:
        response["query"] = query
        response["query_matched_blocks"] = matched
        response["query_match_mode"] = match_mode
        if matched == 0:
            response["transcript"] = ""
            response["note"] = (
                f"Nothing matched {query!r}. Try different wording, or drop `query` "
                "and use `chapter` to read one section at a time."
            )

    if truncated:
        hint = (
            f"Truncated at {max_chars} chars. Continue with start={resume_at}"
            if resume_at is not None
            else f"Truncated at {max_chars} chars."
        )
        if chapters:
            hint += ", or fetch one section at a time with `chapter`"
        response["note"] = hint + "."
        response["resume_at_seconds"] = resume_at

    return response
