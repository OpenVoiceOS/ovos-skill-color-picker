"""Multilingual golden-utterance end-to-end coverage for
ovos-skill-color-picker.

test_golden_utterances.py only exercises en-US; every other locale under
locale/ ships all four .intent files (request_color, request_color_by_name,
request_color_by_hex, request_color_by_rgb). This suite covers every such
locale (kab is not one of them: it only ships request_color_by_name).

The corpus keys this skill as "ovos-skill-color-picker.openvoiceos", but
the real runtime opm.skill id is "ovos-skill-color-picker.krisgesling" (see
test_golden_utterances.py); this suite asserts against the runtime id.

One MiniCroft is booted PER LOCALE (module-scoped fixture, indirectly
parametrized by lang; pytest reuses one boot per distinct lang value
across every row of that lang and tears it down before moving on).

Each row asserts three things, not one: the utterance routes to the
expected intent, the handler does not raise, and every name in the row's
``expected_messages`` reaches the capture. A row declares the effect with
the legacy name ("speak"); the runtime emits the spec name
("ovos.utterance.speak"). The two are read as one effect.

Row construction: each row is derived mechanically from that locale's own
.intent template lines, with slots filled by a native color word taken
from that locale's own color.entity (never a translation of the English
rows), a hex string, or an RGB triple.
"""
import json
import re
from pathlib import Path
from typing import List

import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovos_spec_tools.messages import MIGRATION_MAP, SPEC_TO_LEGACY
from ovoscope import CaptureSession, get_minicroft

SKILL_ID = "ovos-skill-color-picker.krisgesling"
PIPELINE = ["ovos-padacioso-pipeline-plugin"]

END2END_DIR = Path(__file__).parent

LANGS = [
    "en-US", "ca-ES", "da-DK", "de-DE", "es-ES", "eu-ES", "fr-FR",
    "gl-ES", "it-IT", "nl-NL", "pt-BR", "pt-PT", "sv-SE",
]


# A row writes the effect it expects with the name the corpus uses, which is
# the legacy name ("speak"). The runtime emits the spec name
# ("ovos.utterance.speak"). Accept either, so a row is not silently true or
# silently false because of the migration.
def _effect_names(name: str) -> set:
    names = {name}
    spec = MIGRATION_MAP.get(name)
    if spec is not None:
        names.add(str(spec.value))
    legacy = SPEC_TO_LEGACY.get(name)
    if legacy is not None:
        names.add(legacy)
    return names


# An error in the handler is not a pass. OVOS catches the error, emits
# mycroft.skill.handler.error and then speaks the "skill.error" dialog, so a
# bare "speak" assertion stays true while the handler is broken.
ERROR_MSG = "mycroft.skill.handler.error"


def _candidates(skill_id: str, intent_label: str) -> set:
    base = intent_label.removesuffix(".intent")
    return {f"{skill_id}:{intent_label}", f"{skill_id}:{base}"}


def _load_rows(lang):
    path = END2END_DIR / f"golden_utterances_{lang}.jsonl"
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("needs_manual"):
                continue
            rows.append(row)
    return rows


ALL_ROWS = []
for _lang in LANGS:
    for _row in _load_rows(_lang):
        ALL_ROWS.append(_row)


def _golden_id(row):
    return f"{row['lang']}-{row['intent_label']}-{row['utterance']}"


@pytest.fixture(scope="module")
def minicroft(request):
    lang = request.param
    # keep padatious (heavy fann/numpy training, uncancellable background
    # thread) out of the boot entirely -- this suite only queries via
    # padacioso, matching test_golden_utterances.py's own pipeline choice.
    mc = get_minicroft(
        [SKILL_ID], max_wait=150, lang=lang,
        default_pipeline=["ovos-padacioso-pipeline-plugin"],
    )
    yield mc
    mc.stop()


def _messages(mc, text, lang, session_id) -> List[Message]:
    session = Session(session_id)
    session.lang = lang
    session.pipeline = list(PIPELINE)
    utterance = Message(
        "recognizer_loop:utterance",
        {"utterances": [text], "lang": lang},
        {"session": session.serialize(), "source": "A", "destination": "B"},
    )
    capture = CaptureSession(
        mc,
        # ovos-core 2.2.4a1 emits ovos.utterance.handled on the cancelled
        # path, on send_complete_intent_failure and from the stop, fallback
        # and converse services. No emitter is on the matched-intent path, so
        # a row that routes and answers correctly never sees the marker and
        # every capture runs to its full timeout. At 95 rows that is over 45
        # minutes and the CI job is cut at 25.
        #
        # mycroft.skill.handler.complete is emitted after the handler
        # returns, so it lands after every effect a row asserts (the speak
        # and the gui messages are emitted inside the handler). Ending on it
        # keeps the assertions and drops the dead wait.
        eof_msgs=["ovos.utterance.handled",
                  "mycroft.skill.handler.complete"],
        # "speak" is the effect every row declares: it must stay in the
        # capture or the row asserts nothing about the handler.
        ignore_messages=["recognizer_loop:audio_output_start",
                          "recognizer_loop:audio_output_end",
                          "mycroft.audio.play_sound"],
    )
    capture.capture(utterance, timeout=30)
    return list(capture.finish())


