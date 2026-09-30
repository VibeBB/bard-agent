"""Validate a bard_song_proposal JSON and render it to ABC, MIDI, MML, Markdown
and a provenance record. Implements docs/song-proposal-contract.md (schema 0.2).

Python 3.12+, standard library only.

Conventions chosen where the contract leaves detail open:

- Melodic leaps (rule: adjacent notes within 12 semitones) are measured between
  consecutive *sounded* notes; rests do not participate.
- A ``~`` unit note must equal the previous sounded note or move by at most a
  whole step (2 semitones) per the line rule "same or adjacent (stepwise)".
- ``en`` units contain no punctuation: the unit join is compared to the text
  with whitespace and ``,.;:!?'"()-—`` removed and casefolded, so units must
  already be punctuation-free (e.g. ``"lines"`` for the word ``line's``).
- A ``ja`` line may carry a ``reading`` field (kana only); when present the
  unit join is checked against ``reading`` instead of ``text``, freeing
  ``text`` to use kanji. ``reading`` is rejected on ``en`` lines.
- Rhythm rule: any sung line of 4+ notes must use at least two distinct
  ``beats`` values.
- A section ``name`` starting with a known kind word (``intro``/``verse``/
  ``chorus``/``refrain``/``bridge``/``outro``) must carry the matching ``kind``
  (``refrain`` maps to ``chorus``).
- ``rationale`` lyric quotes introduced by ``refrain``/``chorus``/``verse``/
  ``サビ``/``リフレイン`` and ``「」``/``"`` must appear verbatim (after
  whitespace normalization) in some line ``text`` or the ``title``, catching
  quotes left stale by post-critic rewrites.
- ``w:`` lyric lines: for ``en``, text words are reconstructed by consuming
  non-special units against each whitespace-split word's normalized form;
  inside a word, a piece is separated from the previous one by ``-`` only
  when the previous piece is a syllable, so mid-word melismas render as
  ``hea-_ven`` and a word-start ``~`` is a standalone ``_`` token. ``ja``
  text has no word boundaries, so every sung unit is joined by ``-`` into
  one run, with ``~`` breaking the run as a space-separated ``_`` token.
  Rest units emit no lyric token in either language: ABC aligns ``w:``
  words to sounded notes only and skips rests automatically.
- Each lyric ``Line`` renders as its own ABC music line followed by its single
  ``w:`` line, keeping lyric verse alignment 1:1; a line that ends mid-bar
  omits the ``|`` and the next line continues the bar. The section's last
  music line always closes with ``|``.
- ``intro``/``outro`` sections may declare ``lines: []``: the section is then
  an instrumental of bars x beats-per-bar. The melody is silent (ABC emits
  one ``z`` whole-bar rest per chord segment, MML emits ``r`` rests, the MIDI
  melody track plays nothing) while the accompaniment voices keep playing.
- Split-bar chords ("Am Dm") annotate the bar start and are re-annotated before
  the first melody event starting at or after the bar midpoint; if no event
  starts there, the annotation goes just before the bar line.
- MML accidentals prefer sharps, except that flat-spelled tonics (Db Eb Gb Ab
  Bb and F) prefer flats.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from song_model import (  # noqa: E402
    CHORD_QUALITIES,
    CHORD_RE,
    EN_TEXT_STRIP,
    JA_READING_RE,
    JA_TEXT_STRIP,
    LETTER_PC,
    PITCH_RE,
    TONIC_PC,
    TONICS,
    Chord,
    Line,
    Note,
    ProposalError,
    Section,
    Song,
    _parse_chord_symbol,
    parse_pitch,
)
from song_readback import (  # noqa: E402
    ABC_TOKEN_RE,
    MML_TOKEN_RE,
    _midi_note_spans,
    _readback_check,
    lint_song,
    parse_abc_melody,
    parse_midi_counts,
    parse_mml,
    score_lint_report,
)
from song_render import (  # noqa: E402
    ABC_PC_FLAT,
    ABC_PC_SHARP,
    FLAT_TONICS,
    MML_LEN,
    MML_PC_FLAT,
    MML_PC_SHARP,
    PPQ,
    PROVENANCE_KIND,
    _accompaniment_slots,
    _midi_track,
    _vlq,
    _w_line,
    render_abc,
    render_markdown,
    render_midi,
    render_mml,
    render_provenance,
)
from song_validate import (  # noqa: E402
    ALLOWED_BEATS,
    KEY_MODES,
    LANGUAGES,
    MAX_EVENTS,
    METERS,
    MODES,
    PROPOSAL_KIND,
    RATIONALE_QUOTE_RE,
    SCALE_INTERVALS,
    SCHEMA_VERSION,
    SCHEMA_VERSIONS_ACCEPTED,
    SECTION_KINDS,
    SECTION_NAME_KIND,
    SECTION_NAME_RE,
    SEVENTH_QUALITIES,
    SHA256_RE,
    SOURCE_KINDS,
    WS_RUN_RE,
    validate_proposal,
)

__all__ = [
    "Chord",
    "CHORD_QUALITIES",
    "CHORD_RE",
    "EN_TEXT_STRIP",
    "JA_READING_RE",
    "JA_TEXT_STRIP",
    "LETTER_PC",
    "Line",
    "Note",
    "PITCH_RE",
    "ProposalError",
    "Section",
    "Song",
    "TONIC_PC",
    "TONICS",
    "_parse_chord_symbol",
    "parse_pitch",
    "ALLOWED_BEATS",
    "KEY_MODES",
    "LANGUAGES",
    "MAX_EVENTS",
    "METERS",
    "MODES",
    "PROPOSAL_KIND",
    "RATIONALE_QUOTE_RE",
    "SCHEMA_VERSION",
    "SCHEMA_VERSIONS_ACCEPTED",
    "SCALE_INTERVALS",
    "SECTION_KINDS",
    "SECTION_NAME_KIND",
    "SECTION_NAME_RE",
    "SEVENTH_QUALITIES",
    "SOURCE_KINDS",
    "SHA256_RE",
    "WS_RUN_RE",
    "validate_proposal",
    "ABC_PC_FLAT",
    "ABC_PC_SHARP",
    "FLAT_TONICS",
    "MML_LEN",
    "MML_PC_FLAT",
    "MML_PC_SHARP",
    "PPQ",
    "PROVENANCE_KIND",
    "_accompaniment_slots",
    "_midi_track",
    "_vlq",
    "_w_line",
    "render_abc",
    "render_markdown",
    "render_midi",
    "render_mml",
    "render_provenance",
    "ABC_TOKEN_RE",
    "MML_TOKEN_RE",
    "_midi_note_spans",
    "_readback_check",
    "lint_song",
    "parse_abc_melody",
    "parse_midi_counts",
    "parse_mml",
    "score_lint_report",
    "render",
    "main",
]


def render(song: Song) -> dict[str, bytes]:
    abc = render_abc(song)
    midi = render_midi(song)
    mml = render_mml(song)
    md = render_markdown(song, abc)
    return {
        "song.abc": abc.encode("utf-8"),
        "song.mid": midi,
        "song.mml": mml.encode("utf-8"),
        "song.md": md.encode("utf-8"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate and render in memory, write nothing",
    )
    parser.add_argument(
        "--json", action="store_true", help="print the result as one JSON object"
    )
    args = parser.parse_args(argv)

    proposal_path: Path = args.proposal
    out_dir: Path = args.out_dir

    try:
        raw_text = proposal_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except (OSError, json.JSONDecodeError) as e:
        reasons = [f"proposal: cannot read or parse JSON: {e}"]
        if args.json:
            print(json.dumps({"status": "error", "reasons": reasons}))
        else:
            for r in reasons:
                print(r)
        return 3 if isinstance(e, OSError) else 2

    proposal_sha = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    try:
        song = validate_proposal(data)
        outputs = render(song)
        readback_reasons = _readback_check(song, outputs)
        if readback_reasons:
            raise ProposalError(readback_reasons)
        script_hasher = hashlib.sha256()
        for source_name in (
            "render_song.py",
            "song_model.py",
            "song_validate.py",
            "song_render.py",
            "song_readback.py",
        ):
            script_hasher.update(
                (Path(__file__).resolve().parent / source_name).read_bytes()
            )
        script_sha = script_hasher.hexdigest()
        prov = render_provenance(song, proposal_path, proposal_sha, outputs, script_sha)
        outputs["song.provenance.json"] = prov.encode("utf-8")
    except ProposalError as e:
        if args.json:
            print(
                json.dumps(
                    {"status": "rejected", "reasons": e.reasons}, ensure_ascii=False
                )
            )
        else:
            for r in e.reasons:
                print(r)
        return 2
    except OSError as e:
        reasons = [f"io: {e}"]
        if args.json:
            print(json.dumps({"status": "error", "reasons": reasons}))
        else:
            print(reasons[0])
        return 3

    if args.check:
        result = {"status": "ok", "check": True, "proposal_sha256": proposal_sha}
        print(json.dumps(result) if args.json else "check ok")
        return 0

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        written: dict[str, str] = {}
        for name, blob in outputs.items():
            path = out_dir / name
            path.write_bytes(blob)
            written[name] = hashlib.sha256(blob).hexdigest()
    except OSError as e:
        print(
            json.dumps({"status": "error", "reasons": [f"io: {e}"]})
            if args.json
            else f"io: {e}"
        )
        return 3

    if args.json:
        print(json.dumps({"status": "ok", "files": written}, ensure_ascii=False))
    else:
        for name, sha in written.items():
            print(f"{out_dir / name}: {sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
