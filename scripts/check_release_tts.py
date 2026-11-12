"""Synthesize one fixed sentence through the release voice; do not play or save audio."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from nexa.audio.tts import EdgeBackend
    import numpy as np
    import yaml

    parser = argparse.ArgumentParser()
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    settings = yaml.safe_load((args.payload / 'config/settings.example.yaml').read_text(encoding='utf-8'))
    tts = settings['tts']
    try:
        samples, rate = EdgeBackend(tts['edge_voice'], tts['rate'], tts['edge_pitch_hz']).synth('Xin chào. NEXA đã sẵn sàng.')
        report = {'ok': len(samples) > rate and bool(np.isfinite(samples).all()),
                  'voice': tts['edge_voice'], 'sample_rate': rate, 'audio_seconds': round(len(samples) / rate, 2),
                  'played_audio': False, 'saved_audio': False}
    except Exception as exc:
        report = {'ok': False, 'error_type': type(exc).__name__}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
