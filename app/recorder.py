import threading
from datetime import datetime
from pathlib import Path

import numpy as np
import pyaudiowpatch as paw
import sounddevice as sd
import soundfile as sf


class AudioRecorder:
    """Record system audio (WASAPI loopback) and microphone using PyAudioWPatch."""

    def __init__(self, output_dir: Path, mic_device_index: int = -1, system_device_index: int = -1):
        self.output_dir = Path(output_dir)
        self.mic_device_index = mic_device_index if mic_device_index >= 0 else sd.query_default_input_device()["index"]
        self.system_device_index = system_device_index

        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.system_path = self.output_dir / f"{self.timestamp}_system.wav"
        self.mic_path = self.output_dir / f"{self.timestamp}_mic.wav"
        self.mixed_path = self.output_dir / f"{self.timestamp}_mixed.wav"

        self._recording = False
        self._system_audio: list[np.ndarray] = []
        self._mic_audio: list[np.ndarray] = []
        self._lock = threading.Lock()
        self.system_sample_rate = 48000
        self.mic_sample_rate = 48000
        self.system_channels = 2
        self.mic_channels = 2

    def start(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._recording = True
        self._system_audio = []
        self._mic_audio = []

        # Get system audio (WASAPI loopback) using PyAudioWPatch
        self._system_thread = threading.Thread(target=self._record_system_audio, daemon=True)
        self._system_thread.start()

        # Get microphone using sounddevice
        self._mic_thread = threading.Thread(target=self._record_mic_audio, daemon=True)
        self._mic_thread.start()

    def _record_system_audio(self) -> None:
        """Record system audio using PyAudioWPatch WASAPI loopback."""
        p = paw.PyAudio()
        try:
            # Get default loopback device
            loopback = p.get_default_wasapi_loopback()
            device_index = loopback["index"]
            self.system_sample_rate = int(loopback["defaultSampleRate"])
            self.system_channels = int(loopback.get("maxInputChannels", 2))
            if self.system_channels < 1:
                self.system_channels = 2

            # Open stream
            stream = p.open(
                input=True,
                channels=self.system_channels,
                format=paw.paFloat32,
                rate=self.system_sample_rate,
                input_device_index=device_index,
                frames_per_buffer=self.system_sample_rate // 10,
            )

            while self._recording:
                # Read ~0.1 seconds of audio
                raw_data = stream.read(self.system_sample_rate // 10, exception_on_overflow=False)
                audio = np.frombuffer(raw_data, dtype=np.float32)
                audio = audio.reshape(-1, self.system_channels)
                with self._lock:
                    self._system_audio.append(audio.copy())

            stream.stop_stream()
            stream.close()
        finally:
            p.terminate()

    def _record_mic_audio(self) -> None:
        """Record microphone using sounddevice."""
        try:
            device_info = sd.query_devices(self.mic_device_index)
            self.mic_sample_rate = int(device_info["default_samplerate"])
            self.mic_channels = min(2, device_info["max_input_channels"])
            if self.mic_channels < 1:
                self.mic_channels = 1

            def callback(indata, frames, time_info, status):
                if self._recording:
                    with self._lock:
                        self._mic_audio.append(indata.copy())

            with sd.InputStream(
                device=self.mic_device_index,
                samplerate=self.mic_sample_rate,
                channels=self.mic_channels,
                dtype=np.float32,
                callback=callback,
                blocksize=self.mic_sample_rate // 10,
            ):
                while self._recording:
                    sd.sleep(100)
        except Exception as e:
            print(f"Mic recording error: {e}")

    def is_recording(self) -> bool:
        return self._recording

    def stop(self) -> tuple[Path, Path]:
        """Stop recording and save audio files."""
        self._recording = False

        # Wait for threads to finish
        if hasattr(self, "_system_thread"):
            self._system_thread.join(timeout=2)
        if hasattr(self, "_mic_thread"):
            self._mic_thread.join(timeout=2)

        # Combine and save system audio
        if self._system_audio:
            system_data = np.concatenate(self._system_audio, axis=0)
            sf.write(self.system_path, system_data, self.system_sample_rate)
        else:
            # Create empty file marker
            self.system_path.touch()

        # Combine and save mic audio
        if self._mic_audio:
            mic_data = np.concatenate(self._mic_audio, axis=0)
            sf.write(self.mic_path, mic_data, self.mic_sample_rate)
        else:
            # Create empty file marker
            self.mic_path.touch()

        return self.system_path, self.mic_path


def list_system_audio_devices() -> list[dict]:
    """List available WASAPI loopback devices."""
    p = paw.PyAudio()
    try:
        devices = []
        for d in p.get_loopback_device_info_generator():
            devices.append({
                "index": d["index"],
                "name": d["name"],
                "sample_rate": int(d["defaultSampleRate"]),
            })
        return devices
    finally:
        p.terminate()


def get_default_system_device() -> dict:
    """Get default WASAPI loopback device info."""
    p = paw.PyAudio()
    try:
        d = p.get_default_wasapi_loopback()
        return {
            "index": d["index"],
            "name": d["name"],
            "sample_rate": int(d["defaultSampleRate"]),
        }
    finally:
        p.terminate()


def list_microphone_devices() -> list[dict]:
    """List available microphone devices using sounddevice."""
    devices = []
    for d in sd.query_devices():
        if d["max_input_channels"] > 0 and d["hostapi"] in (0, 1, 2):  # MME, DirectSound, WASAPI
            devices.append({
                "index": d["index"],
                "name": d["name"],
                "sample_rate": int(d["default_samplerate"]),
            })
    return devices


def get_default_microphone_device() -> dict:
    """Get default microphone device info."""
    d = sd.query_default_input()
    return {
        "index": d["index"],
        "name": d["name"],
        "sample_rate": int(d["default_samplerate"]),
    }