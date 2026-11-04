import hashlib
import math
import struct

from .tempo import AnalysisError, estimate_bpm

SAMPLE_RATE = 11025
FRAME_SIZE = 8192
HOP_SIZE = FRAME_SIZE
PITCH_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
MAJOR_PROFILE = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
MINOR_PROFILE = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)


def _fft(values):
    size = len(values)
    output = [complex(value, 0.0) for value in values]
    j = 0
    for i in range(1, size):
        bit = size >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            output[i], output[j] = output[j], output[i]

    length = 2
    while length <= size:
        angle = -2.0 * math.pi / length
        root = complex(math.cos(angle), math.sin(angle))
        half = length >> 1
        for start in range(0, size, length):
            factor = 1.0 + 0.0j
            for offset in range(half):
                even = output[start + offset]
                odd = output[start + offset + half] * factor
                output[start + offset] = even + odd
                output[start + offset + half] = even - odd
                factor *= root
        length <<= 1
    return output


def _cosine(left, right):
    left_energy = math.sqrt(sum(value * value for value in left))
    right_energy = math.sqrt(sum(value * value for value in right))
    if left_energy == 0 or right_energy == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_energy * right_energy)


def _chord_for(chroma):
    best = None
    for root in range(12):
        for mode, intervals in (("major", (0, 4, 7)), ("minor", (0, 3, 7))):
            template = [0.0] * 12
            for interval in intervals:
                template[(root + interval) % 12] = 1.0
            score = _cosine(chroma, template)
            if best is None or score > best[0]:
                best = (score, root, mode)
    if best is None or best[0] < 0.58:
        return None
    quality = "" if best[2] == "major" else "m"
    return f"{PITCH_NAMES[best[1]]}{quality}", best[0]


def _dominant_key(chroma):
    candidates = []
    for root in range(12):
        for mode, profile in (("major", MAJOR_PROFILE), ("minor", MINOR_PROFILE)):
            rotated = profile[-root:] + profile[:-root] if root else profile
            candidates.append((_cosine(chroma, rotated), root, mode))
    _, root, mode = max(candidates)
    return f"{PITCH_NAMES[root]} {mode}"


def analyze_harmony(samples, sample_rate=SAMPLE_RATE):
    if sample_rate != SAMPLE_RATE:
        raise AnalysisError("El análisis armónico requiere audio a 11.025 Hz.")
    frame_size = min(FRAME_SIZE, 1 << (len(samples) - 1).bit_length())
    if frame_size < 2048:
        raise AnalysisError("El fragmento es demasiado corto para analizar acordes.")
    if frame_size > FRAME_SIZE:
        frame_size = FRAME_SIZE
    hop = min(HOP_SIZE, frame_size)
    window = [0.5 - 0.5 * math.cos(2.0 * math.pi * index / (frame_size - 1)) for index in range(frame_size)]
    aggregate = [0.0] * 12
    frames = []
    last_start = max(0, len(samples) - frame_size)
    starts = list(range(0, last_start + 1, hop))
    if not starts or starts[-1] != last_start:
        starts.append(last_start)

    for start in starts:
        segment = samples[start : start + frame_size]
        if len(segment) < frame_size:
            segment = list(segment) + [0.0] * (frame_size - len(segment))
        spectrum = _fft([segment[index] * window[index] for index in range(frame_size)])
        chroma = [0.0] * 12
        for bin_index in range(8, frame_size // 2):
            frequency = bin_index * SAMPLE_RATE / frame_size
            if frequency > 5000:
                break
            magnitude = abs(spectrum[bin_index])
            if magnitude < 1e-8:
                continue
            midi_note = round(69 + 12 * math.log2(frequency / 440.0))
            if 0 <= midi_note <= 108:
                chroma[midi_note % 12] += magnitude
        for pitch_class, magnitude in enumerate(chroma):
            aggregate[pitch_class] += magnitude
        chord = _chord_for(chroma)
        frames.append((start / SAMPLE_RATE, chord[0] if chord else None))
        del spectrum, segment, chroma

    key = _dominant_key(aggregate)
    timeline = []
    for index, (start, chord_name) in enumerate(frames):
        if chord_name is None:
            continue
        end = frames[index + 1][0] if index + 1 < len(frames) else len(samples) / SAMPLE_RATE
        if timeline and timeline[-1]["chord"] == chord_name and abs(timeline[-1]["end_seconds"] - start) < 0.1:
            timeline[-1]["end_seconds"] = round(end, 2)
        else:
            timeline.append({
                "start_seconds": round(start, 2),
                "end_seconds": round(end, 2),
                "chord": chord_name,
            })
    return key, timeline, aggregate


def fingerprint(profile):
    normalized = [value / max(profile, default=1.0) for value in profile]
    quantized = bytes(max(0, min(255, round(value * 255))) for value in normalized)
    return hashlib.sha256(b"songo-chroma-v1:" + quantized).hexdigest()


def analyze_music(samples, sample_rate=SAMPLE_RATE, advanced=False):
    bpm = estimate_bpm(samples, sample_rate)
    result = {
        "bpm": bpm,
        "duration_seconds": round(len(samples) / sample_rate, 1),
        "message": "Tempo estimado. El resultado es orientativo.",
    }
    if advanced:
        key, chords, chroma = analyze_harmony(samples, sample_rate)
        result.update({
            "key": key,
            "chords": chords,
            "audio_fingerprint": fingerprint(chroma),
            "chroma_profile": [round(value, 6) for value in chroma],
        })
    return result
