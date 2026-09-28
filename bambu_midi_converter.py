#!/usr/bin/env python3
"""
Bambu Lab G-code ↔ MIDI 相互変換ツール

使い方:
    # MIDI → G-code (サウンドのみ再生用)
    python bambu_midi_converter.py input.mid -o output.gcode
    
    # G-code → MIDI
    python bambu_midi_converter.py input.gcode -o output.mid
    
    # 既存G-codeのサウンドを置換
    python bambu_midi_converter.py input.mid --replace existing.gcode -o modified.gcode
    
    # BPM指定（MIDI→G-code時）
    python bambu_midi_converter.py input.mid -o output.gcode --bpm 120
    
    # 開始音/終了音を指定
    python bambu_midi_converter.py input.mid -o output.gcode --type start
    python bambu_midi_converter.py input.mid -o output.gcode --type finish
"""

import argparse
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Tuple

try:
    from midiutil import MIDIFile
    HAS_MIDIUTIL = True
except ImportError:
    HAS_MIDIUTIL = False

try:
    import mido
    HAS_MIDO = True
except ImportError:
    HAS_MIDO = False


@dataclass
class Note:
    """単一の音符を表す"""
    pitch: int      # MIDIノート番号 (0 = 休符)
    duration: int   # 長さ (×10ms)
    velocity: int   # 音量 (0-100)


@dataclass 
class Chord:
    """最大3音の和音を表す"""
    notes: List[Note]  # 最大3つ
    
    def to_gcode(self) -> str:
        """G-code M1006 行に変換"""
        if not self.notes:
            return ""
        
        # 3音まで埋める
        notes = self.notes.copy()
        while len(notes) < 3:
            notes.append(Note(0, notes[0].duration, 100))
        
        n1, n2, n3 = notes[:3]
        return (f"M1006 A{n1.pitch} B{n1.duration} L{n1.velocity} "
                f"C{n2.pitch} D{n2.duration} M{n2.velocity} "
                f"E{n3.pitch} F{n3.duration} N{n3.velocity}")


