"""Multilingual golden-utterance end-to-end coverage for
ovos-skill-color-picker.

test_golden_utterances.py only exercises en-US; every other locale under
locale/ ships all four .intent files (request_color, request_color_by_name,
request_color_by_hex, request_color_by_rgb). This suite covers every such
locale (kab is not one of them: it only ships request_color_by_name).

The corpus keys this skill as "ovos-skill-color-picker.openvoiceos", but
the real runtime opm.skill id is "ovos-skill-color-picker.krisgesling" (see
test_golden_utterances.py); this suite asserts against the runtime id.

One MiniCroft is booted PER LOCALE (module-scoped fixture, indirectly
parametrized by lang; pytest reuses one boot per distinct lang value
across every row of that lang and tears it down before moving on).

Row construction: each row is derived mechanically from that locale's own
.intent template lines, with slots filled by a native color word taken
from that locale's own color.entity (never a translation of the English
rows), a hex string, or an RGB triple.
"""
import json
from pathlib import Path
from typing import List

import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft

SKILL_ID = "ovos-skill-color-picker.krisgesling"
PIPELINE = ["ovos-padacioso-pipeline-plugin"]

END2END_DIR = Path(__file__).parent

LANGS = [
    "en-US", "ca-ES", "da-DK", "de-DE", "es-ES", "eu-ES", "fr-FR",
    "gl-ES", "it-IT", "nl-NL", "pt-BR", "pt-PT", "sv-SE",
]


def _candidates(skill_id: str, intent_label: str) -> set:
    base = intent_label.removesuffix(".intent")
    return {f"{skill_id}:{intent_label}", f"{skill_id}:{base}"}


def _load_rows(lang):
    path = END2END_DIR / f"golden_utterances_{lang}.jsonl"
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("needs_manual"):
                continue
            rows.append(row)
    return rows


ALL_ROWS = []
for _lang in LANGS:
    for _row in _load_rows(_lang):
        ALL_ROWS.append(_row)


def _golden_id(row):
    return f"{row['lang']}-{row['intent_label']}-{row['utterance']}"


@pytest.fixture(scope="module")
def minicroft(request):
    lang = request.param
    # keep padatious (heavy fann/numpy training, uncancellable background
    # thread) out of the boot entirely -- this suite only queries via
    # padacioso, matching test_golden_utterances.py's own pipeline choice.
    mc = get_minicroft(
        [SKILL_ID], max_wait=150, lang=lang,
        default_pipeline=["ovos-padacioso-pipeline-plugin"],
    )
    yield mc
    mc.stop()


def _types(mc, text, lang, session_id) -> List[str]:
    session = Session(session_id)
    session.lang = lang
    session.pipeline = list(PIPELINE)
    utterance = Message(
        "recognizer_loop:utterance",
        {"utterances": [text], "lang": lang},
        {"session": session.serialize(), "source": "A", "destination": "B"},
    )
    capture = CaptureSession(
        mc,
        eof_msgs=["ovos.utterance.handled"],
        ignore_messages=["speak", "ovos.utterance.speak",
                          "recognizer_loop:audio_output_start",
                          "recognizer_loop:audio_output_end",
                          "mycroft.audio.play_sound"],
    )
    capture.capture(utterance, timeout=30)
    return [m.msg_type for m in capture.finish()]


KNOWN_BUGS = {}

_PARAMS = [
    pytest.param(row["lang"], row, id=_golden_id(row))
    for row in ALL_ROWS
]


@pytest.mark.timeout(300)
@pytest.mark.parametrize("minicroft,row", _PARAMS, indirect=["minicroft"])
def test_golden_utterance_multilang(minicroft, row):
    candidates = _candidates(SKILL_ID, row["intent_label"])
    types = _types(minicroft, row["utterance"], row["lang"], f"golden-{_golden_id(row)}")
    matched = any(t in candidates for t in types)
    bug_key = (row["lang"], row["utterance"])
    if bug_key in KNOWN_BUGS and not matched:
        pytest.xfail(reason=f"known-bug: {KNOWN_BUGS[bug_key]}")
    assert matched, (
        f"[{row['lang']}] {row['utterance']!r}: expected one of {sorted(candidates)!r}, got {types!r}"
    )