# What the skill must SAY, computed from the row's own utterance and never
# read back from the skill. A route plus a speak of any content is not the
# answer the user asked for: a handler that reports the wrong colour, or
# reports "color_not_found", emits a speak and routes correctly.
#
# Every success path speaks one of these dialogs with the colour in its data.
# `color_not_found` and the workshop's `skill.error` are not among them, and
# that is the point.
REPORT_DIALOGS = {
    "report_color_by_name",
    "report_color_by_hex_name_known",
    "report_color_by_hex_name_not_known",
    "report_color_by_rgb_name_known",
    "report_color_by_rgb_name_not_known",
}

_HEX_IN_UTTERANCE = re.compile(r"\b([0-9a-fA-F]{6})\b")
_RGB_IN_UTTERANCE = re.compile(r"\b(\d{1,3})\s+(\d{1,3})\s+(\d{1,3})\b")


def _expected_rgb(utterance: str):
    """The channels the row asks about, by arithmetic on the row's own text.

    A hex row carries `3498db` and an RGB row carries `52 152 219`. Both are
    the same colour, and both are converted here rather than read from the
    skill, so the check is independent of the code it measures. A named-colour
    row carries neither and returns None.
    """
    found = _HEX_IN_UTTERANCE.search(utterance)
    if found:
        digits = found.group(1)
        return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))
    found = _RGB_IN_UTTERANCE.search(utterance)
    if found:
        channels = tuple(int(part) for part in found.groups())
        if all(channel <= 255 for channel in channels):
            return channels
    return None


