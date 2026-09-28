"""m2v-multilingual candidate-default gate for ovos-skill-color-picker.

Boots the skill through the candidate default intent engine -- the
model2vec multilingual classifier (``OpenVoiceOS/ovos-m2v-intents-multi-128M-v5``)
-- via ovoscope's ``get_m2v_minicroft`` and asserts, for a representative slice
of the skill's own golden utterances, the whole round trip: the correct intent
routed AND the rendered spoken dialog carries real answer words (the color
name / hex / RGB channel values), never the raw dialog file name.

The skill's real registered ``opm.skill`` entry point is
``ovos-skill-color-picker.krisgesling`` -- the shared golden corpus keys this
skill as ``ovos-skill-color-picker.openvoiceos``, which does not match any
installed skill_id. This suite loads the skill under its real runtime id
(matching the pre-existing ``test/end2end/test_intents_en_us.py`` and
``test_golden_utterances.py``) so the model is exercised against what
actually boots.

FINDING: the m2v-multilingual model's classes carry
``ovos-skill-color-picker.openvoiceos:request-color-by-name`` (and its three
siblings), never ``ovos-skill-color-picker.krisgesling:*`` -- the label
namespace the model was trained on assumes the id the shared golden corpus
uses, not this skill's real ``opm.skill`` entry point. Under the real runtime
id nothing intersects and every utterance below fails to route
(``complete_intent_failure``); this is a total id-namespace miss, not a
model-quality mispredict, so every effect case is recorded ``xfail(strict=True)``
instead of skipped or loosened, so a corpus/entry-point fix flips it green.
"""
import os
import shutil
import tempfile
import unittest

import pytest

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session

from ovoscope import get_m2v_minicroft, M2V_PIPELINE

SKILL_ID = "ovos-skill-color-picker.krisgesling"
LANG = "en-US"

_MC = None
_PIPE = None
_XDG = None
_ORIG_XDG = None


def setUpModule():
    global _MC, _PIPE, _XDG, _ORIG_XDG
    _ORIG_XDG = os.environ.get("XDG_DATA_HOME")
    _XDG = tempfile.mkdtemp(prefix="ovoscope-m2v-color-picker-xdg-")
    os.environ["XDG_DATA_HOME"] = _XDG

    _MC = get_m2v_minicroft(skill_ids=[SKILL_ID], lang=LANG)
    _PIPE = _MC.intents.pipeline_plugins["ovos-m2v-pipeline"]
    _PIPE._ensure_model(background_ok=False)


def tearDownModule():
    global _MC, _XDG, _ORIG_XDG
    if _MC is not None:
        _MC.stop()
        _MC = None
    if _ORIG_XDG is None:
        os.environ.pop("XDG_DATA_HOME", None)
    else:
        os.environ["XDG_DATA_HOME"] = _ORIG_XDG
    if _XDG is not None:
        shutil.rmtree(_XDG, ignore_errors=True)
        _XDG = None


_XFAIL_REASON = (
    "id-namespace mismatch: the m2v-multilingual model's classes carry "
    "ovos-skill-color-picker.openvoiceos:<intent>, this skill's real opm.skill "
    "entry point registers as ovos-skill-color-picker.krisgesling:<intent> -- "
    "no class intersects the runtime id so nothing routes (see module docstring)"
)


