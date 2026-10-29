"""Spoken answers of the skill on the m2v prototype pipeline in en-US.

``test_golden_utterances.py`` checks only which intent m2v picks. This suite
sends each utterance through the bus on the same boot and reads the first
``speak``: the dialog name and the words the user hears.

The first five cases are the effect cases of the JarbasAl m2v test. For the
two by-name cases the expected words are the colour name only. The skill casts
a colour name to its palette (``cast_to_palette`` defaults to true), so "blue"
answers Pastel Blue #6C8DAA and "red" answers Dusty Red #B9484E on the
padacioso pipeline too. A hex code of the plain colour is not in the answer.

The other cases are the first three golden rows of each en-US intent. For a
hex row the expected words are the RGB values of that hex code. For an RGB row
they are the hex code of those values. Both are computed in this file from the
utterance.

An m2v prototype match carries no slot value: ``match_data`` holds only the
utterance and the confidence. Each handler then speaks ``color_not_found``.
Those cases are ``xfail(strict=True)``, so they fail the suite on the day the
engine fills the slots.
"""
import re
import time
from pathlib import Path

import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import M2V_PROTOTYPE_PIPELINE, M2V_PUBLISHED_MODEL, get_m2v_minicroft
from ovoscope.golden_minicroft import warm_m2v_models

SKILL_ID = "ovos-skill-color-picker.krisgesling"
LANG = "en-US"
GOLDEN_FILE = Path(__file__).parent / f"golden_utterances_{LANG}.jsonl"

BY_NAME = {"report_color_by_name"}
BY_HEX = {"report_color_by_hex_name_known", "report_color_by_hex_name_not_known"}
BY_RGB = {"report_color_by_rgb_name_known", "report_color_by_rgb_name_not_known"}

# Measured with this boot on the five JarbasAl cases and the 12 golden cases:
# no case with a slot gap answered with a colour.
NOT_FOUND = pytest.mark.xfail(strict=True, reason=(
    "m2v prototype match carries no slot value; measured: 13 of 17 cases speak "
    "color_not_found (golden by-name 6 of 6, by-hex 3 of 3, by-RGB 3 of 3, "
    "JarbasAl 1 of 5)"))


def _rgb_words(hex_code):
    red, green, blue = (int(hex_code[i:i + 2], 16) for i in (0, 2, 4))
    return [f"red {red}, green {green}, blue {blue}"]


def _hex_words(rgb):
    return ["#" + "".join(f"{int(value):02x}" for value in rgb.split())]


def _hex_in(utterance):
    return re.search(r"\b[0-9a-f]{6}\b", utterance).group(0)


def _rgb_in(utterance):
    return re.search(r"\d+ \d+ \d+", utterance).group(0)


JARBASAL_CASES = [
    pytest.param("Show me the color blue", BY_NAME, ["blue"], marks=NOT_FOUND),
    pytest.param("what color has a hex code of ff0000", BY_HEX, ["red", "255"]),
    pytest.param("what color has an RGB value of 255 0 0", BY_RGB, ["ff0000"]),
    pytest.param("which color is red", BY_NAME, ["red"]),
    pytest.param("what colour is the RGB value 128 128 128", BY_RGB, ["808080"]),
]

GOLDEN_SAMPLE = {
    "request_color_by_name": [
        ("can you tell me what colour vermilion is", BY_NAME, ["vermilion"]),
        ("do you know what colour crimson is", BY_NAME, ["crimson"]),
        ("what sort of colour is teal", BY_NAME, ["teal"]),
        ("let me see what blue looks like", BY_NAME, ["blue"]),
        ("could you put the colour blue on the screen", BY_NAME, ["blue"]),
        ("what does navy blue look like", BY_NAME, ["blue"]),
    ],
    "request_color_by_hex": [
        (row, BY_HEX, _rgb_words(_hex_in(row))) for row in (
            "what colour does the hex code 1e90ff give me",
            "tell me the colour for hex ff5733",
            "which colour does hex 3498db stand for",
        )
    ],
    "request_color_by_rgb": [
        (row, BY_RGB, _hex_words(_rgb_in(row))) for row in (
            "what colour do I get with RGB 0 128 255",
            "which colour has the red green blue values 255 0 0",
            "name the colour with RGB 128 128 128",
        )
    ],
}
GAP_BY_INTENT = {
    "request_color_by_name": NOT_FOUND,
    "request_color_by_hex": NOT_FOUND,
    "request_color_by_rgb": NOT_FOUND,
}
GOLDEN_CASES = [
    pytest.param(utterance, dialogs, words, marks=GAP_BY_INTENT[intent], id=f"{intent}-{utterance}")
    for intent, cases in GOLDEN_SAMPLE.items()
    for utterance, dialogs, words in cases
]


@pytest.fixture(scope="module")
def minicroft():
    minicroft = get_m2v_minicroft([SKILL_ID], model=M2V_PUBLISHED_MODEL,
                                  lang=LANG, classifier=False)
    warm_m2v_models(minicroft)
    yield minicroft
    minicroft.stop()


def _first_answer(minicroft, utterance, timeout=15):
    answers = []
    for msg_type in ("speak", "complete_intent_failure"):
        minicroft.bus.on(msg_type, answers.append)
    session = Session(session_id=f"m2v-effect-{abs(hash(utterance))}",
                      pipeline=list(M2V_PROTOTYPE_PIPELINE))
    session.lang = LANG
    try:
        minicroft.bus.emit(Message("recognizer_loop:utterance",
                                   {"utterances": [utterance], "lang": LANG},
                                   {"session": session.serialize(), "lang": LANG}))
        deadline = time.time() + timeout
        while not answers and time.time() < deadline:
            time.sleep(0.05)
    finally:
        for msg_type in ("speak", "complete_intent_failure"):
            minicroft.bus.remove(msg_type, answers.append)
    assert answers, f"{utterance!r}: no speak and no complete_intent_failure in {timeout}s"
    return answers[0]


@pytest.mark.timeout(900)
@pytest.mark.parametrize("utterance,dialogs,words", JARBASAL_CASES + GOLDEN_CASES)
def test_spoken_answer_names_the_colour(minicroft, utterance, dialogs, words):
    answer = _first_answer(minicroft, utterance)
    assert answer.msg_type == "speak", f"{utterance!r}: {answer.msg_type}"
    dialog = (answer.data.get("meta") or {}).get("dialog")
    spoken = answer.data["utterance"]
    assert dialog in dialogs, f"{utterance!r}: spoke {dialog} {spoken!r}, expected one of {sorted(dialogs)}"
    for word in words:
        assert word in spoken.lower(), f"{utterance!r}: {spoken!r} lacks {word!r}"


def test_golden_sample_rows_are_golden_rows():
    rows = GOLDEN_FILE.read_text(encoding="utf-8")
    for intent, cases in GOLDEN_SAMPLE.items():
        for utterance, _, _ in cases:
            assert f'"utterance": "{utterance}", "lang": "{LANG}", "intent_label": "{intent}"' in rows, (
                f"{utterance!r} is not a {intent} row of {GOLDEN_FILE.name}")
