"""Validated, deterministic project state for the Flock melodic layer."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

FLOCK_RENDERER_VERSION = "flock-1"
_CATALOG_PATH = Path(__file__).with_name("birds.json")
_catalog_cache: dict[str, Any] | None = None
_bird_map_cache: dict[str, dict[str, Any]] | None = None
_KEYS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_FLATS = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}
_SCALES = {"minor", "dorian", "major", "mixolydian", "minor_pent", "phrygian"}
_WEATHER = {"clear", "dust", "rain", "wind"}
_ROLES = ("bass", "keys", "pad", "lead", "arp", "call")
_FIELDS = {"key", "scale", "progression", "weather", "perches", "seen", "unlocked", "voices"}


def _ensure_catalog() -> dict[str, Any]:
    global _catalog_cache
    if _catalog_cache is None:
        data = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
        expected = {"scales", "chordTables", "registers", "birds", "corvus", "templates", "combos", "comboSongs", "secretUnlock"}
        if not isinstance(data, dict) or set(data) != expected:
            raise ValueError("flock catalog has an invalid exported shape")
        data["secretUnlock"]["seenRequired"] = [bird["id"] for bird in data["birds"]]
        _catalog_cache = data
    return _catalog_cache


def load_catalog() -> dict[str, Any]:
    """Load the shipped JSON catalog and return a mutation-isolated copy."""
    return copy.deepcopy(_ensure_catalog())


def _catalog() -> dict[str, Any]:
    """Read-only access to the cached catalog; callers must not mutate it."""
    return _ensure_catalog()


def _ordinary_ids() -> set[str]:
    return {bird["id"] for bird in _catalog()["birds"]}


def _bird_map() -> dict[str, dict[str, Any]]:
    global _bird_map_cache
    if _bird_map_cache is None:
        data = _catalog()
        _bird_map_cache = {bird["id"]: bird for bird in [*data["birds"], data["corvus"]]}
    return _bird_map_cache


def default_flock() -> dict[str, Any]:
    return {"key": "D", "scale": "dorian", "progression": ["i", "IV", "VII", "III"],
            "weather": "clear", "perches": [None] * 6, "seen": [], "unlocked": []}


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _normalize_key(value: Any) -> str:
    value = _string(value, "key")
    value = _FLATS.get(value, value)
    if value not in _KEYS:
        raise ValueError("key must be a supported sharp/flat spelling from C through B")
    return value


def _known_combo_ids() -> set[str]:
    return {item["id"] for item in _catalog()["combos"]}


def validate_flock(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("flock must be an object")
    if set(value) - _FIELDS:
        raise ValueError(f"flock has unknown fields: {', '.join(sorted(set(value) - _FIELDS))}")
    if not (_FIELDS - {"voices"}) <= set(value):
        raise ValueError("flock is missing required fields")
    key = _normalize_key(value["key"])
    scale = _string(value["scale"], "scale")
    if scale not in _SCALES:
        raise ValueError("scale must be one of the six catalog scales")
    progression = value["progression"]
    if not isinstance(progression, list) or not 1 <= len(progression) <= 8:
        raise ValueError("progression must contain 1 to 8 Roman-numeral chords")
    roman = _catalog()["chordTables"]["romanDegrees"]
    for chord in progression:
        if not isinstance(chord, str) or chord not in roman:
            raise ValueError(f"unrecognized Roman-numeral chord: {chord!r}")
    weather = _string(value["weather"], "weather")
    if weather not in _WEATHER:
        raise ValueError("weather must be clear, dust, rain, or wind")
    perches = value["perches"]
    if not isinstance(perches, list) or len(perches) not in (6, 7):
        raise ValueError("perches must contain exactly 6 or 7 slots")
    ordinary = _ordinary_ids()
    birds = _bird_map()
    seen_roles: dict[str, int] = {}
    perched: set[str] = set()
    normalized_perches: list[dict[str, Any] | None] = []
    d_singers: list[str] = []
    for slot, perch in enumerate(perches):
        if perch is None:
            normalized_perches.append(None)
            continue
        if not isinstance(perch, dict) or set(perch) - {"bird", "song", "mute", "solo", "gain_db", "pan"}:
            raise ValueError(f"perches[{slot}] must be null or a perch object with known fields")
        if "bird" not in perch:
            raise ValueError(f"perches[{slot}].bird is required")
        bird_id = _string(perch["bird"], f"perches[{slot}].bird")
        if bird_id not in birds:
            raise ValueError(f"unknown bird: {bird_id}")
        if bird_id in perched:
            raise ValueError(f"bird {bird_id} cannot occupy more than one slot")
        perched.add(bird_id)
        bird = birds[bird_id]
        if slot == 6:
            if bird_id != "corvus":
                raise ValueError("only Corvus may occupy slot 6")
        elif bird_id == "corvus":
            raise ValueError("Corvus may only occupy slot 6")
        else:
            role = bird["role"]
            seen_roles[role] = seen_roles.get(role, 0) + 1
            if seen_roles[role] > 2:
                raise ValueError(f"at most two birds may occupy the {role} role")
        song = perch.get("song", "A")
        if song not in ("A", "B", "C", "D") or not isinstance(song, str):
            raise ValueError(f"perches[{slot}].song must be A, B, C, or D")
        if bird_id == "corvus" and song != "A":
            raise ValueError("Corvus sings only song A")
        if song == "D":
            d_singers.append(bird_id)
        mute, solo = perch.get("mute", False), perch.get("solo", False)
        if not isinstance(mute, bool) or not isinstance(solo, bool):
            raise ValueError(f"perches[{slot}].mute and solo must be booleans")
        normalized = {"bird": bird_id, "song": song, "mute": mute, "solo": solo}
        if "gain_db" in perch:
            gain_db = perch["gain_db"]
            if isinstance(gain_db, bool) or not isinstance(gain_db, (int, float)) or not -24 <= gain_db <= 12:
                raise ValueError(f"perches[{slot}].gain_db must be a number from -24 to 12")
            normalized["gain_db"] = gain_db
        if "pan" in perch:
            pan = perch["pan"]
            if isinstance(pan, bool) or not isinstance(pan, (int, float)) or not -1 <= pan <= 1:
                raise ValueError(f"perches[{slot}].pan must be a number from -1 to 1")
            normalized["pan"] = pan
        normalized_perches.append(normalized)
    if len(normalized_perches) == 7 and normalized_perches[6] is None:
        normalized_perches.pop()
    if "corvus" in perched:
        required = set(_catalog()["secretUnlock"]["seenRequired"])
        if not required <= set(value["seen"] if isinstance(value["seen"], list) else []):
            raise ValueError("Corvus requires all ordinary birds to have been seen")
    seen = value["seen"]
    if not isinstance(seen, list) or any(not isinstance(item, str) or item not in ordinary for item in seen) or len(seen) != len(set(seen)):
        raise ValueError("seen must be a unique list of known ordinary bird IDs")
    unlocked = value["unlocked"]
    combos = _known_combo_ids()
    if not isinstance(unlocked, list) or any(not isinstance(item, str) or item not in combos for item in unlocked) or len(unlocked) != len(set(unlocked)):
        raise ValueError("unlocked must be a unique list of known combo IDs")
    voices = value.get("voices", "samples")
    if voices not in {"samples", "synth"}:
        raise ValueError("voices must be samples or synth")
    normalized = {"key": key, "scale": scale, "progression": list(progression), "weather": weather,
                 "perches": normalized_perches, "seen": list(seen), "unlocked": list(unlocked)}
    if "voices" in value:
        normalized["voices"] = voices
    for bird_id in d_singers:
        if not _song_d_allowed(normalized, bird_id):
            raise ValueError(f"song D is not unlocked for {bird_id} by an active combo")
    return normalized


def _active_unvalidated(flock: dict[str, Any]) -> list[str]:
    perches = flock["perches"]
    entries = [(index, perch) for index, perch in enumerate(perches) if perch and not perch.get("mute", False)]
    soloed = [item for item in entries if item[1].get("solo", False)]
    if soloed:
        entries = soloed
    ids = {perch["bird"] for _, perch in entries}
    roles = {_bird_map()[bird]["role"] for bird in ids}
    data = _catalog()
    family = data["scales"][flock["scale"]]["family"]
    result = []
    for combo in data["combos"]:
        req = combo["requires"]
        if not set(req.get("birds", [])) <= ids or not set(req.get("roles", [])) <= roles:
            continue
        if req.get("scale_family") and req["scale_family"] != family:
            continue
        if req.get("weather") and req["weather"] != flock["weather"]:
            continue
        result.append(combo["id"])
    return result


def active_combos_unchecked(flock: dict[str, Any]) -> list[str]:
    return _active_unvalidated(flock)


def active_combos(flock: Any) -> list[str]:
    return _active_unvalidated(validate_flock(flock))


def _song_d_allowed(value: dict[str, Any], bird_id: str) -> bool:
    for combo in _catalog()["combos"]:
        if combo["id"] in _active_unvalidated(value) and combo.get("bonus", {}).get("song_overrides", {}).get(bird_id) == "D":
            return True
    return False


def _discover(flock: dict[str, Any], previously_seen: set[str]) -> None:
    ordinary = _ordinary_ids()
    seen = set(flock["seen"])
    seen.update(perch["bird"] for perch in flock["perches"] if perch and perch["bird"] in ordinary)
    flock["seen"] = sorted(seen)
    unlocked = set(flock["unlocked"])
    unlocked.update(_active_unvalidated(flock))
    flock["unlocked"] = sorted(unlocked)
    required = set(_catalog()["secretUnlock"]["seenRequired"])
    if required <= seen and not required <= previously_seen and len(flock["perches"]) == 6:
        flock["perches"].append({"bird": "corvus", "song": "A", "mute": False, "solo": False})


def apply_flock_edit(flock_or_None: Any, args: Any) -> dict[str, Any]:
    flock = default_flock() if flock_or_None is None else validate_flock(flock_or_None)
    previously_seen = set(flock["seen"])
    if not isinstance(args, dict) or not isinstance(args.get("action"), str):
        raise ValueError("flock edit requires an action")
    result = copy.deepcopy(flock)
    action = args["action"]
    schemas = {"template": {"action", "template"}, "perch": {"action", "bird", "slot", "song"},
               "unperch": {"action", "bird", "slot"}, "song": {"action", "bird", "song"},
               "mute": {"action", "bird", "on"}, "solo": {"action", "bird", "on"},
               "mix": {"action", "bird", "gain_db", "pan"},
               "harmony": {"action", "key", "scale", "progression"}, "weather": {"action", "weather"}}
    if action not in schemas:
        raise ValueError(f"unknown flock action: {action}")
    if set(args) - schemas[action]:
        raise ValueError(f"unknown arguments for flock action {action}")
    perches = result["perches"]
    if action == "template":
        if set(args) != {"action", "template"}:
            raise ValueError("template action requires only template")
        name = _string(args["template"], "template")
        template = next((item for item in _catalog()["templates"] if name in (item["id"], item["name"])), None)
        if template is None:
            raise ValueError(f"unknown flock template: {name}")
        by_id = {bird["id"]: bird for bird in _catalog()["birds"]}
        landing = sorted(template["birds"], key=lambda item: (_ROLES.index(by_id[item["bird"]]["role"]), item["bird"]))
        new_perches: list[dict[str, Any] | None] = [None] * 6
        for slot, item in enumerate(landing):
            new_perches[slot] = {"bird": item["bird"], "song": item["song"], "mute": False, "solo": False}
        result.update({key: copy.deepcopy(template[key]) for key in ("key", "scale", "progression", "weather")})
        result["perches"] = new_perches + ([copy.deepcopy(perches[6])] if len(perches) == 7 else [])
    elif action in {"harmony", "weather"}:
        if action == "harmony":
            if set(args) == {"action"}:
                raise ValueError("harmony requires at least one harmony field")
            for field in ("key", "scale", "progression"):
                if field in args:
                    result[field] = args[field]
        else:
            if set(args) != {"action", "weather"}:
                raise ValueError("weather action requires weather")
            result["weather"] = args["weather"]
    else:
        bird_id = _string(args["bird"], "bird") if "bird" in args else None
        slot_index = next((i for i, p in enumerate(perches) if p and p["bird"] == bird_id), None)
        if action == "perch":
            if bird_id not in _bird_map():
                raise ValueError(f"unknown bird: {bird_id}")
            song = args.get("song", "A")
            if song not in {"A", "B", "C", "D"}:
                raise ValueError("song must be A, B, C, or D")
            slot = args.get("slot")
            if slot is None:
                if slot_index is not None:
                    slot = slot_index
                elif bird_id == "corvus" and len(perches) == 6:
                    slot = 6
                else:
                    slot = next((i for i in range(6) if perches[i] is None), None)
            appends_corvus = bird_id == "corvus" and slot == 6 and len(perches) == 6
            if isinstance(slot, bool) or not isinstance(slot, int) or not (
                    0 <= slot < len(perches) or appends_corvus):
                raise ValueError("slot must identify an available zero-based perch")
            if bird_id == "corvus" and slot != 6 or bird_id != "corvus" and slot == 6:
                raise ValueError("Corvus may only occupy slot 6")
            if slot < len(perches) and perches[slot] and perches[slot]["bird"] != bird_id:
                raise ValueError(f"slot {slot} is occupied; unperch its bird first")
            if appends_corvus:
                perches.append(None)
            if slot_index is not None:
                prior = perches[slot_index]
                if slot_index != slot:
                    perches[slot_index] = None
                moved = {"bird": bird_id, "song": song if "song" in args else prior["song"],
                         "mute": prior["mute"], "solo": prior["solo"]}
                for key in ("gain_db", "pan"):
                    if key in prior:
                        moved[key] = prior[key]
                perches[slot] = moved
            else:
                perches[slot] = {"bird": bird_id, "song": song, "mute": False, "solo": False}
        elif action == "unperch":
            if ("bird" in args) == ("slot" in args):
                raise ValueError("unperch requires exactly one of bird or slot")
            if "slot" in args:
                idx = args["slot"]
                if isinstance(idx, bool) or not isinstance(idx, int) or not 0 <= idx < len(perches):
                    raise ValueError("slot must be a valid zero-based perch")
            else:
                if slot_index is None:
                    raise ValueError(f"bird is not perched: {bird_id}")
                idx = slot_index
            perches[idx] = None
        else:
            if slot_index is None:
                raise ValueError(f"bird is not perched: {bird_id}")
            if action == "song":
                song = args.get("song")
                if song not in {"A", "B", "C", "D"}:
                    raise ValueError("song must be A, B, C, or D")
                perches[slot_index]["song"] = song
            elif action == "mix":
                if "gain_db" not in args and "pan" not in args:
                    raise ValueError("mix requires gain_db, pan, or both")
                if "gain_db" in args:
                    perches[slot_index]["gain_db"] = args["gain_db"]
                if "pan" in args:
                    perches[slot_index]["pan"] = args["pan"]
            else:
                if not isinstance(args.get("on"), bool):
                    raise ValueError("on must be a boolean")
                perches[slot_index][action] = args["on"]
    # Explicit D selections must be valid. Other edits can break a D-granting
    # combo, in which case the hidden song falls back to A automatically.
    if action == "song" or action == "perch" and args.get("song") == "D":
        result = validate_flock(result)
    else:
        d_singers = {p["bird"] for p in result["perches"] if p and p["song"] == "D"}
        for p in result["perches"]:
            if p and p["song"] == "D":
                p["song"] = "A"
        result = validate_flock(result)
        for p in result["perches"]:
            if p and p["bird"] in d_singers and _song_d_allowed(result, p["bird"]):
                p["song"] = "D"
    _discover(result, previously_seen)
    return validate_flock(result)


def flock_diffs(before: Any, after: Any, change: str | None = None) -> list[dict[str, Any]]:
    old = default_flock() if before is None else validate_flock(before)
    # An absent flock (undo removing it) compares against the empty default wire.
    new = default_flock() if after is None else validate_flock(after)
    diffs: list[dict[str, Any]] = []
    if change == "template":
        old_p, new_p = old["perches"], new["perches"]
        by_id = _bird_map()
        order = {role: i for i, role in enumerate(_ROLES)}
        indexes = [i for i in range(max(len(old_p), len(new_p)))
                   if (old_p[i] if i < len(old_p) else None) != (new_p[i] if i < len(new_p) else None)]
        def landing_role(index: int) -> int:
            perch = new_p[index] if index < len(new_p) and new_p[index] is not None else old_p[index]
            return order.get(by_id[perch["bird"]]["role"], 99)
        indexes.sort(key=lambda i: (landing_role(i), i))
        for i in indexes:
            diffs.append({"field": "flock", "change": "template", "slot": i,
                          "bird": (new_p[i] if i < len(new_p) and new_p[i] is not None else old_p[i])["bird"],
                          "from": copy.deepcopy(old_p[i] if i < len(old_p) else None),
                          "to": copy.deepcopy(new_p[i] if i < len(new_p) else None)})
    else:
        for i in range(max(len(old["perches"]), len(new["perches"]))):
            a = old["perches"][i] if i < len(old["perches"]) else None
            b = new["perches"][i] if i < len(new["perches"]) else None
            if a == b:
                continue
            if a is None:
                inferred = ["perch"]
            elif b is None:
                inferred = ["unperch"]
            elif a["bird"] == b["bird"]:
                changed = [field for field in ("song", "mute", "solo", "gain_db", "pan") if a.get(field) != b.get(field)]
                inferred = ["mix"] if changed and set(changed) <= {"gain_db", "pan"} else changed
            else:
                inferred = ["perch"]
            for field in inferred or ["perch"]:
                diffs.append({"field": "flock", "change": field, "slot": i,
                              "bird": (b or a)["bird"], "from": copy.deepcopy(a), "to": copy.deepcopy(b)})
    if old["key"] != new["key"] or old["scale"] != new["scale"] or old["progression"] != new["progression"]:
        diffs.append({"field": "flock", "change": "harmony", "from": {k: copy.deepcopy(old[k]) for k in ("key", "scale", "progression")},
                      "to": {k: copy.deepcopy(new[k]) for k in ("key", "scale", "progression")}})
    if old["weather"] != new["weather"]:
        diffs.append({"field": "flock", "change": "weather", "from": old["weather"], "to": new["weather"]})
    return diffs


def state_lines(flock: Any) -> list[str]:
    value = validate_flock(flock)
    labels = {bird["id"]: bird["name"] for bird in [*_catalog()["birds"], _catalog()["corvus"]]}
    slots = []
    for index, perch in enumerate(value["perches"]):
        if perch is None:
            label = "—"
        else:
            label = f"{labels[perch['bird']]} {perch['song']}" + ("·muted" if perch["mute"] else "") + ("·solo" if perch["solo"] else "")
            if perch.get("gain_db"):
                label += f"·{perch['gain_db']:+g}dB"
            if perch.get("pan"):
                label += f"·pan{perch['pan']:+g}"
        slots.append(f"[{index + 1} {label}]")
    progression = "-".join(value["progression"])
    lines = [f"Wire ({value['key']} {value['scale']}, {progression}, {value['weather']}): " + " ".join(slots)]
    found = set(value["unlocked"])
    undiscovered = [combo for combo in _catalog()["combos"] if combo["id"] not in found]
    audible = [p for p in value["perches"] if p and not p["mute"]]
    soloed = [p for p in audible if p["solo"]]
    if soloed:
        audible = soloed
    audible_ids = {p["bird"] for p in audible}
    bird_roles = {bird["id"]: bird["role"] for bird in _catalog()["birds"]}
    audible_roles = {bird_roles[bird] for bird in audible_ids if bird in bird_roles}
    family = _catalog()["scales"][value["scale"]]["family"]
    def distance(combo: dict[str, Any]) -> int:
        requirements = combo["requires"]
        missing = len(set(requirements.get("birds", [])) - audible_ids)
        missing += len(set(requirements.get("roles", [])) - audible_roles)
        if requirements.get("scale_family") and requirements["scale_family"] != family:
            missing += 1
        if requirements.get("weather") and requirements["weather"] != value["weather"]:
            missing += 1
        return missing
    hint = next((combo["riddle"] for combo in undiscovered if distance(combo) == 1), None)
    summary = ", ".join(combo["name"] for combo in _catalog()["combos"] if combo["id"] in found) or "none"
    lines.append(f"Murmurations: {summary}; {len(undiscovered)} undiscovered." + (f' Hint: "{hint}"' if hint else ""))
    return lines


def audio_projection(flock: Any) -> dict[str, Any]:
    value = validate_flock(flock)
    catalog_bytes = json.dumps(_catalog(), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    fingerprint = hashlib.sha256(catalog_bytes).hexdigest()
    perches = copy.deepcopy(value["perches"])
    for combo in _catalog()["combos"]:
        if combo["id"] not in _active_unvalidated(value):
            continue
        for bird, song in combo.get("bonus", {}).get("song_overrides", {}).items():
            for perch in perches:
                if perch and perch["bird"] == bird and not perch["mute"] and perch["song"] != "D":
                    perch["song"] = song
    audio = {key: copy.deepcopy(value[key]) for key in ("key", "scale", "progression", "weather")}
    audio["perches"] = perches
    # Discovery metadata is intentionally excluded from render identity.
    audio["catalog_fingerprint"] = fingerprint
    audio["renderer_version"] = FLOCK_RENDERER_VERSION
    return audio