class BambuGcodeConverter:
    """Bambu Lab G-code パーサー/ジェネレーター"""
    
    # M1006のパターン
    M1006_PATTERN = re.compile(
        r'M1006\s+'
        r'A(\d+)\s+B(\d+)\s+L(\d+)\s+'
        r'C(\d+)\s+D(\d+)\s+M(\d+)\s+'
        r'E(\d+)\s+F(\d+)\s+N(\d+)'
    )
    
    # サウンドブロックのパターン（開始音と終了音で形式が異なる）
    # 終了音: ;=====printer finish  sound=========
    # 開始音: ;=====start printer sound ===================
    FINISH_SOUND_PATTERN = re.compile(
        r'(;=+\s*printer\s+finish\s+sound\s*=+\s*\n)'
        r'((?:.*\n)*?)'
        r'(;=+\s*printer\s+finish\s+sound\s*=+)',
        re.IGNORECASE
    )
    START_SOUND_PATTERN = re.compile(
        r'(;=+\s*start\s+printer\s+sound\s*=+\s*\n)'
        r'((?:.*\n)*?)'
        r'(;=+\s*(?:start\s+printer\s+sound|avoid\s+end\s+stop)\s*=+)',
        re.IGNORECASE
    )
    
    @classmethod
    def parse(cls, gcode: str) -> List[Chord]:
        """G-codeからChordリストをパース"""
        chords = []
        for line in gcode.split('\n'):
            line = line.strip()
            match = cls.M1006_PATTERN.match(line)
            if match:
                values = [int(v) for v in match.groups()]
                notes = [
                    Note(values[0], values[1], values[2]),
                    Note(values[3], values[4], values[5]),
                    Note(values[6], values[7], values[8]),
                ]
                chords.append(Chord(notes))
        return chords
    
    @classmethod
    def extract_sounds(cls, gcode: str) -> Tuple[List[Chord], List[Chord]]:
        """G-codeから開始音と終了音を抽出"""
        start_chords = []
        finish_chords = []
        
        # 開始音を探す
        match = cls.START_SOUND_PATTERN.search(gcode)
        if match:
            start_chords = cls.parse(match.group(2))
        
        # 終了音を探す
        match = cls.FINISH_SOUND_PATTERN.search(gcode)
        if match:
            finish_chords = cls.parse(match.group(2))
        
        return start_chords, finish_chords
    
    @classmethod
    def generate_sound_block(cls, chords: List[Chord], sound_type: str = "finish") -> str:
        """サウンドブロックを生成"""
        if sound_type == "start":
            header = ";=====start printer sound ==================="
            footer = ";=====start printer sound ==================="
        else:
            header = ";=====printer finish  sound========="
            footer = ";=====printer finish  sound========="
        
        lines = [
            header,
            "M17",
            "M400 S1",
            "M1006 S1",
        ]
        
        for chord in chords:
            lines.append(chord.to_gcode())
        
        lines.extend([
            "M1006 W",
            footer,
        ])
        
        return '\n'.join(lines)
    
    @classmethod
    def generate_standalone_gcode(cls, chords: List[Chord], sound_type: str = "finish") -> str:
        """Bambu Lab Studioで読み込める完全なG-codeを生成"""
        
        # 最小限のヘッダー
        header = """; HEADER_BLOCK_START
; BambuStudio Sound Test
; model printing time: 0m 1s; total estimated time: 0m 1s
; HEADER_BLOCK_END

; CONFIG_BLOCK_START
; gcode_flavor = marlin
; CONFIG_BLOCK_END

; EXECUTABLE_BLOCK_START
"""
        
        # サウンドブロック
        sound_block = cls.generate_sound_block(chords, sound_type)
        
        # フッター
        footer = """
M400 S1
M18 X Y Z
; EXECUTABLE_BLOCK_END
"""
        
        return header + sound_block + footer
    
    @classmethod
    def replace_sound_in_gcode(cls, original_gcode: str, new_chords: List[Chord], 
                                sound_type: str = "finish") -> str:
        """既存G-code内のサウンドを置換"""
        
        new_block = cls.generate_sound_block(new_chords, sound_type)
        
        if sound_type == "start":
            pattern = cls.START_SOUND_PATTERN
        else:
            pattern = cls.FINISH_SOUND_PATTERN
        
        # マッチを確認
        match = pattern.search(original_gcode)
        if not match:
            print(f"警告: {sound_type}サウンドブロックが見つかりませんでした")
            return original_gcode
        
        # 置換実行
        result = pattern.sub(new_block, original_gcode)
        
        return result


