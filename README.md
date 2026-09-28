# bambu-midi-music

Make a **Bambu Lab 3D printer play music**. Converts MIDI to the printer's buzzer G-code (and back), and can swap the start/finish jingle inside an existing print file.
Made in December 2025 — the first step of treating G-code as a score.

MIDI を Bambu Lab プリンタのブザー用 G-code に変換して、プリンタに曲を演奏させるツールです。既存の G-code の開始音・終了音の差し替えや、G-code → MIDI の逆変換もできます。

## Usage
```bash
pip install mido midiutil

# MIDI → sound-only G-code
python bambu_midi_converter.py music.mid -o test.gcode
# replace the finish (or --type start) sound of an existing print
python bambu_midi_converter.py music.mid --replace Cube.gcode -o Cube_new.gcode
python bambu_midi_converter.py music.mid --replace Cube.gcode -o Cube_new.gcode --type start
# tempo
python bambu_midi_converter.py music.mid -o out.gcode --bpm 120
# G-code → MIDI (to check what a file will play)
python bambu_midi_converter.py print.gcode -o sound.mid
```

Tested on a Bambu Lab A1 mini. MIDI files and generated G-code are not included (bring your own tunes).

## License
MIT — see [LICENSE](LICENSE).