@pytest.mark.xfail(reason=_XFAIL_REASON, strict=True)
class TestM2VColorPickerGoldenEffect(unittest.TestCase):
    """Effect assertions: golden utterance in -> correct intent -> real color words out."""

    def _run(self, utterance: str, lang: str = LANG, timeout: float = 15.0):
        speaks = []
        failures = []

        def _on_speak(msg):
            speaks.append(msg)

        def _on_fail(msg):
            failures.append(msg)

        _MC.bus.on("speak", _on_speak)
        _MC.bus.on("complete_intent_failure", _on_fail)
        sess = Session(session_id=f"m2v-golden-{hash(utterance)}", pipeline=M2V_PIPELINE)
        sess.lang = lang
        try:
            _MC.bus.emit(Message(
                "recognizer_loop:utterance",
                data={"utterances": [utterance], "lang": lang},
                context={"session": sess.serialize(), "lang": lang},
            ))
            import time as _t
            deadline = _t.time() + timeout
            while _t.time() < deadline and not speaks and not failures:
                _t.sleep(0.05)
        finally:
            _MC.bus.remove("speak", _on_speak)
            _MC.bus.remove("complete_intent_failure", _on_fail)

        if not speaks:
            return None, None, bool(failures)
        data = speaks[0].data
        meta = data.get("meta", {}) or {}
        return meta.get("dialog"), (data.get("utterance") or ""), False

    def _assert_effect(self, utterance, expected_intent, expected_dialogs, expected_substrings):
        dialog, text, failed = self._run(utterance)
        self.assertFalse(failed, f"{utterance!r} did not route: complete_intent_failure")
        self.assertIsNotNone(text, f"{utterance!r} produced no spoken output")
        low = text.lower()
        self.assertIn(
            dialog, expected_dialogs,
            f"{utterance!r} routed to dialog {dialog!r}, expected one of "
            f"{expected_dialogs!r} (rendered: {text!r})")
        self.assertNotIn(
            dialog, low,
            f"{utterance!r} spoke the dialog NAME, not rendered text: {text!r}")
        for sub in expected_substrings:
            self.assertIn(
                sub.lower(), low,
                f"{utterance!r} rendered {text!r}; missing {sub!r}")

    def test_show_me_the_color_blue(self):
        # request-color-by-name.intent -> report-color-by-name, real hex + name.
        self._assert_effect(
            "Show me the color blue", "request-color-by-name.intent",
            ["report-color-by-name"], ["blue", "0000ff"])

    def test_what_color_has_hex_code_of_ff0000(self):
        # request-color-by-hex.intent -> report-color-by-hex-name-known/not-known.
        self._assert_effect(
            "what color has a hex code of ff0000", "request-color-by-hex.intent",
            ["report-color-by-hex-name-known", "report-color-by-hex-name-not-known"],
            ["red", "255"])

    def test_what_color_has_rgb_value_255_0_0(self):
        # request-color-by-rgb.intent -> report-color-by-rgb-name-known/not-known.
        self._assert_effect(
            "what color has an RGB value of 255 0 0", "request-color-by-rgb.intent",
            ["report-color-by-rgb-name-known", "report-color-by-rgb-name-not-known"],
            ["ff0000"])

    def test_which_color_is_red(self):
        # request-color.intent (ambiguous format) -> forwards to by-name.
        self._assert_effect(
            "which color is red", "request-color.intent",
            ["report-color-by-name"], ["red", "ff0000"])

    def test_what_colour_is_rgb_128_128_128(self):
        # British spelling; request-color-by-rgb.intent -> grey.
        self._assert_effect(
            "what colour is the RGB value 128 128 128", "request-color-by-rgb.intent",
            ["report-color-by-rgb-name-known", "report-color-by-rgb-name-not-known"],
            ["808080"])


class TestM2VRegisteredLabelRouting(unittest.TestCase):
    """Documents the id-namespace mismatch: the model's trained labels do
    NOT intersect this skill's real runtime registration, so it routes
    nothing through the m2v-multilingual pipeline as currently packaged."""

    def test_registered_skill_id_labels_do_not_intersect(self):
        classes = {str(c) for c in _PIPE.model.classes_}
        registered = set(_PIPE.intents)
        self.assertIn(f"{SKILL_ID}:request-color-by-name", registered)
        self.assertIn(
            "ovos-skill-color-picker.openvoiceos:request-color-by-name", classes,
            "expected the model to still carry the .openvoiceos-namespaced "
            "label this finding is about; if this now fails the model itself "
            "changed and this test needs re-checking, not the assertion below")
        self.assertFalse(
            registered & classes,
            f"{SKILL_ID}'s registered labels now intersect the model's classes "
            "-- the id-namespace mismatch this test documents appears fixed; "
            "flip TestM2VColorPickerGoldenEffect's xfail back to a real gate")


if __name__ == "__main__":
    unittest.main()
