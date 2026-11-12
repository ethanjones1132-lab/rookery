# Sample sources for Rookery: measured, licensed, pinned

**Status:** research, 2026-11-10. **Scope:** replace or supplement the current `rookery_samples` path (Openverse search + Freesound preview fetch) so an agent inside Rookery gets consistently high-quality drums, melodic loops, textures and one-shots that are safe to publish.
**Read first:** `rookery/samples.py`, `rookery/sampling.py`, the sampling section of `skills/rookery/SKILL.md`, `docs/design/research/sounds.md`, and the README **Disclosure** section.
**Code changed:** only `tools/sample_quality.py` (offline measurement; no audio, no network). No plugin code was changed.

---

## 0. The short answer

There is **no keyless, CC0, commercial-pack-quality *loop* library** that Rookery can point at today. The measured evidence says:

- The Freesound material behind Openverse is often metrically right: two one-bar loops measured **exactly 1.000 bars** at their stated 130 and 128 BPM, and an 8-bar loop measured **exactly 8.000 bars** at 95 BPM. But every file Openverse serves is a **191–200 kbps MP3 preview**, with a −60 dB bandwidth of **8.5–18.8 kHz**. They fail a lossless gate before any musical judgement.
- The free *instrument* libraries are genuinely good and genuinely CC0: Karoryfer's free drum kits and VCSL (which includes much of VSCO 2 CE) measured **44.1 kHz, 16/24-bit, 22 kHz bandwidth, −85 to −98 dBFS noise floors, zero clipping**. But they are **one-shots**, not loops.
- The user's own licensed library is the only source that can already contain commercial loops at commercial quality, with no redistribution and no new licence. Rookery just cannot see it yet.

So the top recommendation is **local-first**:

1. Add a `rookery_library` tool that indexes the user's own sample folders (BPM, key, type, measured quality) and imports a chosen file into the kit with a SHA-256 pin.
2. Give every install a small, pinned **CC0 one-shot kit** (Karoryfer + VCSL) so an agent with no local library still gets real drums and percussion.
3. Change `rookery_samples` so it never imports a lossy preview. Keep Openverse search as discovery only.

The runner-up is a **first-party "Rookery Sessions" pack**: 12 loops + 24 one-shots rendered by Ethan at 48 kHz/24-bit from original patches, shipped as a pinned release asset. It is the only way to get a *consistent signature* sound for every user, but it costs authoring time and a release asset.

Freesound APIv2 "done properly" is **not worth it as the default**. The key alone cannot download originals; originals need OAuth2, which means an app registration, a browser callback, token storage and refresh, and Freesound's API terms. For the number of sounds Rookery needs, manually downloading a folder of CC0 originals and indexing it with `rookery_library` is cheaper and safer.

---

## 1. Ranked table

Ranked by overall fit for Rookery: measured quality first, then licence, then whether it can actually supply the sounds an agent asks for.

