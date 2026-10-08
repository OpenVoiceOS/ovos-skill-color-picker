"""Golden-utterance end-to-end coverage for every locale ovos-skill-color-picker ships.

Every ``golden_utterances_<lang>.jsonl`` file in this directory is loaded, and
every row in it runs, including rows marked ``needs_manual`` (rows no native
speaker has vouched for yet still have to route to the intent they name).

Booting one shared MiniCroft with every locale as a secondary language hits an
open ovoscope harness defect in ``get_minicroft``'s secondary-lang path, so this
suite boots one MiniCroft per locale and tears it down before the next locale.
Rows are grouped by locale so each MiniCroft boots once. Each row is checked
against the trained padacioso container for its locale
(``container.calc_intent``), which names the matched intent as
``<skill_id>:<intent file base name>``.

The corpus keys this skill as ``ovos-skill-color-picker.openvoiceos``; the
runtime ``opm.skill`` id is ``ovos-skill-color-picker.krisgesling``, and the
assertion uses the runtime id.
"""
import json
from pathlib import Path

import pytest
from ovoscope import get_minicroft

SKILL_ID = "ovos-skill-color-picker.krisgesling"

END2END_DIR = Path(__file__).parent

LANGS = sorted(p.stem.split("golden_utterances_", 1)[1]
               for p in END2END_DIR.glob("golden_utterances_*.jsonl"))
assert LANGS, "no golden_utterances_<lang>.jsonl files found"


def _load_rows(lang):
    path = END2END_DIR / f"golden_utterances_{lang}.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    assert rows, f"{lang}: no golden rows"
    for row in rows:
        assert row["lang"] == lang, f"{path.name}: row for {row['lang']!r}"
    return rows


def _golden_id(row):
    return f"{row['lang']}-{row['intent_label']}-{row['utterance']}"


GOLDEN_ROWS = [pytest.param(row, id=_golden_id(row))
               for lang in LANGS for row in _load_rows(lang)]


@pytest.fixture(scope="module")
def minicroft_factory():
    cache = {"lang": None, "mc": None}

    def _get(lang):
        if cache["lang"] != lang:
            if cache["mc"] is not None:
                cache["mc"].stop()
            cache["mc"] = get_minicroft([SKILL_ID], max_wait=150, lang=lang)
            cache["lang"] = lang
        return cache["mc"]

    yield _get
    if cache["mc"] is not None:
        cache["mc"].stop()


@pytest.mark.timeout(300)
@pytest.mark.parametrize("row", GOLDEN_ROWS, ids=_golden_id)
def test_golden_utterance_multilang(minicroft_factory, row):
    lang = row["lang"]
    mc = minicroft_factory(lang)
    container = mc.intents.pipeline_plugins["ovos-padacioso-pipeline-plugin"].containers[lang]
    match = container.calc_intent(row["utterance"])
    matched_name = match["name"] if match else None
    expected = f"{SKILL_ID}:{row['intent_label'].removesuffix('.intent')}"
    assert matched_name == expected, (
        f"[{lang}] {row['utterance']!r}: expected {expected!r}, got {matched_name!r}"
    )


def test_every_shipping_locale_has_a_golden_file():
    golden = {p.stem.split("_", 2)[2]
              for p in END2END_DIR.glob("golden_utterances_*.jsonl")}
    locale_root = END2END_DIR.parent.parent / "locale"
    shipping = {d.name for d in locale_root.iterdir()
                if d.is_dir() and any(d.rglob("*.intent"))}
    assert golden == shipping, (
        f"golden files {sorted(golden ^ shipping)} differ from shipping locales"
    )
