"""
Google Gen AI connectivity test (new SDK).
Run from repo root: python scripts/test_vertex.py
"""

import asyncio
import sys
import time

PROJECT = "k8s-terraform-lab"
LOCATION = "us-central1"
MODEL = "gemini-2.0-flash"


def test_1_sdk_import():
    print("\n[1] Importing google-genai SDK...")
    try:
        from google import genai
        from google.genai import types
        print(f"    ✓ google-genai imported successfully")
        return True
    except Exception as exc:
        print(f"    ✗ Import failed: {exc}")
        return False


def test_2_client_init():
    print("\n[2] Building Vertex AI client (ADC)...")
    try:
        from google import genai
        client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
        print(f"    ✓ Client created for project={PROJECT}")
        return client
    except Exception as exc:
        print(f"    ✗ Client init failed: {type(exc).__name__}: {exc}")
        return None


async def test_3_async_call(client):
    print(f"\n[3] Async generate_content with {MODEL}...")
    try:
        from google.genai import types
        start = time.time()
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=MODEL,
                contents="Reply with exactly one word: hello",
                config=types.GenerateContentConfig(max_output_tokens=10),
            ),
            timeout=20.0,
        )
        elapsed = round(time.time() - start, 2)
        print(f"    ✓ Response: '{response.text.strip()}' ({elapsed}s)")
        return True
    except asyncio.TimeoutError:
        print("    ✗ Timed out after 20s")
        return False
    except Exception as exc:
        print(f"    ✗ Failed: {type(exc).__name__}: {exc}")
        return False


def test_4_list_models(client):
    print("\n[4] Listing available models...")
    try:
        models = list(client.models.list())
        gemini_models = [m.name for m in models if "gemini" in m.name.lower()][:5]
        print(f"    ✓ Found {len(models)} models. Gemini models: {gemini_models}")
        return True
    except Exception as exc:
        print(f"    ✗ Failed: {type(exc).__name__}: {exc}")
        return False


if __name__ == "__main__":
    print("=" * 55)
    print("  Google Gen AI Connectivity Test")
    print(f"  Project: {PROJECT} | Model: {MODEL}")
    print("=" * 55)

    r1 = test_1_sdk_import()
    if not r1:
        sys.exit(1)

    client = test_2_client_init()
    if not client:
        sys.exit(1)

    r4 = test_4_list_models(client)
    r3 = asyncio.run(test_3_async_call(client))

    print("\n" + "=" * 55)
    all_ok = r1 and bool(client) and r3
    if all_ok:
        print("  ✓ All checks passed — ready to run the backend.")
    else:
        print("  ✗ Some checks failed.")
    sys.exit(0 if all_ok else 1)