| # | Source | Quality (measured) | Licence (exact text; commercial?) | Redistribution and catalog fit | Access (key / limits) | Integration cost | Risk |
|---|---|---|---|---|---|---|---|
| 1 | **User's own licensed library** (`rookery_library`) | Not measured here (Ethan's FL Studio packs are commercial by definition). The tool would measure every file with the same gate. | User-owned licences; Rookery does not redistribute. Commercial use depends on the user's own pack licence. | Never redistributed; copied once into the local kit. Fit: **everything** — loops, one-shots, textures, the user's best sounds. | Local disk. No network, no key. | **Medium–high:** scanner, index, search, import, hash. | User may index a pack whose licence forbids sample redistribution; Rookery must not redistribute. Index is local and private. |
| 2 | **First-party "Rookery Sessions" pack** | To be rendered. Target 48 kHz/24-bit, exact bars, −14 LUFS, true peak ≤ −1 dBTP. | Ethan's own recordings/patches. Can be released CC0 or "free for music, no resale as samples". **Commercial: yes** if the provenance statement is clean. | Can ship in the repo (8 MiB budget) or as a pinned release asset. Fit: **signature loops + one-shots**, exactly the Flock aesthetic. | Release asset or repo; no key. | **High authoring**, low runtime. | Effort; hosting; must not use FL Studio stock samples or third-party loops if the output is redistributed as a pack. |
| 3 | **Karoryfer free sample libraries** (Big Rusty Drums measured) | 5/5 pass. 44.1 kHz/16-bit FLAC, 22.0 kHz BW, −86 to −91 dBFS noise floor, peak −6 to −24 dBFS, no clipping. | **CC0 1.0** — https://creativecommons.org/publicdomain/zero/1.0/legalcode. "All our free sample libraries are under a Creative Commons Zero license." **Commercial: yes, no attribution.** | CC0 allows redistribution, but the catalog rule says no third-party audio in the repo. Use a **manifest + pinned fetch**. Fit: **acoustic drum one-shots and instrument multisamples**, not loops. | Keyless. GitHub raw; pin commit + SHA-256. | **Low–medium:** manifest, fetch, hash, credits. | Repo could move; pin the commit and keep a mirror manifest. One-shots only. |
| 4 | **VCSL / VSCO 2 CE** (Versilian) | 4/4 pass. 44.1 kHz 16/24-bit WAV, 4.3–22.0 kHz BW (marimba is dark by nature), −61 to −98 dBFS noise floor, no clipping. | **CC0 1.0** — https://creativecommons.org/publicdomain/zero/1.0/legalcode. VCSL: "you can do whatever you want with these sounds (even make commercial software), no royalties, no credit, no special terms." **Commercial: yes.** | Same: manifest + pinned fetch, no audio in repo. Fit: orchestral/percussion one-shots, textures, not modern loops. | Keyless. GitHub raw; pin commit. | **Medium:** many paths with spaces; curation needed. | Large repo; quality is "lightweight library", not Splice-grade for every articulation. |
| 5 | **Salamander Grand Piano V3** | 3/3 pass. 48 kHz/24-bit FLAC, 24.0 kHz BW, −52 to −70 dBFS noise floor, no clipping. | **CC BY 3.0** — https://creativecommons.org/licenses/by/3.0/legalcode. **Commercial: yes, attribution required.** | Redistribution allowed with attribution; still better as a pinned fetch. Fit: **one piano**, not a general source. | Keyless. GitHub raw; pin commit. | **Medium:** attribution must reach the export credits. | Attribution obligation; one instrument; large files. |
| 6 | **University of Iowa MIS** | 3/3 pass. 44.1 kHz/16-bit AIFF (24/96 stereo versions exist), 22.0 kHz BW, −62 to −72 dBFS noise floor, no clipping. | **No formal licence.** Page says "may be downloaded and used for any projects, without restrictions" — a permission statement, not a licence with legal text. **Commercial: probably yes, but unverifiable.** | Do not redistribute. Pinned fetch only. Fit: piano/orchestral one-shots. | Keyless; large files; no stated rate limit. | **Medium**, but legal review needed. | Permission can be clarified or withdrawn; no licence URL; no explicit redistribution right. |
| 7 | **Freesound APIv2, original quality** | Not measured: original download needs OAuth2. Previews measured and fail. Metadata has real BPM/key/loopable descriptors. | Per-sound **CC0 1.0** — https://creativecommons.org/publicdomain/zero/1.0/legalcode. **Commercial: yes** for CC0 sounds. | CC0 allows use in published music. API terms restrict copying the database. Fit: broad loops/one-shots/textures, but quality varies. | **Key + OAuth2.** Search 60/min, 2000/day; original downloads 30/min, 500/day. | **High:** OAuth app, callback, token storage/refresh, terms. | API terms (key per app, commercial use negotiated), quality variance, metadata errors, key handling. |
| 8 | **Openverse + Freesound previews** (current) | **0/5 pass.** 44.1/48 kHz MP3 at 191–200 kbps, BW 8.5–18.8 kHz, one file clipped 34 runs, one peaked +1.95 dBFS. | Per-item **CC0** (e.g. https://creativecommons.org/publicdomain/zero/1.0/). **Commercial: yes.** | Fine legally; bad acoustically. Fit: discovery only. | Keyless: 20/min, 200/day, page size 20. | Already built. | Lossy previews are the whole problem; Openverse does not verify licences. |
| 9 | **Philharmonia Orchestra samples** | Not measured: licence rejects it before quality matters. Search results say the downloads are MP3. | **CC BY-SA 3.0** — https://creativecommons.org/licenses/by-sa/3.0/legalcode, plus "must not be sold or made available 'as is'". **Commercial: yes, but ShareAlike.** | ShareAlike may force the derivative/song under CC BY-SA; that is a risk to an exclusive commercial release. Reject. | Keyless downloads. | — | Licence trap. Reject. |
| 10 | **Sonatina Symphonic Orchestra / mixed FreePats banks** | Not measured. | Sonatina: **CC Sampling Plus 1.0**, retired and ambiguous; FreePats itself calls it "not a free license" and notes incompatible sources. FreePats banks are **per-bank** (some CC0, some CC BY). | Mixed/uncertain. Reject as a default. | Keyless. | — | Licence uncertainty. Reject unless each bank is re-verified. |
| 11 | **Local generative models** | Not run (no GPU/weights fetched). | Varies: MusicGen/AudioGen/MAGNeT **CC BY-NC 4.0** (no); Stable Audio Open **Stability AI Community License** (commercial <$1M, registration + "Powered by Stability AI", gated weights); Riffusion **CreativeML OpenRAIL-M** with "research purposes only" model card; ACE-Step 1.0 **Apache-2.0**, 1.5 **MIT**. | No third-party samples, but outputs are not a curated pack and are not guaranteed deterministic across hardware. | Model download, GPU, PyTorch. | **Very high.** | Licence/compute/quality/determinism. Reject for this plugin. |

**Rows 1–6 are the real candidates.** Rows 7–11 are included because the brief asked for them; each is rejected for a stated reason, not because it was not tried.

---

## 2. What was measured

### 2.1 Method

`tools/sample_quality.py` is offline, takes paths, and never writes audio. It uses `soundfile` to decode, `ffprobe` when present to read the container/codec, `numpy`/`scipy` for the signal metrics, `pyloudnorm` for LUFS, and `rookery.sampling.analyze` for the plugin's own BPM/key/bar estimate.

Definitions:

- **Codec / preview.** Container and codec from `ffprobe` (`mp3`, `vorbis`, `pcm_s16`, `flac`). A file is a **lossy preview** if the codec is MP3, Vorbis, Opus, AAC, etc. — regardless of bitrate.
- **Effective bandwidth.** Average spectrum of the audible frames (50 ms frames within 40 dB of the loudest frame), in dB relative to the strongest bin; the highest frequency still within **−60 dB** of that peak. This avoids measuring codec noise in a decay tail or silence.
- **Noise floor.** 10th-percentile RMS of 200 ms frames, only when the file actually contains silence (minimum frame ≤ −50 dBFS). A continuous loop has no meaningful noise floor and is reported as `None`.
- **Clipping.** Runs of ≥3 consecutive samples at |x| ≥ 0.999, plus the fraction of full-scale samples and the peak. This catches both hard clipping and MP3 decode overshoot.
- **LUFS / crest.** Integrated LUFS (EBU R128) and peak minus RMS in dB.
- **Bars.** For loops with a stated BPM: `duration / (240 / BPM)`; residual to the nearest whole bar. `analyze`'s own `bars` field is coarse (it snaps to 1/2/4/8) and is not used for the gate.
- **`analyze`.** Called with no project BPM so the tempo estimate is not biased toward the answer being tested.

The gate and its justification are in section 7.

### 2.2 Representative measurements

All numbers are from `tools/sample_quality.py` on the files listed in Appendix A.

**One-shots and instrument samples**

| File | Source | Codec / bits | kHz | Ch | BW kHz | Peak dBFS | Clip runs | Noise floor dBFS | LUFS | Crest dB | Gate |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `kick.flac` | Karoryfer Big Rusty Drums | FLAC 16 | 44.1 | 1 | 22.0 | −6.6 | 0 | −86.6 | −33.0 | 23.4 | PASS |
| `snare.flac` | Karoryfer Big Rusty Drums | FLAC 16 | 44.1 | 1 | 22.0 | −23.9 | 0 | −90.1 | −52.2 | 25.3 | PASS |
| `hihat.flac` | Karoryfer Big Rusty Drums | FLAC 16 | 44.1 | 1 | 22.0 | −15.9 | 0 | −89.1 | −48.8 | 29.9 | PASS |
| `ride.flac` | Karoryfer Big Rusty Drums | FLAC 16 | 44.1 | 1 | 22.0 | −6.2 | 0 | −90.9 | −52.1 | 42.9 | PASS |
| `tom.flac` | Karoryfer Big Rusty Drums | FLAC 16 | 44.1 | 1 | 22.0 | −11.7 | 0 | −89.8 | −38.5 | 23.7 | PASS |
| `BDrumNew_hit_v3_rr1_Sum.wav` | VCSL | WAV 16 | 44.1 | 2 | 22.0 | −17.1 | 0 | −85.1 | −41.7 | 21.6 | PASS |
| `HiHat_Close_rr1_Mid.wav` | VCSL | WAV 16 | 44.1 | 2 | 22.0 | −22.7 | 0 | −97.9 | −53.7 | 27.9 | PASS |
| `Marimba_C4_med.wav` | VCSL | WAV 24 | 44.1 | 2 | 4.3 | −36.4 | 0 | −96.7 | −57.1 | 17.7 | PASS (dark flag) |
| `GrandPno_Sus_A4_v1.wav` | VCSL | WAV 16 | 44.1 | 2 | 22.0 | −5.3 | 0 | −60.9 | −35.0 | 26.7 | PASS |
| `A4v12.flac` | Salamander V3 | FLAC 24 | 48.0 | 2 | 24.0 | −11.9 | 0 | −69.5 | −40.1 | 25.2 | PASS |
| `C4v12.flac` | Salamander V3 | FLAC 24 | 48.0 | 2 | 24.0 | −6.9 | 0 | −58.4 | −34.9 | 25.0 | PASS |
| `A2v12.flac` | Salamander V3 | FLAC 24 | 48.0 | 2 | 24.0 | −9.6 | 0 | −52.8 | −34.9 | 22.4 | PASS |
| `Piano_ff_C4.aiff` | Iowa MIS | AIFF 16 | 44.1 | 2 | 22.0 | −14.5 | 0 | −61.8 | −45.9 | 28.3 | PASS |
| `Piano_mf_C4.aiff` | Iowa MIS | AIFF 16 | 44.1 | 2 | 22.0 | −29.7 | 0 | −71.8 | −59.4 | 26.7 | PASS |
| `Piano_pp_C4.aiff` | Iowa MIS | AIFF 16 | 44.1 | 2 | 22.0 | −42.5 | 0 | −66.7 | −67.3 | 21.8 | PASS |
| `28.flac` (Bramble) | first-party Flock | FLAC 16 | 44.1 | 2 | 1.8 | −3.0 | 0 | none | −15.0 | 9.0 | PASS (sub, dark) |
| `28.flac` (Cinder) | first-party Flock | FLAC 16 | 44.1 | 2 | 22.0 | −3.2 | 0 | none | −14.1 | 7.8 | PASS |
| `61.flac` (Quill) | first-party Flock | FLAC 16 | 44.1 | 2 | 22.0 | −3.0 | 0 | none | −15.7 | 9.7 | PASS |
| `60.flac` (Hush) | first-party Flock | FLAC 16 | 44.1 | 2 | 4.0 | −3.6 | 0 | −54.6 | −25.8 | 19.2 | PASS (dark flag) |
| `LL-Q1860_drumming.wav` | Wikimedia via Openverse | WAV 16 | 48.0 | 1 | 24.0 | −6.4 | 0 | −62.0 | −31.5 | 22.1 | PASS |
| `Drum_Roll_Intro.ogg` | Wikimedia via Openverse | Vorbis | 44.1 | **6** | 15.5 | −15.7 | 0 | none | −35.1 | 16.3 | FAIL: lossy |

**Loops (stated BPM from the title/API)**

| File | Source | Codec / kbps | kHz | BW kHz | Peak dBFS | Clip runs | Noise floor | LUFS | Crest | `analyze` BPM | `analyze` key | Bars actual | Bar residual | Gate |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---|
| `187855_130bpm.mp3` | Freesound via Openverse | MP3 ~196 | 48.0 | 18.8 | **+0.19** | 0 | none | −11.6 | 8.8 | **130.0** | G major | **1.000** | 0.0 ms | FAIL: lossy, peak |
| `201920_128bpm.mp3` | Freesound via Openverse | MP3 ~200 | 48.0 | 18.8 | −1.0 | 0 | none | −17.9 | 13.9 | **128.0** | D# major | **1.000** | 0.0 ms | FAIL: lossy |
| `629138_lofi95.mp3` | Freesound via Openverse | MP3 ~198 | 44.1 | **8.5** | −0.9 | 0 | none | −17.8 | 13.9 | **95.24** | G# minor | **8.000** | 0.0 ms | FAIL: lossy (8.5 kHz flagged) |
| `236003_808.mp3` | Freesound via Openverse | MP3 ~196 | 44.1 | 12.7 | −0.5 | 0 | **−20.8** | −13.3 | 9.8 | 117.65 | G minor | 10.607 at 118* | — | FAIL: lossy, noise, bars unverified |
| `152355_loop.mp3` | Freesound via Openverse | MP3 ~191 | 44.1 | 18.7 | **+1.95** | **34** | −98.3 | −15.0 | 13.9 | 98.36 | D# minor | 1.96 at 98* | — | FAIL: lossy, clipping, bars unverified |

\* No stated BPM in the title/API. The BPM shown is `analyze`'s guess, so the bar check cannot be applied. That is exactly why the gate needs a **stated** BPM, not a guessed one.

### 2.3 What the numbers say

1. **The Freesound musical data is often good; the delivery is not.** Two loops are sample-exact one-bars, and the 95 BPM loop is sample-exact eight bars. `analyze` recovers 130.0, 128.0 and 95.24 BPM. The keys (G major, D# major, G# minor) are plausible but were not verified by ear; confidence was 0.56, 0.60 and 0.46. If Rookery could fetch the **original WAV/FLAC** for these, the current tool would already be much better. It cannot without OAuth.
2. **Every preview fails on codec alone.** The best preview is 18.8 kHz; the worst is 8.5 kHz. One file peaks at +1.95 dBFS with 34 clipped runs; another at +0.19 dBFS. These are not "slightly lossy"; they are audibly dull and occasionally clipped.
3. **The free instrument libraries are clean.** Karoryfer and VCSL are 44.1 kHz/16-bit, 22 kHz bandwidth, −85 to −98 dBFS noise floor, zero clipping. Karoryfer's drum kit is a real recorded kit with velocity layers and round robins; it is the strongest keyless source measured. The trade-off is obvious: one-shots, no loops.
4. **Salamander and Iowa are clean but narrow.** 48 kHz/24-bit (Salamander) and 44.1/16 (Iowa) with 22–24 kHz bandwidth. They are piano libraries, not general sample sources.
5. **The first-party Flock voices pass the lossless gate.** They are 44.1 kHz/16-bit FLAC, peak −3 dBFS, no clipping. Bramble (sub) and Hush (pad) are legitimately dark (1.8 and 4.0 kHz), which is why bandwidth must be advisory for one-shots.
6. **Openverse can serve full-quality originals, but the catalog is not a sample pack.** The Wikimedia WAV passed; the Wikimedia OGG was 6-channel Vorbis and failed. Openverse is an aggregator, not a curated pack.

---

## 3. Top recommendation: local-first, with a pinned CC0 one-shot kit

### 3.1 Why

- **Quality:** the user's own commercial packs are the only source that already sounds like a commercial pack. They are also the sounds the user actually wants in *their* music.
- **Licence:** indexing a folder and copying one file into the local kit is not redistribution. No new licence, no attribution debt, no export change for the user's own files.
- **Determinism:** an imported copy plus a SHA-256 is reproducible even if the original folder is reorganised or the pack is uninstalled.
- **Coverage:** the user's library has loops. The CC0 kit covers drums/percussion for users who have no library, and for one-shots that are hard to find locally.
- **Honesty:** it stops pretending Openverse previews are a sample library.

### 3.2 New tool: `rookery_library`

A separate tool, not a `rookery_samples` source, because it has different guarantees: **no network, no key, no telemetry, user-owned files**.

Schema (proposed):

```
rookery_library(action, folder?, max_files?, query?, bpm?, key?, kind?, limit?, id?)
```

| Action | Parameters | Behaviour |
|---|---|---|
| `scan` | `folder` (absolute path), `max_files` (default 5000, cap 20000) | Walk the folder (no symlinks, no hidden dirs, max depth 8, skip files > 50 MB), read each audio file with `soundfile`, measure the gate, parse BPM/key from the file name and its parent folders, write a local index. Return counts and the top-level folder name only. |
| `search` | `query`, `bpm`, `key`, `kind` (`loop`/`one-shot`/`texture`), `limit` (1–20) | Search the local index. Return compact hits in the same shape as `rookery_samples.search`: `id`, `title`, `seconds`, `bpm`, `key`, `kind`, `quality`, `fit`. Never return the absolute path. |
| `import` | `id` | Verify the file is still the same size/hash, copy it to `<user_kit_dir>/library/<slug>-<hash8>.flac` (24-bit FLAC, peak-normalised to −1 dBFS), write a credit entry with `license: "user-owned"`, `origin: "local"`, `source_sha256`, and the measured metrics. Return a ready `user:library/...` source. |
| `list` | — | List scanned folders, file counts, and the last scan time. |

Index file: `<plugin_data_dir("rookery")>/library-index.json`. It contains absolute paths, so it stays in the user's data dir and is never logged or exported. The tool output uses basenames only.

Search ranking: exact BPM first (allow half/double time), then key fit using `sampling.key_fit`, then a quality score (lossless, 44.1+, 22 kHz, low noise), then filename/tag match. This is the same `fit` idea as `rookery_samples.search`, but with real metadata instead of title guesses.

Why copy rather than reference the external path: `rookery/project.py` only accepts `user:` sources under the kit; importing makes the project portable and pins the audio. The source hash in `credits.json` records where it came from without exposing the path in the export.

### 3.3 Pinned CC0 one-shot kit

Ship **metadata only** in the repo (a manifest under `rookery/` or `docs/`), no audio. The manifest lists a small curated set, not the whole library:

- **Karoryfer Big Rusty Drums** — kick, snare (top/bottom), closed/open hi-hat, ride, crash, toms, rim/click. 44.1/16 FLAC, measured clean.
- **VCSL** — bass drum, snare, hi-hat, marimba, glockenspiel, timpani, cymbal, and a few orchestral one-shots for textures.

Proposed schema for each entry:

```json
{
  "schema": "rookery.sample-source/1",
  "id": "karoryfer.big-rusty-drums/kick_24/k_vl10_rr1",
  "source": "karoryfer.big-rusty-drums",
  "repo": "https://github.com/sfzinstruments/karoryfer.big-rusty-drums",
  "commit": "f07ce00df34a46b6b08375be56fe116cf15782bc",
  "path": "Samples/kick_24/kick/kick/k_vl10_rr1.flac",
  "url": "https://raw.githubusercontent.com/sfzinstruments/karoryfer.big-rusty-drums/f07ce00df34a46b6b08375be56fe116cf15782bc/Samples/kick_24/kick/kick/k_vl10_rr1.flac",
  "sha256": "a43a2124efb24f21f62a79f2fa1eab99dbae800aae111e9da124830703b06720",
  "bytes": 39943,
  "license": "CC0-1.0",
  "license_url": "https://creativecommons.org/publicdomain/zero/1.0/legalcode",
  "kind": "one-shot",
  "tags": ["kick", "acoustic", "close", "dry"]
}
```

Fetch rules:

- One file per call. No prefetch, no zipping the repo, no walking the upstream tree.
- `https://raw.githubusercontent.com` only, with a plain `User-Agent`.
- Maximum 20 MB. Verify `Content-Length`, then `sha256` and `bytes`; delete and error on mismatch.
- Write 24-bit FLAC to `<user_kit_dir>/library/`, and a `credits.json` entry with `license`, `license_url`, `source_url`, `source_commit`, `source_sha256`.
- A missing manifest entry is an error; no "latest" URL, no self-update.

### 3.4 Changes to `rookery_samples`

Keep the tool name and the two actions for compatibility, but stop the preview import:

- `action="search"`: unchanged endpoint, but request the fields that expose the original's format: `alt_files` (already in Openverse's response), `bit_rate`, `sample_rate`, `filetype`, `filesize`. Add a `quality` block:
  - `lossless_source`: true if any `alt_files` entry has `filetype` in `{wav, flac, aiff}` and `sample_rate >= 44100`;
  - `original_filetype`, `original_samplerate`, `original_bytes`;
  - `preview_only`: true when the only `url` is MP3/OGG.
  Sort lossless-source hits first. Hits with no lossless source are still shown but marked `preview_only: true` and cannot be fetched.
  The current compact hit is capped at 150 bytes; a full quality object will not fit. Either raise the cap to about 220 bytes or encode a short `q` string (`"lossless,48k,22k,-86"`) and keep the full metrics in `credits.json`.
- `action="fetch"`: decode and run the gate **before** writing. If the source is lossy, return a specific error:
  > "This result is a Freesound preview (MP3/OGG; measured 191–200 kbps here); Rookery will not import it. Use a lossless CC0 source, add a Freesound OAuth token, or download the original yourself and use `rookery_library`."
- `action="fetch"` with `source="cc0_kit"` and a manifest id: fetch the pinned file, verify, import. This can be a second tool (`rookery_kit`) if the schema gets crowded, but one tool is fewer moving parts.
- Optional `source="freesound"`: only if a user key + OAuth token exists. Default off. See section 5.

Backwards compatibility: existing credits and `user:library/...` sources keep working. The only regression is that a preview fetch that used to succeed now fails with an explanation. That is deliberate.

### 3.5 Pinning scheme

**Rule:** pin the *source bytes*, not the derived FLAC. Normalisation and FLAC encoding can change across library versions; the source file is the thing that must be identical.

For every imported sample, `credits.json` gets:

```json
{
  "id": "karoryfer.big-rusty-drums/kick_24/k_vl10_rr1",
  "file": "kick-...flac",
  "title": "Big Rusty Drums — kick, close, v10",
  "creator": "Karoryfer Samples",
  "license": "CC0-1.0",
  "license_url": "https://creativecommons.org/publicdomain/zero/1.0/legalcode",
  "source_url": "https://raw.githubusercontent.com/.../k_vl10_rr1.flac",
  "source_commit": "f07ce00df34a46b6b08375be56fe116cf15782bc",
  "source_sha256": "a43a...6720",
  "source_bytes": 39943,
  "import": {
    "version": 1,
    "codec": "FLAC",
    "subtype": "PCM_24",
    "sample_rate": 44100,
    "peak_dbfs": -1.0,
    "gate": "rookery.sample-gate/1"
  },
  "metrics": {"bandwidth_hz": 22000, "noise_floor_dbfs": -86.6, "lufs": -33.0, "crest_db": 23.4, "clipping_runs": 0}
}
```

For the user library: `origin: "local"`, `source_path` (absolute, stored locally only), `source_sha256`, `source_bytes`, `source_mtime`, `license: "user-owned"`. The imported copy is what the project references, so a later edit to the original does not change the render.

For Freesound originals: `provider: "freesound"`, `freesound_id`, `md5` (Freesound's own original-file hash), `source_sha256`, `license`, `license_url`, `original_filetype`, `original_samplerate`. Verify both `md5` and `sha256` after download.

If an imported file is missing at render time, `rookery_samples` can re-fetch by manifest id and hash (CC0 kit) or tell the user to re-import (local library). A hash mismatch is a hard error, not a warning.

### 3.6 Proposed Disclosure text (README)

Replace the current network bullet and add the library/kit bullets:

```markdown
- **Local files.** Projects, history, renders and exports are written under
  `plugin_data_dir("rookery")`. Nothing is uploaded.
- **User kit folder.** Rookery reads audio files from the configured
  `user_kit_dir` (default: `plugin_data_dir/kits`). It never copies them into
  the repo.
- **Local sample library (`rookery_library`).** Scans only the folders you
  list, measures the files, and stores the index under
  `plugin_data_dir("rookery")/library-index.json`. Importing copies one chosen
  file into `<user_kit_dir>/library/` and records its SHA-256. No network
  call, no key, no telemetry. You are responsible for the licence of any
  folder you index; Rookery does not redistribute those files.
- **Pinned CC0 kit (`rookery_samples source=cc0_kit`).** Downloads individual
  files listed in `rookery/sample-sources.json` from
  `raw.githubusercontent.com`: Karoryfer Samples' free libraries and the
  Versilian Community Sample Library (VCSL), both released under CC0 1.0
  (https://creativecommons.org/publicdomain/zero/1.0/legalcode). Each file is
  pinned by repository commit and SHA-256; a hash mismatch is refused. Only
  the manifest is in the repository, never the audio. No API key, no
  telemetry.
- **Openverse search (`rookery_samples source=openverse`).** Queries
  `api.openverse.org` (keyless; 20 requests/minute, 200/day) and shows CC0
  results. Openverse's Freesound results are lossy MP3 previews (191–200 kbps
  in these measurements), so
  Rookery marks them `preview_only` and refuses to import them. Rookery does
  not download from `cdn.freesound.org` for import.
- **Freesound (optional, off by default).** If you add Freesound API
  credentials through Hermes (`FREESOUND_CLIENT_ID`,
  `FREESOUND_CLIENT_SECRET`, `secret: true`), Rookery can request
  original-quality CC0 downloads with Freesound's OAuth2 flow. The credentials
  stay in Hermes's env store, are never logged, and are never sent anywhere
  except `freesound.org`. Rate limits: 60 requests/minute and 2,000/day for
  search; 30/minute and 500/day for original downloads. No bulk download.
- **First-party voices.** `rookery/flock/voices/` contains FLAC one-shots
  rendered by the Rookery authors with Xfer Serum from original patches. No
  Serum binaries, presets or wavetable files are included; Serum is a
  build-time authoring tool only. The manifest records the provenance, patch
  hashes and an 8 MiB budget.
- **VST3 / Corvus FX.** Unchanged.
```

Keep the existing "no telemetry" sentence; it is now true for every new path too.

### 3.7 What Ethan has to do

**For the top recommendation:**

1. Put his sample folders in the plugin config, e.g. `rookery.library_dirs = ["D:\\Samples", "D:\\FL Packs"]`. (New config key; the exact name is an implementation choice.)
2. Run `rookery_library action=scan folder=...` once. It is local and can take a few minutes for tens of thousands of files.
3. Listen to the first 20 hits and mark a few favourites if the tool supports tags. No key, no account, no upload.
4. Approve the CC0 kit manifest (Karoryfer + VCSL). No work beyond a yes; it is metadata only.
5. If he wants Freesound loops specifically: download 10–20 CC0 **originals** while logged in at freesound.org, save them in a folder with a `LICENSE.txt`/`credits.json`, and scan that folder. This avoids OAuth and keeps the licence trail.

**For the runner-up:** see section 4.4.

### 3.8 Migration and compatibility

- `rookery_samples` old credits keep working because they already have `license: "cc0"` and a `file`. Add `metrics` and `source_sha256` lazily on the next import.
- `export._license()` currently says "library sources are CC0" and lists CC0 credits. With `rookery_library`, user-owned files are outside `library/` and already fall into the `own` branch ("User-provided sounds: your own files"). The CC0 kit files are inside `library/` and have a real `license_url`, so the existing credits block still works. Add a line for `origin: "local"`: "User-provided sounds: your own files (…)" is already there; do not claim they are CC0.
- `tools/audit.py` needs a new rule for `rookery/sample-sources.json`: it is JSON metadata, not audio, so `rule_samples` already passes; add a check that every manifest URL is `https://raw.githubusercontent.com/...` and every entry has `sha256`, `license_url`, `commit`, `bytes`. The current audit rule only allows audio under `rookery/flock/voices/`, so do not put the kit audio in the repo.
- `plugin.yaml` gains `rookery_library` in `provides_tools`; `rookery_samples` stays. If a Freesound key is added, declare it under `requires_env`/`optional_env` with `secret: true`.

---

## 4. Runner-up: a first-party "Rookery Sessions" pack

### 4.1 What to render

A small, curated pack that sounds like the Flock, not a generic Splice clone.

| Item | Count | Spec |
|---|---:|---|
| Drum loops | 4 | 2 bars, 90/120/140 BPM, dry, no sidechain, kick/snare/hat/perc |
| Melodic loops | 4 | 4 bars, C minor / F minor / A minor, 90/120/140 BPM, stem-like (no drums) |
| Texture loops | 4 | 4 or 8 bars, vinyl/tape/room, quiet, mono-compatible |
| One-shots: drums | 12 | kick ×3, snare ×3, clap ×2, hat closed/open ×2, perc ×2 |
| One-shots: tonal | 12 | bass hit ×2, chord stab ×2, pluck ×2, bell ×2, sub ×2, FX ×2 |

Format: **48 kHz, 24-bit FLAC** (WAV for the authoring copies). Loops are exactly N bars at the stated BPM, no fade that eats the downbeat, no reverb tail beyond the bar unless it is a texture. One-shots are trimmed at −70 dBFS with a 10 ms fade. Loudness: −14 LUFS integrated for loops, true peak ≤ −1 dBTP; one-shots peak-normalised to −3 dBFS and left dynamic.

Naming: `kick_deep_120bpm_Cmin_1shot.flac`, `keys_dusty_140bpm_Fmin_4bars.flac`, `texture_tape_90bpm_Amin_8bars.flac`. Put BPM, key and bars in the filename so `sampling.parse_title` and the gate can verify them.

Provenance: **original patches and recordings only.** Serum's author has said a licensed user may use Serum "in any sound design capacity" and that original sounds (not third-party noise/wavetables) are clear (https://xferrecords.com/forums/general/can-i-use-serum-to-create-samples-i-sell-directly-or-even-create-a-sample-based-instrument). Do **not** render FL Studio stock samples or third-party pack loops into a redistributed pack. Check Image-Line's EULA and the pack's licence first; most allow use in music, not resale as samples. If a drum is needed, use a Karoryfer CC0 hit or synthesize it.

### 4.2 Hosting and pinning

- Put the pack on a GitHub release as `rookery-sessions-v1.zip`, with `manifest.json` inside and beside it. Pin the release tag and the SHA-256 of the zip and of every file.
- The plugin ships only `rookery/sample-packs.json` (metadata). `rookery_samples source=first_party` fetches one file by id, verifies SHA-256, imports.
- Do not use a "latest" URL. Do not auto-update. A new pack is a new tag + manifest.
- If the pack is small enough for the 8 MiB repo budget, extend the Flock voices manifest pattern instead. The current voices use 5.17 MiB of the 8 MiB (per `tools/audit.py`), so a meaningful loop pack will not fit; use the release asset.

### 4.3 Effort and risk

- **Effort:** 1–2 days of authoring for 12 loops + 24 one-shots if the FL projects/patches already exist; half a day for rendering, trimming, loudness and naming; 1–2 hours for the manifest and release. Start with 4 loops + 12 one-shots if a day is all there is.
- **Risk:** the pack is only as good as the curation; a bad loop is worse than no loop. The licence statement must be explicit. Hosting adds a network dependency (disclosed). A first-party pack does not solve the "user wants a specific genre" problem; the local library does.

### 4.4 What Ethan has to do

1. Render the files at 48 kHz/24-bit from original patches.
2. Curate: keep only what he would put in a pack he sells. Delete the rest.
3. Run `tools/sample_quality.py --kind loop --bpm ...` on every loop and `--kind one-shot` on every hit; fix or drop failures.
4. Upload the zip + manifest, send the tag and SHA-256.
5. Approve the licence line: CC0 1.0 (simplest) or "free to use in music, including commercial; do not redistribute as samples".

---

## 5. Freesound APIv2: verdict

### 5.1 What "done properly" would look like

Search with a user token:

```
GET https://freesound.org/apiv2/search/
  ?query=dark+piano+loop
  &filter=license:"Creative Commons 0" samplerate:[44100 TO *] type:(wav OR flac OR aiff)
  &sort=rating_desc
  &fields=id,name,license,type,samplerate,bitdepth,channels,duration,filesize,md5,
          num_downloads,avg_rating,num_ratings,bpm,bpm_confidence,tonality,
          tonality_confidence,loopable,spectral_rolloff,previews,download
  &token=...
```

Quality signals that are actually useful:

- `avg_rating >= 3.8` and `num_ratings >= 3` (avoid one-vote wonders);
- `num_downloads >= 100` (a weak popularity prior, not quality);
- `bpm_confidence >= 0.7` and `tonality_confidence >= 0.5` when the query needs tempo/key;
- `loopable = true` for loops;
- `type` in `{wav, flac, aiff}` and `samplerate >= 44100`;
- `spectral_rolloff` high (but this is Essentia's descriptor, not a substitute for the measured −60 dB bandwidth);
- `md5` for pinning.

Original download:

```
GET https://freesound.org/apiv2/sounds/{id}/download/
Authorization: Bearer <OAuth2 access token>
```

### 5.2 Why it is not the default

- **The key alone is not enough.** Freesound's docs: original-quality downloads require OAuth2; previews do not. A plain API key gets you only the previews that already fail the gate.
- **OAuth is a product, not a field.** It needs a registered application (client id/secret), a browser authorization step, a redirect/callback (or a paste-a-token workaround), token storage, refresh, and revocation handling. That is a lot of surface for a plugin whose core makes no network calls.
- **The terms add obligations.** API keys are per application and must not be shared; the API is for interaction with your application, not full database copies; intermediate copies should be deleted when no longer needed; commercial API use is negotiated case-by-case. A distributed plugin with a single bundled key would be a terms problem; a per-user key is fine but is another setup step.
- **The rate limits are small for browsing.** 60 requests/minute and 2,000/day for search, 30/minute and 500/day for downloads. A user auditioning loops can hit that quickly.
- **The quality is still variable.** Freesound is a field-recording community with some excellent musicians. Ratings and descriptors help, but they do not make it a commercial pack. The measured previews were musically exact and acoustically poor; the originals would be better, but not uniformly "incredible".

### 5.3 If Ethan insists

Do it as an **optional advanced source**, exactly:

1. Declare `FREESOUND_CLIENT_ID` and `FREESOUND_CLIENT_SECRET` under `requires_env` with `secret: true`; check `os.environ` only through the Hermes env path, never log the values.
2. Implement the OAuth2 authorization-code flow with a localhost callback on a fixed port, `state` validation, and a short-lived access token. Store the refresh token in the Hermes env store, not in the project.
3. Only `license:"Creative Commons 0"`; reject `Attribution` and `Attribution NonCommercial` by default. (CC BY would force an attribution block into every export; CC BY-NC is not publishable commercially.)
4. Download the original, verify `md5` and `sha256`, run the gate, then import.
5. Cache search results for 24 hours; never bulk-download; one sound per user action.
6. If the token is absent, the source is hidden, not broken. The default paths must work with no key.

For most users, the cheaper path is: **download the CC0 originals manually, put them in a folder, and let `rookery_library` index them.** No OAuth, no key, no API terms, and the user sees exactly what they are getting.

---

## 6. Local generative models

| Model | Weights licence | Commercial use | Why not for Rookery |
|---|---|---|---|
| **Stable Audio Open 1.0 / Small** | Stability AI Community License — https://stability.ai/license | Yes under **$1M** annual revenue, but **registration** and "Powered by Stability AI" attribution are required; above $1M the licence terminates. Weights are gated behind a Hugging Face account acceptance. | 1B-param diffusion + T5 + VAE; needs PyTorch/GPU (or a slow CPU path); outputs are not sample-pack-curated; model access requires an account. The licence is not a clean "no attribution" grant. |
| **MusicGen** (small/medium/large/melody) | **CC BY-NC 4.0** — https://github.com/facebookresearch/audiocraft/blob/main/LICENSE_weights | **No.** | Non-commercial. Reject. |
| **AudioGen** | **CC BY-NC 4.0** (same AudioCraft weights licence) | **No.** | Non-commercial. Reject. |
| **MAGNeT** | **CC BY-NC 4.0** (AudioCraft) | **No.** | Non-commercial. Reject. |
| **Riffusion v1** | CreativeML OpenRAIL-M — https://huggingface.co/riffusion/riffusion-model-v1 | The licence permits commercial use subject to use restrictions, but the model card says "intended for research purposes only"; output is a 512×512 spectrogram, i.e. lo-fi. | Quality is below the previews measured here. Reject. |
| **ACE-Step 1.0 / 1.5** | Apache-2.0 (1.0) / MIT (1.5) — https://github.com/ace-step/ACE-Step , https://github.com/ace-step/ACE-Step-1.5 | **Yes** (the clearest licence of the group). | 2B–4B DiT + LM, 4–20 GB VRAM, PyTorch, several GB of weights; full-song generator, not a sample-pack curator; deterministic seeds are not guaranteed across hardware. A future optional "generate a texture" tool, not a default. |

The pattern is the one the brief predicted: **MusicGen/AudioGen/MAGNeT are non-commercial; Stable Audio Open is commercial only under a revenue threshold with registration and attribution; the Apache/MIT models are too heavy and too non-deterministic for a plugin that promises reproducible renders.** None belongs in the catalog now.

---

## 7. The quality gate

This is the part to implement in one follow-up brief. It applies to **every** source: network fetch, CC0 kit, first-party pack, and user library.

### 7.1 Thresholds

| Check | Threshold | Why |
|---|---|---|
| **Codec** | Reject MP3, MP2, AAC, Vorbis, Opus, WMA, AC-3; reject WAV/AIFF whose subtype is MPEG/Vorbis/Opus. Accept WAV, AIFF, FLAC with PCM 16/24/32 or float. | A lossy preview cannot be restored by re-encoding to FLAC. Commercial packs ship lossless. This is the single check that fixes the current results. |
| **Sample rate** | ≥ 44,100 Hz. | 44.1k gives a 22.05k Nyquist. 32k/22.05k sources lose the top octave and are audibly lo-fi. 48k is preferred but not required. |
| **Bit depth** | ≥ 16-bit PCM (or float). Reject 8-bit/unsigned. | 16-bit is CD quality and is what Karoryfer ships; 24-bit is preferred for headroom. |
| **Channels** | 1 or 2. | Rookery's renderer and sample track are mono/stereo; a 6-channel OGG (measured) is not usable. |
| **Bandwidth** | **Hard floor for loops:** ≥ 8,000 Hz. **Advisory:** flag loops below 19 kHz and one-shots below 16 kHz. | 8 kHz is the point where a loop is a telephone effect, not a sample. MP3 previews measured 8.5–18.8 kHz; the codec check already rejects them. A kick, 808, sub or deliberate lo-fi loop is legitimately dark, so bandwidth must not be a hard reject except at the floor. |
| **Clipping** | Reject if any run of ≥ 3 consecutive samples at |x| ≥ 0.999, or > 0.05% of samples at full scale, or peak > 0 dBFS. | A run of 3+ is hard clipping, not a transient. MP3 decode overshoot is a real defect (measured +1.95 dBFS, 34 runs). |
| **Noise floor** | When the file contains silence (min 200 ms frame ≤ −50 dBFS): 10th-percentile frame RMS ≤ **−45 dBFS**. Skip when there is no silence (continuous loop). | −45 dBFS is audible hiss at normal monitoring. Karoryfer/VCSL measured −85 to −98; the 808 MP3 measured −20.8. A pad tail at −54.6 is fine. |
| **LUFS** | Advisory: −22 to −6 LUFS. Loops should be −14 to −8; one-shots are often −30 to −55 and are normalised on import. | Rookery peak-normalises to −1 dBFS; a raw one-shot is not "bad" for being quiet. Do not reject on loudness. |
| **Crest** | Advisory: 4–24 dB. Percussion and piano can be 25–43 dB. | A high crest means transient-rich, not defective. Flag only. |
| **Loop length** | Requires a **stated** BPM (API `bpm` with confidence ≥ 0.7, or a filename/title match). `bar_s = 240 / BPM`. Pass if `1 ≤ round(bars) ≤ 16` and `abs(bars − round(bars)) × bar_s ≤ max(25 ms, 2% of bar_s)`. If no stated BPM, mark `loop_length: "unverified"`; do not reject on a guessed BPM. | At 120 BPM a bar is 2,000 ms; 25 ms is 1.25%. The three Freesound loops with stated BPM were exact to 0.0 ms. A trailing reverb can add a few ms; 25 ms is tolerant without accepting a 1.96-bar loop as 2 bars. |
| **`analyze` sanity** | BPM estimate within ±3% of stated BPM, or a half/double-time relation; key confidence ≥ 0.5. | `analyze` recovered 130.0/128.0/95.24; low key confidence (0.46) should be flagged, not silently trusted. |

### 7.2 Reject vs flag

**Hard reject (do not import):**

- lossy codec;
- sample rate < 44.1 kHz;
- bit depth < 16;
- channels > 2;
- clipping;
- loop bandwidth < 8 kHz;
- loop with a stated BPM that is not a whole number of bars;
- duration > 30 s (the existing cap) or > 20 MB (the existing cap).

**Flag (import, but show in `quality.warnings` and down-rank in search):**

- loop bandwidth 8–19 kHz (`narrow-band loop`);
- one-shot bandwidth < 16 kHz (`dark/narrow`);
- LUFS outside −22..−6;
- crest outside 4–24 dB;
- key confidence < 0.5;
- no stated BPM (`loop_length: "unverified"`);
- noise floor not measurable (no silence);
- sample rate exactly 44.1 kHz (fine, but 48k is preferred);
- mono source used as a stereo texture.

**User-library exception:** for local files, "hard reject" means **excluded from the default search**; `rookery_library action=import id=... allow_flagged=true` can import a lossy file the user explicitly chose, with `quality.warnings` in the credit. The user owns the file; the tool should not silently hide it, but it must not pretend it passed.

### 7.3 Pseudocode

```python
def gate(path, *, stated_bpm=None, kind="one-shot"):
    info = sf.info(path)
    fmt = (info.format or "").upper()
    sub = (info.subtype or "").upper()
    if fmt not in {"WAV", "FLAC", "AIFF"} or any(t in sub for t in ("MPEG", "VORBIS", "OPUS")):
        return reject("lossy codec")
    if info.samplerate < 44100:
        return reject("sample rate")
    if info.channels not in (1, 2):
        return reject("channels")
    if bits(info.subtype) < 16:
        return reject("bit depth")

    audio, sr = sf.read(path, dtype="float32", always_2d=True)
    mono = audio.mean(axis=1)
    peak_db, runs, frac = clipping(mono)
    if runs or frac > 0.0005 or peak_db > 0:
        return reject("clipping")

    width = bandwidth_60db(mono, sr)          # audible frames only
    floor = noise_floor(mono, sr)             # None when no silence
    lufs = integrated_lufs(mono, sr)
    crest = peak_db - rms_db(mono)

    warnings = []
    if kind == "loop" and width < 8000:
        return reject("bandwidth")
    if width < 16000:
        warnings.append("dark/narrow" if kind == "one-shot" else "narrow-band loop")
    elif kind == "loop" and width < 19000:
        warnings.append("below full range")
    if floor is not None and floor > -45:
        return reject("noise floor")
    if not (-22 <= lufs <= -6): warnings.append("loudness")
    if not (4 <= crest <= 24): warnings.append("crest")

    if kind == "loop":
        if stated_bpm is None:
            warnings.append("loop_length unverified")
        else:
            bars = (len(mono) / sr) / (240 / stated_bpm)
            residual = abs(bars - round(bars)) * (240 / stated_bpm)
            if not (1 <= round(bars) <= 16) or residual > max(0.025, 0.02 * (240 / stated_bpm)):
                return reject("loop length")
    return accept(warnings)
```

### 7.4 Calibration against the measured files

- **All 20 lossless one-shot files pass** (Karoryfer, VCSL, Salamander, Iowa, Flock, Wikimedia WAV; the dark marimba/Bramble/Hush are flagged, not rejected).
- **All 5 MP3 previews fail** (codec; two also peak/clip; one also noise; the 95 BPM preview is also only 8.5 kHz, flagged).
- **The 3 loops with stated BPM pass the bar check** with 0.0 ms residual; their only failure is the codec.
- **The 2 loops with no stated BPM** are marked `unverified`, not failed. This is the honest outcome: `analyze` guessed 117.65 and 98.36, but a guess cannot prove a bar count.

If the gate feels too strict on one-shots, the only threshold worth revisiting is bandwidth; keep it advisory there. Do not relax the lossless, sample-rate or clipping checks.

---

## 8. What I could not verify

- **No listening.** I did not audition any file. Every quality statement is a signal measurement, not an ear judgement. "Commercial-pack quality" for Karoryfer/VCSL is inferred from format, bandwidth, noise floor and the libraries' design (multi-velocity, round-robin, close mics), not from hearing them.
- **Freesound originals.** Not measured: the download endpoint returned 401 without OAuth. The previews are the only Freesound audio measured.
- **VSCO 2 CE raw WAVs.** The official raw-WAV download is a 3 GB archive; I measured VCSL instead, which is the GitHub-hosted CC0 library and includes much of VSCO 2 CE. I did not verify that every VSCO 2 CE sample is in VCSL.
- **Ethan's FL Studio library.** Not scanned. I do not know its folder layout, formats, or licences; the quality claim is from the fact that it is a commercial pack, not from measurement.
- **Philharmonia.** Not measured; the CC BY-SA + "not as-is" terms reject it before audio quality matters. The search result says the downloads are MP3, but I did not confirm every file.
- **FreePats.** Not measured; its banks are per-bank licensed (some CC0, some CC BY), and it explicitly calls Sonatina/Philharmonia non-free. A bank-by-bank review is required.
- **Local generative models.** Not run. No GPU, no weights fetched, no account created. Licences are from the model cards/licence files, not from legal review.
- **BPM/key ground truth.** The stated BPMs are from titles/API; the keys are `analyze`'s guesses. I did not verify the keys by ear or with a reference.
- **Commercial-pack comparison.** No commercial pack audio was measured (only the numbers in `tools/drum_targets.json` from an earlier pass). The gate is calibrated against the free sources above, not against a pack.
- **Legal advice.** None. The licence URLs and quotes are cited; a lawyer should confirm any redistribution plan, especially the first-party pack and the user-library terms.
- **Platform.** All measurements are on Windows 11 with ffmpeg 8.1.1 and the Hermes dev venv (`soundfile` 0.14.0, numpy 2.4.3, scipy 1.17.1). macOS/Linux decode paths were not measured.

---

## 9. Sources and exact licence URLs

**CC0 1.0 (public domain dedication)**
- Legal text: https://creativecommons.org/publicdomain/zero/1.0/legalcode
- Karoryfer free samples: https://shop.karoryfer.com/pages/free-samples — "All our free sample libraries are under a Creative Commons Zero license."
- Karoryfer Big Rusty Drums repo: https://github.com/sfzinstruments/karoryfer.big-rusty-drums (CC0-1.0)
- VCSL: https://github.com/sgossner/VCSL — "you can do whatever you want with these sounds (even make commercial software), no royalties, no credit, no special terms."
- VSCO 2 CE: https://versilian-studios.com/vsco-community/ — "The library is under a Creative Commons 0 (i.e. public domain) license."
- Freesound CC0 example: https://freesound.org/people/waveplaySFX/sounds/187855/ (per-item `license_url` = CC0 legal code)

**CC BY 3.0 (attribution)**
- Legal text: https://creativecommons.org/licenses/by/3.0/legalcode
- Salamander Grand Piano V3: https://github.com/sfzinstruments/SalamanderGrandPiano — "This work is licensed under a Creative Commons Attribution 3.0 Unported License."
- Iowa MIS is **not** CC BY; it is a permission statement: https://theremin.music.uiowa.edu/MIS.html — "may be downloaded and used for any projects, without restrictions." No licence URL.

**CC BY-SA 3.0 (share-alike)**
- Legal text: https://creativecommons.org/licenses/by-sa/3.0/legalcode
- Philharmonia: https://philharmonia.co.uk/resources/sound-samples/ — "You are free to use these samples as you wish, including releasing them as part of a commercial work. The only restriction is that they must not be sold or made available 'as is'..." and "Creative Commons Attribution-ShareAlike 3.0 Unported License."

**CC BY-NC 4.0 (non-commercial)**
- Legal text: https://creativecommons.org/licenses/by-nc/4.0/legalcode
- MusicGen/AudioGen/MAGNeT weights: https://github.com/facebookresearch/audiocraft/blob/main/LICENSE_weights (the file is the CC BY-NC 4.0 text)

**Other**
- Freesound API overview: https://freesound.org/docs/api/overview.html
- Freesound API terms: https://freesound.org/help/tos_api/
- Freesound API resources/fields: https://freesound.org/docs/api/resources_apiv2.html
- Openverse API: https://api.openverse.org/v1/
- Openverse terms: https://docs.openverse.org/terms_of_service.html
- Stable Audio Open: https://huggingface.co/stabilityai/stable-audio-open-1.0 ; licence: https://stability.ai/license
- Riffusion: https://huggingface.co/riffusion/riffusion-model-v1
- ACE-Step: https://github.com/ace-step/ACE-Step (Apache-2.0), https://github.com/ace-step/ACE-Step-1.5 (MIT)
- Serum sample-pack statement: https://xferrecords.com/forums/general/can-i-use-serum-to-create-samples-i-sell-directly-or-even-create-a-sample-based-instrument
- Sonatina/FreePats licence notes: https://freepats.zenvoid.org/other-sample-libraries.html

---

## Appendix A — files fetched and measured

All fetched files are in `C:\Projects\rookery\.crew\out\claude\T2\sounds\` (git-ignored). **22 files** were downloaded, under the ~30 cap. No accounts, no logins, no scraping.

| Source | Files | Notes |
|---|---|---|
| Openverse/Freesound previews | 5 MP3 | `187855`, `201920`, `629138`, `236003`, `152355` |
| Karoryfer Big Rusty Drums | 5 FLAC | kick, snare, hi-hat, ride, tom |
| VCSL | 4 WAV | bass drum, hi-hat, marimba, piano A4 |
| Salamander V3 | 3 FLAC | A2, A4, C4, velocity 12 |
| Iowa MIS | 3 AIFF | piano C4 pp/mf/ff |
| Wikimedia via Openverse | 1 WAV, 1 OGG | a spoken-word WAV and a 6-channel OGG |
| First-party Flock | 4 FLAC (in repo) | Bramble 28, Cinder 28, Quill 61, Hush 60 |

Pinned commits used:

- Karoryfer Big Rusty Drums: `f07ce00df34a46b6b08375be56fe116cf15782bc`
- VCSL: `c1ea7bcc3c7309650ab0da9d15c9cd1fbc4a4c7e`
- Salamander Grand Piano: `3382bf9496bba2486f5ab0de55a264d1dfc38404`

Example SHA-256 values:

```
a43a2124efb24f21f62a79f2fa1eab99dbae800aae111e9da124830703b06720  karoryfer/kick.flac
a2d8829e8b2b59e8afb12fa396b01758827059339c2a84ad066d17b36c82d1ff  vcsl/BDrumNew_hit_v3_rr1_Sum.wav
16f43b59ecb870359978c4523c97745a13c439d56e574ed5a96aec633aae5f4f  salamander/A4v12.flac
92f65bcbfb326257869017ea88da346bda98285183f13a78394f5d1c83218e0f  iowa/Piano_ff_C4.aiff
eea55a15bbb56037daed82889eb8498b76f78181db85627d5d1124baab517bc7  freesound/187855_130bpm.mp3
```

---

## Appendix B — `tools/sample_quality.py` output

Command (from the worktree root, Hermes dev venv):

```
python tools/sample_quality.py --kind one-shot \
  <out>/freesound/*.mp3 <out>/karoryfer/*.flac <out>/vcsl/*.wav \
  <out>/salamander/*.flac <out>/iowa/*.aiff <out>/wikimedia/* \
  rookery/flock/voices/bramble/28.flac rookery/flock/voices/cinder/28.flac \
  rookery/flock/voices/quill/61.flac rookery/flock/voices/hush/60.flac
```

```
file         sec       sr       ch      bit  codec       kbps   BW kHz     peak     clip    floor     LUFS    crest      BPM  key         bars  gate
152355_loop.mp3                  4.80    44100    2     -  mp3        190.9    18.7     1.95    34   -98.31   -14.96    13.9   98.36  D# minor      2  FAIL
    FAIL: lossy codec, clipping (34 runs)
187855_130bpm.mp3                1.85    48000    2     -  mp3        196.5    18.8     0.19     0     None   -11.57    8.76     130  G major       1  FAIL
    FAIL: lossy codec, peak 0.19 dBFS
201920_128bpm.mp3                1.88    48000    2     -  mp3        200.0    18.8    -0.97     0     None   -17.88    13.91     128  D# major      1  FAIL
    FAIL: lossy codec
236003_808.mp3                  21.57    44100    2     -  mp3        196.0    12.7    -0.51     0    -20.8   -13.33    9.82  117.65  G minor       8  FAIL
    FAIL: lossy codec, noise floor -20.8 dBFS
    note: dark/narrow: 12.7 kHz
629138_lofi95.mp3               20.21    44100    2     -  mp3        198.0     8.5    -0.93     0     None    -17.8    13.86   95.24  G# minor      8  FAIL
    FAIL: lossy codec
    note: dark/narrow: 8.5 kHz
hihat.flac                       1.24    44100    1    16  flac       251.6    22.0   -15.90     0   -89.08   -48.75   29.85  176.47  B minor       1  PASS
    note: loudness -48.75 LUFS, crest 29.85 dB
kick.flac                        1.70    44100    1    16  flac       188.1    22.0    -6.62     0   -86.57   -32.99   23.37  157.89  D minor       1  PASS
    note: loudness -32.99 LUFS
ride.flac                       11.58    44100    1    16  flac       147.5    22.0    -6.15     0   -90.87   -52.05    42.9   150.0  G# major      8  PASS
    note: loudness -52.05 LUFS, crest 42.9 dB
snare.flac                       1.45    44100    1    16  flac       193.2    22.0   -23.90     0   -90.12   -52.24   25.33  171.43  G major       1  PASS
    note: loudness -52.24 LUFS, crest 25.33 dB
tom.flac                         2.50    44100    1    16  flac       162.1    22.0   -11.72     0   -89.82   -38.47   23.74  130.43  G minor       1  PASS
    note: loudness -38.47 LUFS
BDrumNew_hit_v3_rr1_Sum.wav      2.08    44100    2    16  pcm_s16   1411.2    22.0   -17.14     0   -85.09   -41.69   21.55  176.47  F major       2  PASS
    note: loudness -41.69 LUFS
GrandPno_Sus_A4_v1.wav           8.62    44100    2    16  pcm_s16   1411.2    22.0    -5.29     0   -60.92   -34.95   26.66  107.14  A major       4  PASS
    note: loudness -34.95 LUFS, crest 26.66 dB
HiHat_Close_rr1_Mid.wav          1.34    44100    2    16  pcm_s16   1411.2    22.0   -22.73     0   -97.87   -53.66   27.94  181.82  C minor       1  PASS
    note: loudness -53.66 LUFS, crest 27.94 dB
Marimba_C4_med.wav               2.48    44100    2    24  pcm_s24   2116.8     4.3   -36.41     0   -96.67   -57.07   17.66  181.82  C major       2  PASS
    note: dark/narrow: 4.3 kHz, loudness -57.07 LUFS
A2v12.flac                      16.17    48000    2    24  flac       977.8    24.0    -9.56     0   -52.75   -34.92   22.36  157.89  A major       8  PASS
    note: loudness -34.92 LUFS
A4v12.flac                      13.74    48000    2    24  flac       845.1    24.0   -11.94     0   -69.51   -40.13   25.18  142.86  A major       8  PASS
    note: loudness -40.13 LUFS, crest 25.18 dB
C4v12.flac                      15.72    48000    2    24  flac       904.1    24.0    -6.89     0   -58.43   -34.88   24.99  142.86  C major       8  PASS
    note: loudness -34.88 LUFS, crest 24.99 dB
Piano_ff_C4.aiff                36.02    44100    2    16  pcm_s16   1411.2    22.0   -14.54     0   -61.84   -45.88   28.34  162.16  C major       8  PASS
    note: loudness -45.88 LUFS, crest 28.34 dB
Piano_mf_C4.aiff                30.91    44100    2    16  pcm_s16   1411.2    22.0   -29.73     0   -71.77   -59.38   26.65  157.89  C major       8  PASS
    note: loudness -59.38 LUFS, crest 26.65 dB
Piano_pp_C4.aiff                29.45    44100    2    16  pcm_s16   1411.2    22.0   -42.51     0   -66.72   -67.33   21.82  162.16  C major       8  PASS
    note: loudness -67.33 LUFS
Drum_Roll_Intro.ogg              3.98    44100    6     -  vorbis     516.0    15.5   -15.72     0     None   -35.06   16.34  117.65  B minor       2  FAIL
    FAIL: lossy codec, channels 6
    note: dark/narrow: 15.5 kHz, loudness -35.06 LUFS
LL-Q1860_drumming.wav            0.74    48000    1    16  pcm_s16    768.0    24.0    -6.39     0   -61.99   -31.49   22.09  113.21  G major       1  PASS
    note: loudness -31.49 LUFS
28.flac                          1.35    44100    2    16  flac       177.1     1.8    -3.00     0     None   -14.99    8.99  176.47  E major       1  PASS
    note: dark/narrow: 1.8 kHz
28.flac                          0.60    44100    2    16  flac       212.2    22.0    -3.24     0     None   -14.06    7.82  176.47  E major       1  PASS
61.flac                          1.26    44100    2    16  flac       355.1    22.0    -3.00     0     None   -15.7     9.7  171.43  C# major       1  PASS
60.flac                          5.20    44100    2    16  flac       306.7     4.0    -3.56     0   -54.56   -25.79   19.23   92.31  C major       2  PASS
    note: dark/narrow: 4.0 kHz, loudness -25.79 LUFS
```

Loop checks (same tool, `--kind loop --bpm ...`):

```
== 187855_130bpm.mp3 @ 130 BPM
187855_130bpm.mp3                1.85    48000    2     -  mp3        196.5    18.8     0.19     0     None   -11.57    8.76     130  G major       1  FAIL
    FAIL: lossy codec, peak 0.19 dBFS
    note: below full range: 18.8 kHz
== 201920_128bpm.mp3 @ 128 BPM
201920_128bpm.mp3                1.88    48000    2     -  mp3        200.0    18.8    -0.97     0     None   -17.88    13.91     128  D# major      1  FAIL
    FAIL: lossy codec
    note: below full range: 18.8 kHz
== 629138_lofi95.mp3 @ 95 BPM
629138_lofi95.mp3               20.21    44100    2     -  mp3        198.0     8.5    -0.93     0     None    -17.8    13.86   95.24  G# minor      8  FAIL
    FAIL: lossy codec
    note: narrow-band loop: 8.5 kHz
```

JSON for the exact bar residuals:

```json
{"duration_s": 1.846, "bpm_audio": 130, "key_audio": "G major", "confidence": 0.563,
 "bars_actual": 1.0, "bars_trimmed": 0.997, "bar_residual_ms": 0.0, "bar_ok": true,
 "failures": ["lossy codec", "peak 0.19 dBFS"]}
{"duration_s": 1.875, "bpm_audio": 128, "key_audio": "D# major", "confidence": 0.598,
 "bars_actual": 1.0, "bars_trimmed": 0.992, "bar_residual_ms": 0.0, "bar_ok": true,
 "failures": ["lossy codec"]}
{"duration_s": 20.211, "bpm_audio": 95.24, "key_audio": "G# minor", "confidence": 0.455,
 "bars_actual": 8.0, "bars_trimmed": 7.996, "bar_residual_ms": 0.0, "bar_ok": true,
 "failures": ["lossy codec"]}
```