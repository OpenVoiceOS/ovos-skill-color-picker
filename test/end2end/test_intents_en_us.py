"""End-to-end intent-routing tests for ovos-skill-color-picker (en-US).

Each case boots an in-process MiniCroft with the skill loaded and feeds a real
utterance through the padatious pipeline, asserting where it routes and how the
``{color}`` slot is filled. One case proves the ``color.blacklist`` slot-value
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
        # ovos-workshop>=9.3.12a1 / OVOS-INTENT-2 dispatches the matched
        # intent bus event without the ".intent" filename suffix (same
        # naming fix documented in ovos-skill-audio-recording's e2e suite);
        # listen on the bare name so this doesn't regress on the floor bump.
        by_name = f"{SKILL_ID}:request-color-by-name"
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


class TestColorSlotKnownValuesRoute(_RoutingTest):
    """Positive e2e coverage: sample colors from color.entity still route
    the {color} slot correctly after wiring
    ``self.register_entity_file("color.entity")`` into a new
    ``initialize()`` (requires ovos-workshop>=9.3.12a1 +
    ovos-padatious>=2.0.3a1).

    Fixed upstream: ovos-padatious 2.0.3a1 (PyPI) corrected a bug where a
    registered ``.entity`` file made a slot an effectively closed
    vocabulary instead of the scoring hint it's documented to be
    (INTENT-1 §5.4). Under 2.0.3a1, an out-of-list slot value still
    matches, floored into the padatious-medium confidence band
    (~[0.8, 0.92]); in-list values are unaffected. This hint behavior
    only fires when ``ovos-padatious-pipeline-plugin-medium`` is in the
    active pipeline (PIPELINE above registers high/medium/low).

    Empirically re-verified against ovos-padatious==2.0.3a1: "show me the
    color banana" (unrelated, unlisted noun, not a color.entity sample)
    now matches ``request-color-by-name.intent`` with ``{color}`` filled
    as "banana" -- proving the registration is a hint, not an allowlist.
    Listed samples ("teal", "maroon") keep matching too.

    The registration-wiring proof itself (independent of padatious
    matching behavior) is
    ``test/unittests/test_skill_loading.py::TestColorEntityRegistration``.
    """

    def test_known_color_teal_matches(self):
        """"teal" is a real sample value in
        locale/en-US/entities/color.entity."""
        intents, _ = self._run("show me the color teal")
        self.assertIn(("request-color-by-name.intent", "teal"), intents)

    def test_known_color_maroon_matches(self):
        intents, _ = self._run("what does the color maroon look like")
        self.assertIn(("request-color-by-name.intent", "maroon"), intents)

    def test_out_of_list_value_still_routes_as_hint(self):
        """Post ovos-padatious>=2.0.3a1: registering color.entity is a
        scoring HINT, not a closed vocabulary. An unrelated, unlisted
        noun ("banana") must still match request-color-by-name.intent
        with the {color} slot filled with the literal utterance value.
        """
        intents, _ = self._run("show me the color banana")
        matched = [i for i in intents if i[0] == "request-color-by-name.intent"]
        self.assertIn(
            ("request-color-by-name.intent", "banana"), matched,
            "out-of-list slot value did not route with the expected slot "
            "value -- ovos-padatious hint semantics (2.0.3a1+) may have "
            "regressed"
        )


class TestByRgbNumericSlot(_RoutingTest):
    """request-color-by-rgb.intent with a real numeric ``{rgb}`` slot.

    The ``golden_utterances.jsonl`` row for this intent uses the placeholder
    utterance "what color has an RGB value of something" precisely so that
    routing can be asserted without ever exercising the handler's numeric
    path (an unparsable placeholder short-circuits into the
    ``color-not-found`` dialog). That left a real "{rgb}" triple of digits
    -- the actual documented use case ("what color has the RGB value of 172
    172 172") -- with no e2e coverage at all: ``handle_request_color_by_rgb``
    passed the three space-split slot values to ``sRGBAColor`` as ``str``
    instead of ``int``, and ``sRGBAColor.__post_init__`` compares them with
    ``<=`` against ``int`` bounds, raising ``TypeError`` and never reaching
    ``speak_dialog`` at all.
    """

    def test_rgb_black_is_spoken(self):
        _, spoken = self._run("what color has an RGB value of 0 0 0")
        joined = " ".join(spoken).lower()
        self.assertTrue(spoken, "a valid numeric RGB triple must produce a "
                                 "spoken response, not a silently swallowed "
                                 "handler exception")
        self.assertIn("black", joined)

    def test_rgb_white_is_spoken(self):
        _, spoken = self._run("what color is the RGB value 255 255 255")
        joined = " ".join(spoken).lower()
        self.assertTrue(spoken, "a valid numeric RGB triple must produce a "
                                 "spoken response, not a silently swallowed "
                                 "handler exception")
        self.assertIn("white", joined)


class TestSiblingNegatives(_RoutingTest):
    """A hex/rgb/name utterance must route to exactly its own intent, never
    one of its by-hex/by-name/by-rgb siblings."""

    def _claimed_others(self, utterance, own_intent):
        session = Session(f"e2e-en_us-neg-{abs(hash(utterance))}")
        session.lang = LANG
        session.pipeline = PIPELINE
        claimed = []
        siblings = {
            "request-color-by-name": f"{SKILL_ID}:request-color-by-name",
            "request-color-by-hex": f"{SKILL_ID}:request-color-by-hex",
            "request-color-by-rgb": f"{SKILL_ID}:request-color-by-rgb",
        }
        handlers = {}
        for label, msg_type in siblings.items():
            if label == own_intent:
                continue
            cb = (lambda l: lambda m: claimed.append(l))(label)
            handlers[msg_type] = cb
            self.bus.on(msg_type, cb)
        try:
            self.bus.emit(Message(
                "recognizer_loop:utterance",
                {"utterances": [utterance], "lang": LANG},
                {"session": session.serialize()},
            ))
            time.sleep(3)
        finally:
            for msg_type, cb in handlers.items():
                self.bus.remove(msg_type, cb)
        return claimed

    def test_hex_utterance_not_claimed_by_name_or_rgb(self):
        claimed = self._claimed_others(
            "what color has a hex code of ff5733", "request-color-by-hex")
        self.assertEqual(claimed, [])

    def test_rgb_utterance_not_claimed_by_name_or_hex(self):
        claimed = self._claimed_others(
            "what color has an RGB value of 255 0 0", "request-color-by-rgb")
        self.assertEqual(claimed, [])

    def test_name_utterance_not_claimed_by_hex_or_rgb(self):
        claimed = self._claimed_others(
            "show me the color red", "request-color-by-name")
        self.assertEqual(claimed, [])


class TestBlacklistSlotExclusion(_RoutingTest):
    """A bare pronoun must never be reported as a color.

    The open ``{color}`` slot will capture a demonstrative pronoun ("set the
    color to that"), but the ``color.blacklist`` slot-value exclusion marks
    such values as non-colors. The handler rejects them and re-prompts with
    ``color-not-found`` instead of announcing a bogus color report for
    "that".
    """

    def test_pronoun_is_not_reported_as_a_color(self):
        _, spoken = self._run("set the color to that")
        joined = " ".join(spoken).lower()
        self.assertNotIn("hex value", joined,
                         "'that' must not yield a color report")
        self.assertIn("could not find", joined,
                      "'that' must be rejected in-handler via color-not-found")
