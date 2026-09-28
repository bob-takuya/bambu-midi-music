# bambu-midi-music

Make a **Bambu Lab 3D printer play music**. Converts MIDI to the printer's buzzer G-code (`M1006`) and back, and can swap the start/finish jingle inside an existing print file.

MIDI を Bambu Lab プリンタのブザー用 G-code に変換して、プリンタに曲を演奏させるツールです。既存の G-code の開始音・終了音の差し替えや、G-code → MIDI の逆変換もできます。

## Status

**Small working script / experiment.** A single-file CLI that does the conversions below. The `M1006` note format and the sound-block markers are taken from Bambu Studio-generated G-code for the A1 mini (the author's printer); other Bambu models are untested. No tests.

✅ **Works**
- MIDI → standalone sound-only G-code
- MIDI → replace the finish (default) or start sound block inside an existing Bambu G-code file
- G-code → MIDI (reads the finish block, else the start block, else every `M1006` line) to hear what a file will play
- Chords of up to 3 simultaneous notes; gaps over 30 ms become rests; repeated identical chords are merged

🚧 **Partial or rough**
- Timing is approximate: notes are grouped by start time (±10 ms) and played chord by chord, so overlapping / legato lines drift
- Only the first tempo event in the MIDI file is used; tempo changes are ignored

📝 **Not implemented yet**
- Tempo change / transpose on MIDI → G-code (`--bpm` only affects G-code → MIDI)
- Per-note dynamics (all notes get the single `--volume` value)
- Choosing which 3 voices to keep

⚠️ **Known issues & limitations**
- When more than 3 notes start together, the **lowest** 3 are kept — a melody on top can disappear
- Each note is capped at 1 s (`B100` × 10 ms); longer notes are cut short
- `--replace` only works if the file contains Bambu's `;=====printer finish  sound=====` / `;=====start printer sound=====` markers; otherwise it prints a warning and writes the file unchanged
- Standalone G-code has a minimal header; how you get it onto the printer (and whether your firmware accepts it) is untested beyond the author's setup

## Background

Made in December 2025 — the first step of treating G-code as a score.

## Usage

```bash
pip install mido MIDIUtil

# MIDI → sound-only G-code
python bambu_midi_converter.py music.mid -o test.gcode
# replace the finish (or --type start) sound of an existing print
python bambu_midi_converter.py music.mid --replace Cube.gcode -o Cube_new.gcode
python bambu_midi_converter.py music.mid --replace Cube.gcode -o Cube_new.gcode --type start
# buzzer volume 0-100 (default 30)
python bambu_midi_converter.py music.mid -o out.gcode --volume 50
# G-code → MIDI (to check what a file will play); --bpm sets the output MIDI tempo
python bambu_midi_converter.py print.gcode -o sound.mid --bpm 120
```

`mido` is needed for MIDI → G-code, `MIDIUtil` for G-code → MIDI. MIDI files and generated G-code are not included (bring your own tunes).

## Related

- [shodo-printer](https://github.com/bob-takuya/shodo-printer) — another experiment in making a Bambu printer do something other than printing parts (brush-like calligraphy)

## License

MIT — see [LICENSE](LICENSE).