class MidiConverter:
    """MIDI ↔ Chord 変換"""
    
    DEFAULT_VELOCITY = 30  # 30%
    DEFAULT_DURATION = 10  # 100ms
    
    @classmethod
    def midi_to_chords(cls, midi_path: str) -> List[Chord]:
        """MIDIファイルからChordリストに変換"""
        if not HAS_MIDO:
            raise ImportError("mido が必要です: pip install mido")
        
        mid = mido.MidiFile(midi_path)
        
        # テンポを取得（デフォルト120 BPM = 500000 μs/beat）
        tempo = 500000
        for track in mid.tracks:
            for msg in track:
                if msg.type == 'set_tempo':
                    tempo = msg.tempo
                    break
        
        # ticks → ms 変換係数
        ticks_per_beat = mid.ticks_per_beat
        ms_per_tick = tempo / 1000 / ticks_per_beat
        
        # 全トラックからノートイベントを収集
        events = []  # (time_ms, type, pitch, velocity)
        
        for track in mid.tracks:
            time_ms = 0
            for msg in track:
                time_ms += msg.time * ms_per_tick
                if msg.type == 'note_on' and msg.velocity > 0:
                    vel = int(msg.velocity / 127 * 100)
                    events.append((time_ms, 'on', msg.note, vel))
                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                    events.append((time_ms, 'off', msg.note, 0))
        
        events.sort(key=lambda x: (x[0], x[1] == 'on'))  # offを先に処理
        
        # ノートをChordに変換（開始時間でグループ化）
        note_groups = {}  # start_time -> [(pitch, duration, velocity), ...]
        active_notes = {}  # pitch -> (start_time, velocity)
        
        for time_ms, etype, pitch, vel in events:
            if etype == 'on':
                active_notes[pitch] = (time_ms, vel)
            elif etype == 'off' and pitch in active_notes:
                start_time, velocity = active_notes[pitch]
                duration_ms = time_ms - start_time
                
                # 開始時間でグループ化（10ms以内は同時発音）
                group_time = None
                for t in note_groups:
                    if abs(t - start_time) < 10:
                        group_time = t
                        break
                if group_time is None:
                    group_time = start_time
                    note_groups[group_time] = []
                
                note_groups[group_time].append((pitch, duration_ms, velocity))
                del active_notes[pitch]
        
        # 時間順にソートしてChordを生成
        chords = []
        sorted_times = sorted(note_groups.keys())
        
        for idx, start_time in enumerate(sorted_times):
            notes_data = note_groups[start_time]
            
            # 前のChordの終了時間との間に休符があるか確認
            if idx > 0:
                prev_time = sorted_times[idx - 1]
                prev_notes = note_groups[prev_time]
                # 前のChordの最長duration
                prev_end = prev_time + max(d for _, d, _ in prev_notes)
                gap = start_time - prev_end
                
                if gap > 30:  # 30ms以上の間隔なら休符を挿入
                    rest_duration = max(1, int(gap / 10))
                    chords.append(Chord([Note(0, rest_duration, 100)]))
            
            # 最大3音、音程でソート
            sorted_notes = sorted(notes_data, key=lambda x: x[0])[:3]
            
            # Chordを作成（各ノートのdurationを使用）
            chord_notes = []
            for pitch, duration_ms, velocity in sorted_notes:
                duration = max(1, min(100, int(duration_ms / 10)))
                chord_notes.append(Note(pitch, duration, velocity))
            
            chords.append(Chord(chord_notes))
        
        return cls._optimize_chords(chords)
    
    @classmethod
    def _optimize_chords(cls, chords: List[Chord]) -> List[Chord]:
        """連続する同一和音を統合、空のコードを除去"""
        if not chords:
            return []
        
        result = []
        for chord in chords:
            # 空でないノートがあるか確認
            has_sound = any(n.pitch > 0 for n in chord.notes)
            
            if not result:
                result.append(chord)
                continue
            
            prev = result[-1]
            prev_pitches = tuple(sorted(n.pitch for n in prev.notes))
            curr_pitches = tuple(sorted(n.pitch for n in chord.notes))
            
            if prev_pitches == curr_pitches and prev_pitches != (0, 0, 0):
                # 同じ和音なら duration を延長
                for n in prev.notes:
                    n.duration = min(100, n.duration + chord.notes[0].duration)
            else:
                result.append(chord)
        
        return result
    
    @classmethod
    def chords_to_midi(cls, chords: List[Chord], output_path: str, bpm: int = 120):
        """ChordリストからMIDIファイルを生成"""
        if not HAS_MIDIUTIL:
            raise ImportError("MIDIUtil が必要です: pip install MIDIUtil")
        
        midi = MIDIFile(1)
        track = 0
        channel = 0
        time = 0  # 拍単位
        
        midi.addTempo(track, 0, bpm)
        
        ms_per_beat = 60000 / bpm
        
        for chord in chords:
            # このChordの最大duration（休符含む）
            max_duration_ms = 0
            has_notes = False
            
            for note in chord.notes:
                duration_ms = note.duration * 10
                max_duration_ms = max(max_duration_ms, duration_ms)
                
                if note.pitch > 0:
                    has_notes = True
                    duration_beats = duration_ms / ms_per_beat
                    velocity = int(note.velocity * 127 / 100)
                    midi.addNote(track, channel, note.pitch, time, duration_beats, velocity)
            
            # 時間を進める（休符の場合もdurationを使う）
            if max_duration_ms > 0:
                time += max_duration_ms / ms_per_beat
        
        with open(output_path, 'wb') as f:
            midi.writeFile(f)


