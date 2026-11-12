"""Minimal live requests using release credentials; never echo keys or response errors."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--payload', type=Path, default=ROOT / 'release/windows-portable/NEXA')
    parser.add_argument('--report', type=Path, default=ROOT / 'release/verification/api.json')
    parser.add_argument('--active-only', action='store_true')
    args = parser.parse_args()
    values = dotenv_values(args.payload / '.env')
    provider = values.get('NEXA_AI_PROVIDER', 'gemini')
    results = {}
    for name, key in (('openai', 'OPENAI_API_KEY'), ('gemini', 'GEMINI_API_KEY')):
        if args.active_only and name != provider:
            continue
        if not values.get(key) or values[key].startswith('YOUR_'):
            continue
        try:
            if name == 'openai':
                from openai import OpenAI
                with OpenAI(api_key=values[key], base_url=values.get('OPENAI_BASE_URL'),
                            timeout=45, max_retries=0) as client:
                    response = client.chat.completions.create(model=values['OPENAI_MODEL'],
                        messages=[{'role': 'user', 'content': 'Reply with OK only.'}], max_tokens=32)
                ok = bool(response.choices and response.choices[0].message.content)
            else:
                from google import genai
                from google.genai import types
                with genai.Client(api_key=values[key], http_options=types.HttpOptions(timeout=30000,
                        retry_options=types.HttpRetryOptions(attempts=1))) as client:
                    response = client.models.generate_content(model=values['GEMINI_MODEL'],
                        contents='Reply with OK only.', config=types.GenerateContentConfig(max_output_tokens=32,
                            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)))
                ok = bool(response.text)
            results[name] = {'ok': ok}
        except Exception as exc:
            results[name] = {'ok': False, 'error_type': type(exc).__name__,
                             'http_code': getattr(exc, 'status_code', getattr(exc, 'code', None))}
    report = {'ok': bool(results) and all(r['ok'] for r in results.values()) and provider in results,
              'active_provider': provider, 'providers': results}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
