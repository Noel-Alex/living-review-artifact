"""Rebuild ReviewAnchorBench target files from the released case descriptors (WP K7).

The benchmark's transformation builder (build_review_anchor_benchmark.py) is not in the
released packages 1.0.0 or 1.1.0. Each case descriptor records its family, parameters and the
SHA-256 of the target content, so a target is rebuilt here from the source blob and accepted
only when its hash equals the released target_content_sha256. Cases that cannot be rebuilt
to the released hash are reported, never guessed.

Library use: rebuild(case, source_lines) -> (target_lines | None, rule).
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path


def decode(data: bytes) -> list[str]:
    """The package's decode_source_bytes: strict UTF-8 (BOM allowed), CRLF/CR -> LF, split on LF."""
    text = data.decode("utf-8-sig", errors="strict")
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def normalize_line(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(text))).strip()


def content_sha256(lines: list[str]) -> str:
    return hashlib.sha256(("\n".join(lines)).encode("utf-8")).hexdigest()


def _remove(lines, s, e):
    return lines[:s - 1] + lines[e:]


def candidates(case: dict, src: list[str]):
    """Yield (rule, target_lines) for the case's family; the hash check selects among them."""
    fam, p = case["family"], case["parameters"]
    s, e = case["source_range"]
    block = src[s - 1:e]
    rep = case["raw_replacement_lines"]
    if fam == "IDENTITY":
        yield "identity", list(src)
    elif fam == "PREFIX_INSERT":
        yield "blank-prefix", [""] * p["insert_n"] + src
    elif fam == "BLOCK_MOVE":
        rest = _remove(src, s, e)
        d = p["destination_before_insert"]
        yield "move", rest[:d] + block + rest[d:]
    elif fam == "MOVE_AND_REPLACE":
        rest = _remove(src, s, e)
        d = p["destination_before_insert"]
        yield "move-replace", rest[:d] + rep + rest[d:]
    elif fam == "REPLACEMENT_APPLIED":
        yield "replace", src[:s - 1] + rep + src[e:]
    elif fam == "TARGET_DELETE":
        yield "delete", _remove(src, s, e)
    elif fam == "DUPLICATE_PREIMAGE":
        d = p["duplicate_insert_before_line"]
        yield "duplicate", src[:d - 1] + block + src[d - 1:]
    elif fam == "SURROUNDING_CONTEXT_EDIT":
        i = p["edited_line"] - 1
        old = src[i]
        for rule, new in CONTEXT_EDITS(old):
            yield rule, src[:i] + [new] + src[i + 1:]
    elif fam == "INTERNAL_LINE_EDIT":
        i = s - 1 + p["edited_offset"]
        old = src[i]
        for rule, new in INTERNAL_EDITS(old):
            yield rule, src[:i] + [new] + src[i + 1:]
    elif fam == "WHITESPACE_INSIDE":
        for rule, new_block in WHITESPACE_EDITS(block):
            yield rule, src[:s - 1] + new_block + src[e:]


def _variants(old: str, tag: str):
    ind = old[:len(old) - len(old.lstrip())]
    body = old.strip()
    yield f"{tag}-append-space", f"{old} {tag}"
    yield f"{tag}-append-nospace", f"{old}{tag}"
    yield f"{tag}-replace", tag
    yield f"{tag}-indent-replace", f"{ind}{tag}"
    yield f"{tag}-prepend", f"{tag} {old}"
    yield f"{tag}-indent-prepend", f"{ind}{tag} {body}"
    yield f"{tag}-rstrip-append", f"{old.rstrip()} {tag}"


def CONTEXT_EDITS(old: str):
    for tag in ("REVIEW_ANCHOR_CONTEXT_EDIT", "CONTEXT_EDIT", "SURROUNDING_CONTEXT_EDIT", "REVIEW_ANCHOR_CONTEXT"):
        yield from _variants(old, tag)


def INTERNAL_EDITS(old: str):
    for tag in ("REVIEW_ANCHOR_INTERNAL_EDIT", "INTERNAL_EDIT", "INTERNAL_LINE_EDIT"):
        yield from _variants(old, tag)


def WHITESPACE_EDITS(block: list[str]):
    yield "ws-double-spaces", [re.sub(r" ", "  ", x) for x in block]
    yield "ws-first-space-double", [x.replace(" ", "  ", 1) for x in block]
    yield "ws-trailing-space", [x + " " for x in block]
    yield "ws-leading-space", [" " + x for x in block]
    yield "ws-trailing-tab", [x + "\t" for x in block]
    yield "ws-leading-tab", ["\t" + x for x in block]
    yield "ws-spaces-to-tabs", [x.replace(" ", "\t") for x in block]
    yield "ws-collapse", [re.sub(r"\s+", " ", x).strip() for x in block]
    yield "ws-strip", [x.strip() for x in block]
    yield "ws-first-line-trailing", [block[0] + " "] + block[1:]
    yield "ws-first-line-leading", [" " + block[0]] + block[1:]
    yield "ws-first-line-double", [block[0].replace(" ", "  ", 1)] + block[1:]


def rebuild(case: dict, src: list[str]):
    want = case["target_content_sha256"]
    for rule, tgt in candidates(case, src):
        if content_sha256(tgt) == want and len(tgt) == case["target_line_n"]:
            return tgt, rule
    return None, None


if __name__ == "__main__":
    import sys
    from collections import Counter
    cases = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["cases"]
    blobs = Path(sys.argv[2])
    got, miss, absent = Counter(), Counter(), Counter()
    for c in cases:
        b = blobs / f"{c['source_blob_sha256']}.bin"
        if not b.exists():
            absent[c["family"]] += 1
            continue
        src = decode(b.read_bytes())
        tgt, rule = rebuild(c, src)
        (got if tgt is not None else miss)[(c["family"], rule)] += 1
    print("rebuilt", sorted(got.items()))
    print("unmatched", sorted(miss.items()))
    print("blob absent", sorted(absent.items()))
