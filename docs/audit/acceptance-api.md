# Acceptance API

Sol implements this. Grok's tests in `tests/acceptance/` call it and nothing else. They stay red until these modules exist. The Hermes wrappers in `__init__.py` call `rookery.tools` and register these eight names: `rookery_new`, `rookery_steps`, `rookery_track`, `rookery_mix`, `rookery_render`, `rookery_state`, `rookery_undo`, `rookery_kits`.

`data_dir` is a directory the test creates. Projects live at `data_dir/projects/<name>/project.json`. History snapshots live at `data_dir/projects/<name>/history/NNNN.json`. `rev` is a monotonic int per project, starting at 1 on create. Every successful write, including undo, bumps it. A rejected write raises and leaves the file and `rev` unchanged.

## rookery.project

- `ProjectError(ValueError)`. The message is the text the model sees. It is never empty.
- `validate(project) -> None`
- `load(project_dir) -> dict`
- `save(project, project_dir) -> int` validates, snapshots the previous file, writes, returns the new rev.
- `rev(project_dir) -> int`
- `undo(project_dir, steps=1) -> dict` returns the restored project.
- `canonical_json(project) -> str`. Sorted keys, compact separators, `history` and `rev` omitted. A short `steps` string may stay short on disk.

`bars` is 4 or 8. `steps_per_bar` is 16. `swing` is 0 through 1 inclusive. `bpm` is a positive number. Drum `steps` use only `x` and `.`. A short pattern repeats to `bars * 16`. `schema` is `rookery.project/1`.

## rookery.render

- `SR = 44100`
- `RENDERER_VERSION: str`
- `render(project) -> numpy.ndarray` float32, shape `(samples, 2)`.
- `samples = round(bars * 4 * 60 / bpm * SR)` using Python `round`. Swing does not change the count. An empty `tracks` list renders silence of that length.
- `content_hash(project) -> str` is the sha256 hex of `canonical_json(project)` plus `RENDERER_VERSION`.
- `write_wav(path, audio, sr=SR) -> None` writes 24-bit PCM stereo at 44100 Hz.

Known lengths: 90 bpm and 4 bars is 470400 frames. 93 bpm and 8 bars is 910452 frames.

## rookery.checks

`evaluate(audio, sr, project, *, this_hash, other_hash) -> dict`

Six keys: `length_exact`, `no_clipping`, `loudness`, `seam_click`, `not_silent`, `deterministic`. Each value is `{"pass": bool, "value": number or str}`.

Pass rules from HANDOFF §2.3. `no_clipping` is true peak at or under -1.0 dBTP with 4x oversampling. `loudness` is integrated LUFS within -14 ±1. `not_silent` is RMS above -50 dBFS. `deterministic` passes when the two hashes match.

## rookery.tools

Each edit returns `{"project": dict, "rev": int, "diff": list}`. A steps diff has `field == "steps"` and `steps` as the list of step indexes that changed.

- `new(data_dir, name, bpm, bars=4, swing=0.0, seed=1337, genre=None) -> dict`
- `steps(data_dir, name, track, steps, velocity=None) -> dict`
- `track(data_dir, name, action, id, **fields) -> dict` with `action` in `add`, `remove`, `set`. `add` and `set` accept `notes` (list of `{step, len, pitch}`) and `slices` (int) so bass and sample tracks stay on this tool.
- `mix(data_dir, name, target, fx) -> dict`
- `render(data_dir, name) -> {"path", "hash", "report", "rev"}`. `path` ends with `{hash}.wav`. `report` uses the same six keys. Same project, same seed, same version, same bytes, including across processes.
- `state(data_dir, name) -> str` includes the track id and the step pattern.
- `undo(data_dir, name, steps=1) -> {"project", "rev", "diff"}`
- `kits(data_dir) -> {"factory": [names], "user": [...], "corvus": {"found": bool}}`

Factory names: `kick_boom`, `808`, `snare_crack`, `clap`, `hat_closed`, `hat_open`, `rim`, `perc`.

Sol agreed on the board (2026-11-08 01:54): `notes` and `slices` ride on `rookery_track` add/set. There is no ninth tool.
