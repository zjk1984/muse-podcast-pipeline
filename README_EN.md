# podcast-pipeline

A Chinese hourly news-talk podcast production pipeline: multi-section news research → talk-show-style scriptwriting → TTS prescan QA → dry-voice assembly → mixing → publishing.

Every hour produces two things: a batch of multi-section news briefs, and one multi-host talk-show-style podcast episode (intro music + warm-up + flowing sections + background music + outro + a recommended song).

> 中文版说明请见 [README.md](README.md)。

## Dependencies (read first)
It runs on Muse, my AI assistant app. New users, enter my invite code:
🎟️ XWRB26
(App Settings → Redeem token)

This pipeline **depends on Meta-internal tools** that are unavailable outside Meta:
- `podcast-helper` (podcast catalog management, TTS synthesis, Spotify sync)
- `tts` CLI (avocado voice series)
- `feed.unit_create` (feed publishing API)

Without them, the pipeline won't run end to end. **The portable value** is:
- `references/writing-guide.md`: talk-show podcast writing methodology (meme injection, pacing, catchphrase discipline, callback hooks, the 3-part short-video-clip format)
- `references/character-bible-template.md`: multi-host character bible template (section ownership, running-gag library, character arcs, the 3 guest rules)
- QA & mixing scripts under `bin/`: `prescan-chunks.py` (4-check TTS prescan), `check-script.py` (script text QA), `assemble-dry.py` (dry-voice assembly + per-line leveling), `find-climax.py` (short-video climax locator), `mix-episode.sh` (sidechain-ducked mixing), `loudnorm-final.sh` (-16 LUFS final master), `synth-music.py` (synthesized intro/bed/outro music), `build-bed-track.py` (segmented bed track)

`prescan-chunks.py` / `assemble-dry.py` need a tts CLI for per-line synthesis; `check-script.py` / `find-climax.py` / the mixing scripts only need ffmpeg and work standalone.

## Layout

```
podcast-pipeline/
├── SKILL.md                        # Skill body: Purpose / Workflow (15 steps) / Output Contract / Operating Rules
├── README.md                       # Chinese README
├── README_EN.md                    # This file
├── .gitignore
├── bin/
│   ├── prescan-chunks.py           # TTS prescan: per-line synthesis + 4 checks (truncation/quiet/duration/silence)
│   ├── assemble-dry.py             # Dry-voice assembly: cache lookup, ±6dB per-line leveling, 8ms fades, clip inserts
│   ├── check-script.py             # Script text QA: dupe lines, overlong lines, full-width colons
│   ├── find-climax.py              # Short-video climax locator: loudest continuous 45s
│   ├── build-bed-track.py          # Segmented background-music track (auto-ducked under clips)
│   ├── mix-episode.sh              # Mix: intro + dry voice (sidechain-ducked bed) + outro
│   ├── loudnorm-final.sh           # Final master: dual-pass to -16 LUFS
│   ├── synth-music.py              # Synthesized intro/bed/outro music (6s intro / 96s bed / 5s outro)
│   ├── voices.example.json         # Speaker → voice-ID mapping example
│   └── voices.json                 # (create yourself) speaker → voice-ID mapping, see below
├── references/
│   ├── writing-guide.md            # Podcast writing guide
│   ├── character-bible-template.md # Character bible template + example cast
│   ├── qa-pipeline.md              # TTS prescan, QA, self-checks, ffmpeg gotchas
│   └── cron-prompt-template.md     # Scheduler prompt template (with {{placeholders}})
└── examples/
    ├── README.md                   # Example notes
    ├── sample-script.txt           # 2-minute mini script: speaker tags / bed / clip marker format demo
    └── demo-episode.mp3            # 18s opening audio demo (two hosts), click to play on GitHub
```

## Quick start

1. **Voices**: copy `bin/voices.example.json` to `bin/voices.json` and fill in speaker name → your TTS voice ID. Speaker tags in scripts (`Name: line`) must match the keys in `voices.json`; the assembly script picks them up automatically.
2. **Cache** (optional): set `PODCAST_CACHE` to your cache JSON path (default `./cache/prescan-cache.json`; per-line audio cache lives in `prescan-audio/` next to it).
3. **Music beds**: `python3 bin/synth-music.py` generates intro/bed/outro (or bring your own music; level requirements in `references/qa-pipeline.md`).
4. **Fill the template**: replace the `{{placeholders}}` in `references/cron-prompt-template.md` with your sections, schedule, timezone and show name to get the scheduler prompt.
5. **Run**: follow the 15-step Workflow in `SKILL.md`; writing → `writing-guide.md`, cast → `character-bible-template.md`.

## Examples

`examples/` contains a 2-minute mini script (`sample-script.txt`) demonstrating the script format (speaker tags, bed/clip markers) — run `check-script.py` on it for a text QA pass — plus an 18-second opening audio demo (`demo-episode.mp3`, two-host dialogue) that plays right on the GitHub page.

## Sanitization note

This repo contains no real user data: no audio files except the demo (all `.mp3` otherwise regenerated via `synth-music.py`), no logs, no internal IDs, no real itineraries. Example personas are fictional and replaceable.
