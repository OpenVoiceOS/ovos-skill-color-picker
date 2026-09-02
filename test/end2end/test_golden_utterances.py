"""Golden-utterance end-to-end coverage for ovos-skill-color-picker (en-US).

The golden corpus (``golden_utterances.jsonl``) is a vendored slice of the
shared ovoscope golden-utterance dataset. The corpus keys this skill as
``ovos-skill-color-picker.openvoiceos``, but the repo's actual registered
``opm.skill`` entry point (and its pre-existing ``test/end2end/
test_intents_en_us.py``) is ``ovos-skill-color-picker.krisgesling`` -- report
this mismatch for the master corpus. This suite loads the skill and asserts
against the real runtime skill_id.

One shared ``MiniCroft`` (module-scoped fixture) is booted for the whole
suite; every row is its own parametrized test item. ``ovos-padatious`` is a
heavy native/swig dependency (see the ``system_deps: 'swig libfann-dev'`` CI
config) that isn't buildable in every dev sandbox, so this suite (like the
rest of this repo's end2end tests) drives the padacioso-only pipeline,
which registers the same intents.
"""
import json
from pathlib import Path

import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft

CORPUS_SKILL_ID = "ovos-skill-color-picker.openvoiceos"  # as keyed in the shared corpus
SKILL_ID = "ovos-skill-color-picker.krisgesling"  # actual runtime opm.skill id
LANG = "en-US"

PIPELINE = ["ovos-padacioso-pipeline-plugin"]

GOLDEN_PATH = Path(__file__).parent / "golden_utterances.jsonl"

# utterances lifted verbatim from OTHER skills' golden-utterance slices,
# picked for lexical overlap with color-picker's "color"/"colour"/"hex"/
# "RGB" vocabulary.
NEGATIVE_UTTERANCES = [
    ("take a picture", "ovos-skill-camera.openvoiceos"),
    ("count to ten", "ovos-skill-count.openvoiceos"),
    ("what happened today in history", "ovos-skill-days-in-history.openvoiceos"),
    ("launch spotify", "ovos-skill-application-launcher.openvoiceos"),
    ("are you ready", "ovos-skill-boot-finished.openvoiceos"),
    ("turn on the lights", "ovos-skill-homeassistant.openvoiceos"),
    ("what's the weather", "ovos-skill-weather.openvoiceos"),
]


def _candidates(skill_id: str, intent_label: str) -> set:
    """Different ovos-core/padacioso versions register the matched-intent
    bus event under different normalizations of the ``.intent`` filename
    basename -- observed variants include the bare basename with no
    extension (current OVOS-INTENT-2 naming) and the basename with the
    extension kept (older naming, e.g. what this repo's pinned ``coverage``
    CI job's older ovos-core resolves to). Candidates cover both so the
    suite isn't pinned to whichever version happens to be installed."""
    base = intent_label.removesuffix(".intent")
    return {f"{skill_id}:{intent_label}", f"{skill_id}:{base}"}


def _load_golden_rows():
    rows = []
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("needs_manual"):
                continue
            assert row["skill_id"] == CORPUS_SKILL_ID
            rows.append(row)
    return rows


GOLDEN_ROWS = [pytest.param(r, id=r["utterance"]) for r in _load_golden_rows()]


@pytest.fixture(scope="module")
def minicroft():
    mc = get_minicroft([SKILL_ID])
    yield mc
    mc.stop()


def _types(mc, text, session_id):
    session = Session(session_id)
    session.lang = LANG
    session.pipeline = list(PIPELINE)
    utterance = Message(
        "recognizer_loop:utterance",
        {"utterances": [text], "lang": LANG},
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


@pytest.mark.timeout(60)
@pytest.mark.parametrize("row", GOLDEN_ROWS, ids=lambda r: r["utterance"])
def test_golden_utterance(minicroft, row):
    candidates = _candidates(SKILL_ID, row["intent_label"])
    types = _types(minicroft, row["utterance"], f"golden-{row['utterance']}")
    assert any(t in candidates for t in types), (
        f"{row['utterance']!r}: expected one of {sorted(candidates)!r}, got {types!r}"
    )


@pytest.mark.timeout(60)
@pytest.mark.parametrize("negative", NEGATIVE_UTTERANCES, ids=lambda n: n[0])
def test_negative_confusable_not_claimed(minicroft, negative):
    text, source_skill = negative
    types = _types(minicroft, text, f"negative-{text}")
    claimed = any(t.startswith(f"{SKILL_ID}:") for t in types)
    assert not claimed, f"{text!r} (from {source_skill}) was incorrectly claimed by {SKILL_ID}"


# each row: (utterance, own intent label, sibling labels it must NOT match)
SIBLING_NEGATIVES = [
    ("show me the color red", "request-color-by-name.intent",
     ["request-color-by-hex.intent", "request-color-by-rgb.intent"]),
    ("what color has a hex code of ff5733", "request-color-by-hex.intent",
     ["request-color-by-name.intent", "request-color-by-rgb.intent"]),
    ("what color has an RGB value of 255 0 0", "request-color-by-rgb.intent",
     ["request-color-by-name.intent", "request-color-by-hex.intent"]),
]


@pytest.mark.timeout(60)
@pytest.mark.parametrize("row", SIBLING_NEGATIVES, ids=lambda r: r[0])
def test_sibling_intent_not_claimed(minicroft, row):
    """The by-hex/by-name/by-rgb intents share overlapping "color"/"colour"
    vocabulary; each utterance must route to exactly its own sibling, never
    one of the others."""
    text, own_label, sibling_labels = row
    types = _types(minicroft, text, f"sibling-{text}")
    own_candidates = _candidates(SKILL_ID, own_label)
    assert any(t in own_candidates for t in types), (
        f"{text!r}: expected one of {sorted(own_candidates)!r}, got {types!r}"
    )
    for sibling_label in sibling_labels:
        sibling_candidates = _candidates(SKILL_ID, sibling_label)
        assert not any(t in sibling_candidates for t in types), (
            f"{text!r}: incorrectly also claimed by sibling {sibling_label!r} "
            f"({types!r})"
        )
