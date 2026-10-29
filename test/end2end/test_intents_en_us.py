"""End-to-end intent-routing tests for ovos-skill-color-picker (en-US).

Each case boots an in-process MiniCroft with the skill loaded and feeds a real
utterance through the padacioso pipeline, asserting where it routes and how the
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

PIPELINE = ["ovos-padacioso-pipeline-plugin"]


def _in_session(message, session):
    """True when ``message`` answers the utterance of ``session``.

    The bus is process-wide and its topics are shared, so a reply or an
    intent event of the preceding test can arrive after that test's window
    closed. Only a message of this call's own session counts.
    """
    ctx = (message.context or {}).get("session") or {}
    return ctx.get("session_id") == session.session_id


class _RoutingTest(TestCase):
    """Shared MiniCroft harness for padacioso intent routing."""

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
        by_name = f"{SKILL_ID}:request_color_by_name"
        session = Session(f"e2e-en_us-{abs(hash(utterance))}")
        session.lang = LANG
        session.pipeline = PIPELINE

        def by_name_cb(m):
            if _in_session(m, session):
                intents.append(("request_color_by_name.intent", m.data.get("color")))

        handlers = {by_name: by_name_cb}
        for msg_type, cb in handlers.items():
            self.bus.on(msg_type, cb)

        def speak_cb(m):
            # without the session filter, a late reply of the preceding test
            # ("i could not find that color") failed test_rgb_white_is_spoken
            # on a loaded runner
            if _in_session(m, session):
                spoken.append(m.data.get("utterance", ""))

        self.bus.on("speak", speak_cb)
        try:
            self.bus.emit(Message(
                "recognizer_loop:utterance",
                {"utterances": [utterance], "lang": LANG},
                {"session": session.serialize()},
            ))
            # Wait for this session's reply rather than sleeping a fixed
            # three seconds. A loaded two-worker runner is slower than a
            # developer machine, and a blind sleep turns that into a red.
            deadline = time.time() + 30
            while time.time() < deadline and not spoken:
                time.sleep(0.1)
            # let a second dialog of the same turn land
            time.sleep(0.5)
        finally:
            for msg_type, cb in handlers.items():
                self.bus.remove(msg_type, cb)
            self.bus.remove("speak", speak_cb)
        return intents, spoken


class TestByNameRouting(_RoutingTest):
    """request_color_by_name.intent with the {color} slot filled."""

    def test_set_the_color_to_red(self):
        intents, _ = self._run("set the color to red")
        self.assertIn(("request_color_by_name.intent", "red"), intents)

    def test_show_me_blue(self):
        intents, _ = self._run("show me the color blue")
        self.assertIn(("request_color_by_name.intent", "blue"), intents)


class TestColorSlotKnownValuesRoute(_RoutingTest):
    """Sample colors from color.entity route the {color} slot, and a value
    outside the file still routes.

    A registered ``.entity`` file is a scoring hint, not a closed vocabulary
    (INTENT-1 §5.4). Padacioso lowers the confidence of a slot value that is
    not in the file, but the intent still matches with the value filled in:
    "show me the color banana" routes to ``request_color_by_name`` with
    ``{color}`` set to "banana". Listed samples ("teal", "maroon") match at
    full confidence.

    ``test/unittests/test_skill_loading.py::TestColorEntityRegistration``
    proves the registration itself, independent of any engine.
    """

    def test_known_color_teal_matches(self):
        """"teal" is a real sample value in
        locale/en-US/entities/color.entity."""
        intents, _ = self._run("show me the color teal")
        self.assertIn(("request_color_by_name.intent", "teal"), intents)

    def test_known_color_maroon_matches(self):
        intents, _ = self._run("what does the color maroon look like")
        self.assertIn(("request_color_by_name.intent", "maroon"), intents)

    def test_out_of_list_value_still_routes_as_hint(self):
        """Registering color.entity is a scoring hint, not a closed
        vocabulary. An unrelated, unlisted
        noun ("banana") must still match request_color_by_name.intent
        with the {color} slot filled with the literal utterance value.
        """
        intents, _ = self._run("show me the color banana")
        matched = [i for i in intents if i[0] == "request_color_by_name.intent"]
        self.assertIn(
            ("request_color_by_name.intent", "banana"), matched,
            "out-of-list slot value did not route with the expected slot "
            "value: the entity file acted as a closed vocabulary"
        )


class TestByRgbNumericSlot(_RoutingTest):
    """request_color_by_rgb.intent with a real numeric ``{rgb}`` slot.

    The ``golden_utterances.jsonl`` row for this intent uses the placeholder
    utterance "what color has an RGB value of something" precisely so that
    routing can be asserted without ever exercising the handler's numeric
    path (an unparsable placeholder short-circuits into the
    ``color_not_found`` dialog). That left a real "{rgb}" triple of digits
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
            "request_color_by_name": f"{SKILL_ID}:request_color_by_name",
            "request_color_by_hex": f"{SKILL_ID}:request_color_by_hex",
            "request_color_by_rgb": f"{SKILL_ID}:request_color_by_rgb",
        }
        handlers = {}
        for label, msg_type in siblings.items():
            if label == own_intent:
                continue
            def cb(m, label=label):
                if _in_session(m, session):
                    claimed.append(label)
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
            "what color has a hex code of ff5733", "request_color_by_hex")
        self.assertEqual(claimed, [])

    def test_rgb_utterance_not_claimed_by_name_or_hex(self):
        claimed = self._claimed_others(
            "what color has an RGB value of 255 0 0", "request_color_by_rgb")
        self.assertEqual(claimed, [])

    def test_name_utterance_not_claimed_by_hex_or_rgb(self):
        claimed = self._claimed_others(
            "show me the color red", "request_color_by_name")
        self.assertEqual(claimed, [])


class TestBlacklistSlotExclusion(_RoutingTest):
    """A bare pronoun must never be reported as a color.

    The open ``{color}`` slot will capture a demonstrative pronoun ("set the
    color to that"), but the ``color.blacklist`` slot-value exclusion marks
    such values as non-colors. The handler rejects them and re-prompts with
    ``color_not_found`` instead of announcing a bogus color report for
    "that".
    """

    def test_pronoun_is_not_reported_as_a_color(self):
        _, spoken = self._run("set the color to that")
        joined = " ".join(spoken).lower()
        self.assertNotIn("hex value", joined,
                         "'that' must not yield a color report")
        self.assertIn("could not find", joined,
                      "'that' must be rejected in-handler via color_not_found")


class TestCollectorOwnSession(_RoutingTest):
    """The collector keeps only the messages of its own session.

    A late reply of another session lands inside the window here, the way a
    slow runner delivers the preceding test's answer.
    """

    def test_a_reply_of_another_session_is_not_collected(self):
        stale = "i could not find that color"

        def late_reply(message):
            self.bus.emit(Message("speak", {"utterance": stale},
                                  {"session": {"session_id": "another-test"}}))

        self.bus.on("recognizer_loop:utterance", late_reply)
        try:
            _, spoken = self._run("what color is the RGB value 255 255 255")
        finally:
            self.bus.remove("recognizer_loop:utterance", late_reply)
        self.assertNotIn(stale, spoken)
        self.assertIn("white", " ".join(spoken).lower())
