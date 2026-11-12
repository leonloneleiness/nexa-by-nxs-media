"""Offline synthesized VI/EN audio smoke test. Never executes recognized actions.

Run synthesis and recognition in separate processes (WinRT/Whisper DLL isolation).
This is synthetic speech, not a microphone accuracy benchmark.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PAIRS = (
    ("Mở Notepad", "Open Notepad"),
    ("Đặt âm lượng ba mươi phần trăm", "Set volume to thirty percent"),
    ("Chụp màn hình", "Take a screenshot"),
    ("Mở cài đặt", "Open settings"),
    ("Chạy thử code", "Run code tests"),
    ("Chọn bài học con lắc đơn", "Select lesson pendulum"),
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("synth", "recognize"))
    ap.add_argument("--out", type=Path, default=ROOT/"scratch"/"bilingual_audio_audit")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = args.out/"manifest.json"
    if args.mode == "synth":
        import numpy as np
        from winrt.windows.media.speechsynthesis import SpeechSynthesizer
        from nexa.audio.tts import WinRTBackend, SapiBackend
        from nexa.research.corpus import write_wav
        from scripts.asr_synth import to_16k
        try:
            voices = list(SpeechSynthesizer.all_voices)
        except OSError:
            voices = []
        rows = []
        for language, column in (("vi",0), ("en",1)):
            voice = next((v for v in voices if v.language.lower().startswith(language)), None)
            if voice is None:
                if language == "vi":
                    import shutil
                    base = ROOT/"data"/"asr_synth"
                    cached = [json.loads(line) for line in (base/"manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
                    for i, row in enumerate(cached[:len(PAIRS)]):
                        path = args.out/f"vi-{i}.wav"
                        shutil.copyfile(base/row["audio"], path)
                        rows.append({"language":"vi", "text":row["reference"],"audio":path.name,"voice":row["speaker"] + " (cached synthetic)"})
                    continue
                backend = SapiBackend()
                backend._voice = lambda sp: next((v for v in sp.GetVoices() if v.GetAttribute("Language").lower() == "409"), None)
                voice_name = "SAPI English (offline)"
            else:
                backend = WinRTBackend("", 0)
                backend._voice = lambda voice=voice: voice
                voice_name = voice.display_name
            for i, pair in enumerate(PAIRS):
                audio, sr = backend.synth(pair[column])
                pad = np.zeros(4800, np.float32)
                path = args.out/f"{language}-{i}.wav"
                write_wav(path, np.concatenate([pad, to_16k(audio,sr), pad]))
                rows.append({"language":language,"text":pair[column],"audio":path.name,"voice":voice_name})
        manifest.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Created {len(rows)} offline synthetic utterances.")
        return 0

    from faster_whisper import WhisperModel
    from nexa.audio.stt import SpeechRecognizer
    from nexa.ai.intent_router import IntentRouter
    from nexa.ai.tool_registry import build_registry
    from nexa.research.corpus import read_wav
    from nexa.utils.config import Config
    model_paths = list((ROOT/"models"/"whisper"/"models--Systran--faster-whisper-small"/"snapshots").glob("*/model.bin"))
    if not model_paths:
        raise RuntimeError("Cached small model missing; no downloads are performed.")
    cfg = Config(settings_path=args.out/"settings.yaml", gestures_path=args.out/"gestures.yaml", load_env=False)
    recognizer = SpeechRecognizer(cfg, ROOT/"models")
    recognizer._model = WhisperModel(str(model_paths[0].parent), device="cpu", compute_type="int8", cpu_threads=4,
                                     local_files_only=True)
    router = IntentRouter(registry=build_registry(cfg))
    rows = json.loads(manifest.read_text(encoding="utf-8"))
    for row in rows:
        audio, sr = read_wav(args.out/row["audio"])
        res = recognizer.transcribe(audio, sr)
        expected, actual = router.route(row["text"]), router.route(res.text)
        row.update(recognized=res.text, accepted=res.ok, expected=expected.calls, actual=actual.calls,
                   passed=res.ok and actual.kind == expected.kind and actual.calls == expected.calls)
        print(f"{row['language']} {row['audio']}: {'PASS' if row['passed'] else 'FAIL'}", flush=True)
    report = {"model":"small / CPU int8", "language":"auto", "synthetic":True,
              "passed":sum(r["passed"] for r in rows),"total":len(rows),"rows":rows}
    (args.out/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k != "rows"}))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
