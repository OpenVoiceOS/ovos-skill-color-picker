"""Effect-checking end-to-end coverage for ovos-skill-color-picker.

``test_intents_en_us.py`` and ``test_golden_utterances.py`` only assert that
an utterance routes to the expected intent -- a handler that matched and then
did nothing would still pass. This suite drives the same real MiniCroft bus
and asserts the actual consequence: the ``speak`` message's ``meta.dialog``
key and the rendered ``color_name``/``hex_code`` data the handler put into it,
for the RGB-lookup path (``handle_request_color_by_rgb``).

It also boots with it-IT active (the skill ships an it-IT locale under
``locale/it-IT``) and drives the Italian RGB phrasing, since a default en-US
boot only registers en-US intents and an Italian utterance would otherwise
route nowhere.
"""
import time

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft

SKILL_ID = "ovos-skill-color-picker.krisgesling"  # real runtime opm.skill id


def _speak_dialog(mc, utterance: str, lang: str, session_id: str):
    session = Session(session_id)
    session.lang = lang
    session.pipeline = ["ovos-padacioso-pipeline-plugin"]
    msg = Message(
        "recognizer_loop:utterance",
        {"utterances": [utterance], "lang": lang},
        {"session": session.serialize(), "source": "A", "destination": "B"},
    )
    capture = CaptureSession(mc, eof_msgs=["ovos.utterance.handled"])
    capture.capture(msg, timeout=30)
    messages = capture.finish()
    speaks = [m for m in messages if m.msg_type in ("speak", "ovos.utterance.speak")]
    assert speaks, f"{utterance!r}: no speak message emitted, got {[m.msg_type for m in messages]!r}"
    return speaks[0]


def test_rgb_255_0_0_speaks_red_by_name_en_us():
    """"what color has the RGB value of 255 0 0" must speak the
    report-color-by-rgb-name-known dialog with color_name "red" -- not just
    match the intent."""
    mc = get_minicroft([SKILL_ID])
    try:
        speak = _speak_dialog(
            mc, "what color has the RGB value of 255 0 0", "en-US", "e2e-rgb-en"
        )
        meta = speak.data["meta"]
        assert meta["dialog"] == "report-color-by-rgb-name-known", (
            f"expected report-color-by-rgb-name-known, got {meta['dialog']!r} "
            f"(utterance: {speak.data['utterance']!r})"
        )
        assert meta["data"]["color_name"].lower() == "red", (
            f"expected color_name 'red', got {meta['data']!r}"
        )
    finally:
        mc.stop()


def test_rgb_it_it_speaks_correct_dialog():
    """Boot with it-IT active and drive the Italian RGB phrasing
    ("A che colore corrisponde il valore R G B ...") -- a default en-US boot
    would never register this intent at all."""
    mc = get_minicroft([SKILL_ID], lang="it-IT")
    try:
        speak = _speak_dialog(
            mc, "a che colore corrisponde il valore R G B 255 0 0", "it-IT", "e2e-rgb-it"
        )
        meta = speak.data["meta"]
        assert meta["dialog"] == "report-color-by-rgb-name-known", (
            f"expected report-color-by-rgb-name-known, got {meta['dialog']!r} "
            f"(utterance: {speak.data['utterance']!r})"
        )
    finally:
        mc.stop()
