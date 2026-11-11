"""Dialogue bridge protocol units: downsample, request gating, bounded queue."""
import importlib.util
import json
import queue
import struct
import unittest
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location(
    'dialogue_bridge', Path(__file__).with_name('dialogue_bridge.py'))
bridge_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge_mod)
downsample_16k = bridge_mod.downsample_16k
DialogueBridge = bridge_mod.DialogueBridge


def stereo_chunk(values, channel=1):
    """Interleave L/R s16 frames with the given samples on `channel`."""
    out = bytearray()
    for value in values:
        left, right = (0, value) if channel == 1 else (value, 0)
        out += struct.pack('<hh', left, right)
    return bytes(out)


class FakeAudio:
    def __init__(self):
        self.active = True
        self.dialogue_mode = False
        self.backend = SimpleNamespace(playback_device='null')
    def suppressed(self):
        return False


class DownsampleTests(unittest.TestCase):
    def test_length_matches_16k_thirds(self):
        raw = stereo_chunk([100] * 96)          # 96 frames @48k -> 32 @16k
        data = downsample_16k(raw)
        self.assertEqual(len(data), 64)
        self.assertEqual(struct.unpack('<32h', data), (100,) * 32)

    def test_averages_each_group_of_three(self):
        raw = stereo_chunk([300, 300, 301, -90, -90, -93])
        data = downsample_16k(raw)
        self.assertEqual(struct.unpack('<2h', data), (300, -91))

    def test_only_right_channel_is_sent(self):
        raw = struct.pack('<8h', 5000, 300, 5000, 300, 5000, 300, 5000, 300)
        data = downsample_16k(raw)
        self.assertEqual(struct.unpack('<1h', data), (300,))


class BridgeProtocolTests(unittest.TestCase):
    def setUp(self):
        self.audio = FakeAudio()
        self.quacks = []
        self.hub = DialogueBridge(self.audio, self.quacks.append,
                                  clock=lambda: 0.0, path='/unused/dialogue.sock')
        self.hub.enabled = True

    def test_requires_active_dialogue_for_output_requests(self):
        self.hub.enabled = False
        for request in ({'method': 'tts', 'data': 'AAAA'}, {'method': 'tts_end'},
                        {'method': 'quack', 'tag': 'greet'}):
            self.assertFalse(self.hub._handle(request)['ok'], request)
        self.assertTrue(self.hub._handle({'method': 'ping'})['ok'])

    def test_rejects_bad_payloads_and_unknown_methods(self):
        for request in ({'method': 'tts'}, {'method': 'tts', 'data': ''},
                        {'method': 'tts', 'data': 123},
                        {'method': 'quack'}, {'method': 'quack', 'tag': 'x' * 40},
                        {'method': 'robot.do'}, 'not-an-object'):
            self.assertFalse(self.hub._handle(request)['ok'], request)

    def test_quack_reaches_the_native_sound_path(self):
        self.assertTrue(self.hub._handle({'method': 'quack', 'tag': 'greet'})['ok'])
        self.assertEqual(self.quacks, ['greet'])
        self.hub.quack = lambda tag: (_ for _ in ()).throw(RuntimeError('robotd away'))
        self.assertFalse(self.hub._handle({'method': 'quack', 'tag': 'greet'})['ok'])

    def test_feed_drops_oldest_when_studio_stalls(self):
        self.hub.client = object()
        big = stereo_chunk([100] * 4800)         # 100 ms chunks
        for _ in range(8):                        # ~800 ms >> MAX_QUEUE_BYTES/3
            self.hub.feed(big)
        self.assertLessEqual(self.hub.pcm_bytes, bridge_mod.MAX_QUEUE_BYTES)

    def test_feed_ignored_without_client_or_switch(self):
        self.hub.client = None
        self.hub.feed(stereo_chunk([10] * 96))
        self.assertEqual(self.hub.pcm.qsize(), 0)
        self.hub.client = object()
        self.hub.enabled = False
        self.hub.feed(stereo_chunk([10] * 96))
        self.assertEqual(self.hub.pcm.qsize(), 0)

    def test_status_is_bounded_and_public(self):
        status = self.hub.status()
        self.assertEqual(set(status), {'dialogue', 'bridge_client'})
        self.assertTrue(status['dialogue'])


if __name__ == '__main__':
    unittest.main()
