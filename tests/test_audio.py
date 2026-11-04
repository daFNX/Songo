import math
import struct
import unittest

from backend.services.audio import analyze_music


def make_c_major():
    sample_rate = 11025
    duration = 8
    samples = []
    frequencies = (261.63, 329.63, 392.0)
    for index in range(sample_rate * duration):
        time = index / sample_rate
        phase = time % 0.5
        envelope = 0.8 * math.exp(-phase * 35) if phase < 0.08 else 0.015
        sample = envelope * sum(
            math.sin(2 * math.pi * frequency * time) for frequency in frequencies
        ) / len(frequencies)
        samples.append(sample)
    return samples


class HarmonicAnalysisTests(unittest.TestCase):
    def test_extracts_key_chords_and_stable_fingerprint(self):
        result = analyze_music(make_c_major(), advanced=True)

        self.assertEqual(result["bpm"], 120)
        self.assertEqual(result["key"], "C major")
        self.assertTrue(result["chords"])
        self.assertTrue(any(item["chord"] == "C" for item in result["chords"]))
        self.assertEqual(len(result["audio_fingerprint"]), 64)
        self.assertRegex(result["audio_fingerprint"], r"^[0-9a-f]{64}$")

    def test_fingerprint_is_deterministic(self):
        samples = make_c_major()
        first = analyze_music(samples, advanced=True)
        second = analyze_music(samples, advanced=True)

        self.assertEqual(first["audio_fingerprint"], second["audio_fingerprint"])


if __name__ == "__main__":
    unittest.main()
