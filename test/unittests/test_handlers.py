"""Handler behaviour of the skill on a FakeBus, with no intent engine.

Each test calls a handler with the message an engine sends and reads the
dialog the handler speaks. The expected values come from ovos-color-parser or
from arithmetic on the input, never from the skill.
"""
import os
import tempfile
import unittest
from unittest.mock import patch

from ovos_bus_client.message import Message
from ovos_color_parser import color_from_description
from ovos_utils.messagebus import FakeBus

from ovos_skill_color_picker import ColorPickerSkill

SKILL_ID = "ovos-skill-color-picker.krisgesling"
BY_HEX = {"report_color_by_hex_name_known", "report_color_by_hex_name_not_known"}
BY_RGB = {"report_color_by_rgb_name_known", "report_color_by_rgb_name_not_known"}


def _skill():
    skill = ColorPickerSkill()
    skill._startup(FakeBus(), SKILL_ID)
    return skill


def _intent_handlers(skill):
    return {intent: getattr(skill, name)
            for name in dir(type(skill))
            for intent in getattr(getattr(type(skill), name), "intents", [])}


class TestIntentHandlers(unittest.TestCase):
    def setUp(self):
        # Skill settings persist under XDG_CONFIG_HOME: one fresh tree per test.
        xdg = tempfile.TemporaryDirectory()
        self.addCleanup(xdg.cleanup)
        env = patch.dict(os.environ, {"XDG_CONFIG_HOME": xdg.name})
        env.start()
        self.addCleanup(env.stop)
        self.skill = _skill()
        patcher = patch.object(self.skill, "speak_dialog")
        self.speak_dialog = patcher.start()
        self.addCleanup(patcher.stop)

    def _spoken(self):
        return [call.args[0] for call in self.speak_dialog.call_args_list]

    def test_one_intent_per_colour_format(self):
        self.assertEqual(set(_intent_handlers(self.skill)),
                         {"request_color_by_name.intent",
                          "request_color_by_hex.intent",
                          "request_color_by_rgb.intent"})

    def test_missing_slot_speaks_color_not_found(self):
        for intent, handler in _intent_handlers(self.skill).items():
            for data in ({}, {"color": ""}, {"color": None}, {"hex_code": ""},
                         {"hex_code": None}, {"rgb": ""}, {"rgb": None}):
                with self.subTest(intent=intent, data=data):
                    self.speak_dialog.reset_mock()
                    handler(Message(f"{SKILL_ID}:{intent[:-7]}", data))
                    self.assertEqual(self._spoken(), ["color_not_found"])

    def test_named_colour_reports_the_parser_colour(self):
        handler = _intent_handlers(self.skill)["request_color_by_name.intent"]
        expected = color_from_description("light sea green", lang="en",
                                          cast_to_palette=True, fuzzy=True)
        handler(Message("", {"color": "light sea green"}))
        self.speak_dialog.assert_called_once()
        self.assertEqual(self.speak_dialog.call_args.args[0], "report_color_by_name")
        data = self.speak_dialog.call_args.kwargs["data"]
        self.assertEqual((data["color_name"], data["hex_code"]),
                         (expected.name, expected.hex_str))

    def test_cast_to_palette_setting_reaches_the_parser(self):
        handler = _intent_handlers(self.skill)["request_color_by_name.intent"]
        self.skill.settings["cast_to_palette"] = False
        expected = color_from_description("red", lang="en", cast_to_palette=False, fuzzy=True)
        handler(Message("", {"color": "red"}))
        data = self.speak_dialog.call_args.kwargs["data"]
        self.assertEqual(data["hex_code"], expected.hex_str)
        self.assertNotEqual(expected.hex_str,
                            color_from_description("red", lang="en", cast_to_palette=True,
                                                   fuzzy=True).hex_str)

    def test_hex_code_in_the_colour_slot_reports_its_rgb_values(self):
        handler = _intent_handlers(self.skill)["request_color_by_name.intent"]
        handler(Message("", {"color": "1e 90 ff"}))
        self.speak_dialog.assert_called_once()
        self.assertIn(self.speak_dialog.call_args.args[0], BY_HEX)
        data = self.speak_dialog.call_args.kwargs["data"]
        self.assertEqual((data["red_value"], data["green_value"], data["blue_value"]),
                         (0x1e, 0x90, 0xff))

    def test_rgb_values_in_the_colour_slot_report_their_hex_code(self):
        handler = _intent_handlers(self.skill)["request_color_by_name.intent"]
        handler(Message("", {"color": "0 128 255"}))
        self.speak_dialog.assert_called_once()
        self.assertIn(self.speak_dialog.call_args.args[0], BY_RGB)
        self.assertEqual(self.speak_dialog.call_args.kwargs["data"]["hex_code"].lower(),
                         "#" + "".join(f"{value:02x}" for value in (0, 128, 255)))

    def test_blacklisted_pronoun_speaks_color_not_found(self):
        handler = _intent_handlers(self.skill)["request_color_by_name.intent"]
        handler(Message("", {"color": "that"}))
        self.assertEqual(self._spoken(), ["color_not_found"])