def _spoken_rgb(data: dict):
    """The channels the skill reported, whichever way the dialog carries them."""
    if all(key in data for key in ("red_value", "green_value", "blue_value")):
        return (int(data["red_value"]), int(data["green_value"]),
                int(data["blue_value"]))
    code = str(data.get("hex_code") or "").lstrip("#")
    if len(code) == 6:
        try:
            return tuple(int(code[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return None
    return None


def _speak_effects(messages):
    """(dialog name, dialog data) for every speak in the capture."""
    names = _effect_names("speak")
    out = []
    for message in messages:
        if message.msg_type not in names:
            continue
        meta = message.data.get("meta") or {}
        out.append((meta.get("dialog"), meta.get("data") or {}))
    return out


def _value_problem(row, messages):
    """Why the spoken answer is wrong, or None when it is right."""
    spoken = _speak_effects(messages)
    if not spoken:
        return "the skill spoke nothing"
    reports = [(name, data) for name, data in spoken if name in REPORT_DIALOGS]
    if not reports:
        return ("the skill spoke no colour report, only "
                f"{sorted({name for name, _ in spoken})!r}")
    wanted = _expected_rgb(row["utterance"])
    if wanted is None:
        # A named-colour row: the palette name is the skill's to choose, so
        # the check is that it named one and gave its value, not which.
        for name, data in reports:
            if str(data.get("color_name") or "").strip() and _spoken_rgb(data):
                return None
        return (f"no report carried a colour name and its value, got "
                f"{reports!r}")
    for _, data in reports:
        if _spoken_rgb(data) == wanted:
            return None
    return (f"expected the colour {wanted!r}, and the reports carried "
            f"{[_spoken_rgb(data) for _, data in reports]!r}")


# Rows that a known, filed skill defect makes red. Each value names the task
# that tracks the fix; the row turns green again on its own once the fix
# lands: the xfail is strict, so a row that starts passing FAILS and says
# so, which is the signal to delete its entry here.
#
# T-4958: handle_request_color_by_rgb speaks
# report_color_by_rgb_name_not_known with red_value, green_value and
# blue_value, and every locale writes that dialog with a {hex_code} slot.
# The render raises KeyError and the user hears skill.error. Every non-en-US
# RGB row uses 52 152 219, which no locale names, so every one of them takes
# that branch. The en-US rows use named triples and take the working branch.
KNOWN_BUGS = {
    # T-5569: ovos_spec_tools.normalize_for_match strips combining marks, so
    # padacioso hands the skill "rod" for "röd" and the Swedish colour lookup
    # returns nothing. da-DK "rød" passes in the same run, because o-slash is
    # its own letter and not o plus a combining mark, which is the control
    # that isolates the mechanism.
    ('sv-SE', 'vilken färg är röd'): "T-5569",
    ('sv-SE', 'visa mig färgen röd'): "T-5569",
    ('sv-SE', 'ändra färgen till röd'): "T-5569",
    ('sv-SE', 'berätta om färgen röd'): "T-5569",
    ('ca-ES', 'Quin color té un valor RGB de 52 152 219'):
        "T-4958",
    ('da-DK', 'hvilken farve har en RGB-værdi på 52 152 219'):
        "T-4958",
    ('da-DK', 'hvilken farve er RGB-værdien 52 152 219'):
        "T-4958",
    ('de-DE', 'welche Farbe hat einen RGB-Wert von 52 152 219'):
        "T-4958",
    ('es-ES', '¿Qué color tiene un valor RGB de 52 152 219'):
        "T-4958",
    ('eu-ES', 'zein koloretakoa da 52 152 219 RGB balioa duena'):
        "T-4958",
    ('eu-ES', 'zein kolore da RGB balioa 52 152 219'):
        "T-4958",
    ('fr-FR', 'quelle couleur a une valeur RVB de 52 152 219'):
        "T-4958",
    ('gl-ES', 'que cor ten un valor RGB de 52 152 219'):
        "T-4958",
    ('gl-ES', 'que cor é o valor RGB 52 152 219'):
        "T-4958",
    ('it-IT', 'A che colore corrisponde il valore R G B 52 152 219'):
        "T-4958",
    ('nl-NL', 'welke kleur heeft een RGB waarde van 52 152 219'):
        "T-4958",
    ('nl-NL', 'welke kleur is de RGB waarde 52 152 219'):
        "T-4958",
    ('pt-BR', 'qual cor tem um valor RGB de 52 152 219'):
        "T-4958",
    ('pt-PT', 'qual cor tem um valor RGB de 52 152 219'):
        "T-4958",
    ('sv-SE', 'vilken färg har ett RGB värde på 52 152 219'):
        "T-4958",
    ('sv-SE', 'vilken färg är det RGB värdet 52 152 219'):
        "T-4958",
}

def _marks(row):
    """A strict xfail for a row a filed defect makes red.

    An imperative ``pytest.xfail()`` inside the test can never be strict:
    it is only reached once the row has already failed, so a row that
    starts passing simply stops calling it and reports green. The entry
    then sits in KNOWN_BUGS forever and nothing says the defect is fixed.

    A marker is evaluated whichever way the row goes, so ``strict=True``
    turns an unexpected PASS into a failure that names the row. That is the
    signal to delete its KNOWN_BUGS entry, and it is the only thing that
    stops this table rotting.
    """
    task = KNOWN_BUGS.get((row["lang"], row["utterance"]))
    if task is None:
        return ()
    return (pytest.mark.xfail(strict=True, reason=f"known-bug: {task}"),)


_PARAMS = [
    pytest.param(row["lang"], row, id=_golden_id(row), marks=_marks(row))
    for row in ALL_ROWS
]


@pytest.mark.timeout(300)
@pytest.mark.parametrize("minicroft,row", _PARAMS, indirect=["minicroft"])
def test_golden_utterance_multilang(minicroft, row):
    candidates = _candidates(SKILL_ID, row["intent_label"])
    messages = _messages(minicroft, row["utterance"], row["lang"],
                         f"golden-{_golden_id(row)}")
    types = [m.msg_type for m in messages]
    matched = any(t in candidates for t in types)
    missing = [name for name in row.get("expected_messages", [])
               if not (_effect_names(name) & set(types))]
    errored = ERROR_MSG in types
    wrong_value = _value_problem(row, messages)
    assert matched, (
        f"[{row['lang']}] {row['utterance']!r}: expected one of {sorted(candidates)!r}, got {types!r}"
    )
    assert not errored, (
        f"[{row['lang']}] {row['utterance']!r}: the handler raised, got {types!r}"
    )
    assert not missing, (
        f"[{row['lang']}] {row['utterance']!r}: no effect for {missing!r}, got {types!r}"
    )
    assert not wrong_value, (
        f"[{row['lang']}] {row['utterance']!r}: {wrong_value}"
    )
