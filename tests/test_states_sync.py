"""config/states.json and the BANDS/STATES blocks of the playback HTML must agree."""
import json
import re

from src.config import ROOT

HTML = (ROOT / "eeg_zustaende_playback.html").read_text(encoding="utf-8")
DEFINITIONS = json.loads((ROOT / "config" / "states.json").read_text(encoding="utf-8"))


def _block(name):
    start = HTML.index(f"const {name} =")
    end = HTML.index("\n};" if name == "BANDS" else "\n];", start)
    return HTML[start:end]


def test_bands_match():
    html = {key: (label, rng, color) for key, label, rng, color in re.findall(
        r'(\w+):\s*\{\s*label:"([^"]+)",\s*range:"([^"]+)",\s*color:"([^"]+)"', _block("BANDS"))}
    json_bands = {key: (b["label"], b["range"], b["color"]) for key, b in DEFINITIONS["bands"].items()}
    assert html == json_bands


def test_states_match():
    html, current = {}, None
    for line in _block("STATES").splitlines():
        match = re.search(r'\bid:"([a-z_]+)"', line)
        if match:
            current = match.group(1); html[current] = set()
        for el, band, trend in re.findall(r'el:"(\w+)",\s*band:"(\w+)",\s*trend:"(\w+)"', line):
            html[current].add((el, band, trend))
    json_states = {s["id"]: {(m["el"], m["band"], m["trend"]) for m in s["mappings"]}
                   for s in DEFINITIONS["states"]}
    assert html == json_states


def test_every_mapping_uses_a_defined_band():
    bands = set(DEFINITIONS["bands"])
    assert all(m["band"] in bands for s in DEFINITIONS["states"] for m in s["mappings"])
