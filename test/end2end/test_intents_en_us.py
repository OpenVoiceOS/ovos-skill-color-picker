"""End-to-end intent-routing tests for ovos-skill-color-picker (en-US).

Each case boots an in-process MiniCroft with the skill loaded and feeds a real
utterance through the padatious pipeline, asserting where it routes and how the
``{color}`` slot is filled. One case proves the ``color_exclude`` slot-value
exclusion: a bare pronoun ("that") captured by the open ``{color}`` slot is
rejected as a non-color and re-prompted instead of reported.

Run: pytest test/end2end/ -v
"""
import time
from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import get_minicroft

SKILL_ID = "ovos-skill-color-picker.krisgesling"
LANG = "en-US"

# Exact expansions score conf 1.0 (the -high band); the {color} slot variants
# land lower, so register both padatious bands.
PIPELINE = [
    "ovos-padatious-pipeline-plugin-high",
    "ovos-padatious-pipeline-plugin-medium",
]


class _RoutingTest(TestCase):
    """Shared MiniCroft harness for padatious intent routing."""

    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_minicroft([SKILL_ID])
        cls.bus = cls.minicroft.bus

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "minicroft", None):
            cls.minicroft.stop()

    def _run(self, utterance):
        """Emit ``utterance`` and collect the by-name intent + speak output."""
        intents = []
        spoken = []
        by_name = f"{SKILL_ID}:request-color-by-name.intent"
        handlers = {
            by_name: lambda m: intents.append(("request-color-by-name.intent",
                                                m.data.get("color"))),
        }
        for msg_type, cb in handlers.items():
            self.bus.on(msg_type, cb)
        speak_cb = lambda m: spoken.append(m.data.get("utterance", ""))
        self.bus.on("speak", speak_cb)
        try:
            session = Session(f"e2e-en_us-{abs(hash(utterance))}")
            session.lang = LANG
            session.pipeline = PIPELINE
            self.bus.emit(Message(
                "recognizer_loop:utterance",
                {"utterances": [utterance], "lang": LANG},
                {"session": session.serialize()},
            ))
            time.sleep(3)
        finally:
            for msg_type, cb in handlers.items():
                self.bus.remove(msg_type, cb)
            self.bus.remove("speak", speak_cb)
        return intents, spoken


class TestByNameRouting(_RoutingTest):
    """request-color-by-name.intent with the {color} slot filled."""

    def test_set_the_color_to_red(self):
        intents, _ = self._run("set the color to red")
        self.assertIn(("request-color-by-name.intent", "red"), intents)

    def test_show_me_blue(self):
        intents, _ = self._run("show me the color blue")
        self.assertIn(("request-color-by-name.intent", "blue"), intents)


class TestBlacklistSlotExclusion(_RoutingTest):
    """A bare pronoun must never be reported as a color.

    The open ``{color}`` slot will capture a demonstrative pronoun ("set the
    color to that"), but the ``color_exclude`` vocabulary marks such values as
    non-colors. The handler rejects them and re-prompts with ``color-not-found``
    instead of announcing a bogus color report for "that".
    """

    def test_pronoun_is_not_reported_as_a_color(self):
        _, spoken = self._run("set the color to that")
        joined = " ".join(spoken).lower()
        self.assertIn("could not find", joined,
                      "pronoun should trigger the color-not-found re-prompt")
        self.assertNotIn("hex value", joined,
                         "'that' must not yield a color report")
