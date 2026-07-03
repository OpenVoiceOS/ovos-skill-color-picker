"""End-to-end intent routing tests for the en-US locale.

Each canonical utterance is fired through a real MiniCroft and asserted to
route to the expected padatious intent handler and run it to completion.
Assertions cover the intent binding and handler lifecycle, not dialog content.
"""
import unittest

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft

SKILL_ID = "ovos-skill-color-picker.krisgesling"


class TestColorPickerIntentsEnUS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_minicroft([SKILL_ID])

    @classmethod
    def tearDownClass(cls):
        cls.minicroft.stop()

    def _run(self, text):
        session = Session("test-session")
        session.pipeline = [
            "ovos-adapt-pipeline-plugin-high",
            "ovos-padatious-pipeline-plugin-high",
            "ovos-adapt-pipeline-plugin-medium",
            "ovos-adapt-pipeline-plugin-low",
        ]
        utterance = Message(
            "recognizer_loop:utterance",
            {"utterances": [text], "lang": "en-US"},
            {"session": session.serialize(), "source": "A", "destination": "B"},
        )
        capture = CaptureSession(self.minicroft)
        capture.capture(utterance, timeout=30)
        return capture.finish()

    def _assert_intent(self, text, intent_file):
        messages = self._run(text)
        types = [m.msg_type for m in messages]
        self.assertIn(f"{SKILL_ID}:{intent_file}", types)

    def test_request_color_by_name(self):
        self._assert_intent("show me the color blue", "request-color-by-name.intent")

    def test_request_colour_by_name_spelling(self):
        self._assert_intent("show me the colour blue", "request-color-by-name.intent")

    def test_request_color_by_hex(self):
        self._assert_intent("what color has a hex code of ffffff", "request-color-by-hex.intent")

    def test_request_color_by_rgb(self):
        self._assert_intent("what color has an RGB value of 255 0 0", "request-color-by-rgb.intent")
