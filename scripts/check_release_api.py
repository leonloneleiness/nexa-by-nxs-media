"""One minimal live request using release credentials, never echoing keys/errors."""
from pathlib import Path
from dotenv import dotenv_values
from google import genai
from google.genai import types

root = Path(__file__).resolve().parents[1]
values = dotenv_values(root / 'release/windows-portable/NEXA/.env')
try:
    with genai.Client(api_key=values['GEMINI_API_KEY'],
                      http_options=types.HttpOptions(timeout=15000,
                          retry_options=types.HttpRetryOptions(attempts=1))) as client:
        response = client.models.generate_content(
            model=values['GEMINI_MODEL'], contents='Reply with OK only.',
            config=types.GenerateContentConfig(max_output_tokens=32,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)))
    ok = bool(response.text)
    print('AI request succeeded:', ok)
    raise SystemExit(0 if ok else 1)
except Exception as exc:
    print('AI request failed. Type:', type(exc).__name__, 'HTTP code:', getattr(exc, 'code', None))
    raise SystemExit(1)
