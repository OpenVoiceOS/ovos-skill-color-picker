import unittest
from os.path import dirname

from ovos_plugin_manager.skills import find_skill_plugins
from ovos_utils.messagebus import FakeBus
from ovos_workshop.skill_launcher import PluginSkillLoader, SkillLoader
from ovos_skill_color_picker import ColorPickerSkill


class TestSkillLoading(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.skill_id = "ovos-skill-color-picker.krisgesling"
        self.path = dirname(dirname(dirname(__file__)))

    def test_from_class(self):
        bus = FakeBus()
        skill = ColorPickerSkill()
        skill._startup(bus, self.skill_id)
        self.assertEqual(skill.bus, bus)
        self.assertEqual(skill.skill_id, self.skill_id)

    def test_from_plugin(self):
        bus = FakeBus()
        for skill_id, plug in find_skill_plugins().items():
            if skill_id == self.skill_id:
                skill = plug()
                skill._startup(bus, self.skill_id)
                self.assertEqual(skill.bus, bus)
                self.assertEqual(skill.skill_id, self.skill_id)
                break
        else:
            raise RuntimeError("plugin not found")

    def test_from_loader(self):
        bus = FakeBus()
        loader = SkillLoader(bus, self.path)
        loader.load()
        self.assertEqual(loader.instance.bus, bus)
        self.assertEqual(loader.instance.root_dir, self.path)

    def test_from_plugin_loader(self):
        bus = FakeBus()
        loader = PluginSkillLoader(bus, self.skill_id)
        for skill_id, plug in find_skill_plugins().items():
            if skill_id == self.skill_id:
                loader.load(plug)
                break
        else:
            raise RuntimeError("plugin not found")

        self.assertEqual(loader.skill_id, self.skill_id)
        self.assertEqual(loader.instance.bus, bus)
        self.assertEqual(loader.instance.skill_id, self.skill_id)


class TestColorEntityRegistration(unittest.TestCase):
    """Unit-level, no-MiniCroft proof that ``color.entity`` reaches the
    padatious pipeline with NO manual registration call anywhere in this
    skill.

    ovos-workshop>=9.5.0a1 auto-registers every ``.entity`` file shipped
    under a skill's locale resources the first time that language's
    resources are loaded (during ``_startup()``) -- no skill-authored
    ``initialize()``/``register_entity_file()`` wiring required. This test
    boots the skill via ``_startup()`` alone and asserts the
    ``padatious:register_entity`` message for "color" landed on the bus
    with the expected sample values.

    Mutation tripwire: delete/rename
    ``locale/en-US/entities/color.entity`` and this test goes red -- there
    is nothing left in the skill to register it, since discovery walks the
    on-disk locale/ directory.

    NOTE: an ``*.entity`` file is training-data bias for a padatious
    ``{slot}``, not an admission-control allowlist -- an unlisted value
    remains capturable by the slot (empirically confirmed: a nonsense token
    in the {color} position still matched request-color-by-name.intent at
    padatious-high both before and after this change). This test only
    proves the entity reaches the engine, not that unknown values get
    rejected.
    """

    def test_color_entity_reaches_padatious_on_startup(self):
        bus = FakeBus()
        captured = []
        bus.on("padatious:register_entity", captured.append)

        skill_id = "ovos-skill-color-picker.krisgesling"
        skill = ColorPickerSkill()
        skill._startup(bus, skill_id)

        registrations = [m for m in captured
                         if m.data.get("name", "").endswith(":color")]
        self.assertEqual(len(registrations), 1,
                         "color.entity must be registered exactly once with the intent engine")
        samples = registrations[0].data.get("samples") or []
        # sample colors drawn straight from locale/en-US/entities/color.entity
        self.assertIn("teal", samples)
        self.assertIn("maroon", samples)