def gcode_to_midi(gcode_path: str, midi_path: str, bpm: int = 120):
    """G-codeファイルをMIDIに変換"""
    with open(gcode_path, 'r') as f:
        gcode = f.read()
    
    # まずサウンドブロックを探す
    start_chords, finish_chords = BambuGcodeConverter.extract_sounds(gcode)
    
    if finish_chords:
        chords = finish_chords
        print(f"終了音を検出")
    elif start_chords:
        chords = start_chords
        print(f"開始音を検出")
    else:
        # サウンドブロックがなければ全体からM1006をパース
        chords = BambuGcodeConverter.parse(gcode)
    
    if not chords:
        print("エラー: M1006コマンドが見つかりませんでした")
        return
    
    MidiConverter.chords_to_midi(chords, midi_path, bpm)
    print(f"変換完了: {gcode_path} → {midi_path}")
    print(f"  {len(chords)} 和音を変換")


def midi_to_gcode(midi_path: str, gcode_path: str, sound_type: str = "finish",
                  replace_path: Optional[str] = None, volume: int = 30):
    """MIDIファイルをG-codeに変換"""
    chords = MidiConverter.midi_to_chords(midi_path)
    
    if not chords:
        print("エラー: MIDIファイルからノートを抽出できませんでした")
        return
    
    # 音量を調整
    for chord in chords:
        for note in chord.notes:
            if note.pitch > 0:
                note.velocity = volume
    
    if replace_path:
        # 既存G-codeのサウンドを置換
        with open(replace_path, 'r') as f:
            original_gcode = f.read()
        gcode = BambuGcodeConverter.replace_sound_in_gcode(original_gcode, chords, sound_type)
        print(f"既存G-codeの{sound_type}サウンドを置換")
    else:
        # スタンドアロンG-codeを生成
        gcode = BambuGcodeConverter.generate_standalone_gcode(chords, sound_type)
    
    with open(gcode_path, 'w') as f:
        f.write(gcode)
    
    print(f"変換完了: {midi_path} → {gcode_path}")
    print(f"  {len(chords)} 和音を変換")


def main():
    parser = argparse.ArgumentParser(
        description='Bambu Lab G-code ↔ MIDI 相互変換ツール',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  # MIDIからG-code（サウンドテスト用）
  python bambu_midi_converter.py music.mid -o test.gcode
  
  # G-codeからMIDI
  python bambu_midi_converter.py print.gcode -o sound.mid
  
  # 既存G-codeのサウンドを置換
  python bambu_midi_converter.py music.mid --replace Cube.gcode -o Cube_new.gcode
"""
    )
    parser.add_argument('input', help='入力ファイル (.gcode または .mid/.midi)')
    parser.add_argument('-o', '--output', help='出力ファイル', required=True)
    parser.add_argument('--bpm', type=int, default=120, help='BPM (MIDI出力時、デフォルト: 120)')
    parser.add_argument('--type', choices=['start', 'finish'], default='finish',
                        help='サウンドタイプ (デフォルト: finish)')
    parser.add_argument('--volume', type=int, default=30,
                        help='音量 0-100 (デフォルト: 30)')
    parser.add_argument('--replace', metavar='GCODE',
                        help='このG-codeファイル内のサウンドを置換')
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_path = Path(args.output)
    
    if input_path.suffix.lower() == '.gcode':
        if not HAS_MIDIUTIL:
            print("エラー: MIDIUtil が必要です")
            print("  pip install MIDIUtil")
            return 1
        gcode_to_midi(str(input_path), str(output_path), args.bpm)
    
    elif input_path.suffix.lower() in ('.mid', '.midi'):
        if not HAS_MIDO:
            print("エラー: mido が必要です")
            print("  pip install mido")
            return 1
        midi_to_gcode(str(input_path), str(output_path), args.type, args.replace, args.volume)
    
    else:
        print(f"エラー: 未対応のファイル形式: {input_path.suffix}")
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())