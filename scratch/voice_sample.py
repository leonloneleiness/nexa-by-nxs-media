import sys, wave
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from nexa.audio import voice_fx
from nexa.audio.tts import OUT_SR, EdgeBackend, trim_silence
text = "Chào anh Sơn, em là Nexa. Em đã mở YouTube và bật playlist anh yêu cầu rồi ạ."
x, sr = EdgeBackend("en-US-AndrewMultilingualNeural", 5, 0).synth(text)
for name, fx in (("andrew_clean", "none"), ("andrew_jarvis", "jarvis")):
    y = trim_silence(voice_fx.apply(fx, x, OUT_SR, 0.5), OUT_SR)
    with wave.open(str(Path(__file__).parent / f"{name}.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(OUT_SR)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())
    print(name, round(y.size / OUT_SR, 2), "s")
