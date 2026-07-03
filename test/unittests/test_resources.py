"""Fast, offline unit tests for ovos-skill-color-picker resources.

These do not boot a MiniCroft; they validate that the en-US locale ships the
padatious intents, the ``{color}`` entity vocabulary and its blacklist, and
that the color parser the skill relies on resolves a named color. This keeps
the build/coverage matrix quick while the heavy routing lives in test/end2end/.
"""
from os.path import dirname, isfile, join
from unittest import TestCase

SKILL_ROOT = dirname(dirname(dirname(__file__)))
EN_US = join(SKILL_ROOT, "locale", "en-US")


def _read(*parts):
    path = join(EN_US, *parts)
    assert isfile(path), f"missing resource: {path}"
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestLocaleResources(TestCase):
    def test_intent_files_present(self):
        for name in ("request-color.intent",
                     "request-color-by-name.intent",
                     "request-color-by-hex.intent",
                     "request-color-by-rgb.intent"):
            self.assertTrue(_read("intents", name).strip(),
                            f"{name} is empty")

    def test_by_name_intent_uses_color_slot(self):
        self.assertIn("{color}", _read("intents", "request-color-by-name.intent"))

    def test_color_entity_lists_named_colors(self):
        entity = _read("entities", "color.entity").lower()
        for color in ("red", "blue", "green"):
            self.assertIn(color, entity)

    def test_color_exclude_voc_lists_pronouns(self):
        blacklist = {line.strip().lower()
                     for line in _read("vocab", "color_exclude.voc").splitlines()
                     if line.strip()}
        for pronoun in ("it", "that", "this"):
            self.assertIn(pronoun, blacklist)


class TestColorParser(TestCase):
    def test_named_color_resolves(self):
        from ovos_color_parser import color_from_description
        color = color_from_description("red", lang="en")
        self.assertIsNotNone(color)
        self.assertTrue(color.hex_str)
