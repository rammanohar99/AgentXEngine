"""
Quick test of google-genai SDK with API key.
Usage: python scripts/test_genai.py YOUR_API_KEY
"""

import asyncio
import sys


async def main(api_key: str) -> None:
    from google import genai

    client = genai.Client(api_key=api_key)

    print("Testing sync call...")
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents="Reply with exactly one word: hello",
    )
    print(f"  Sync OK: {response.text.strip()}")

    print("Testing async call...")
    response = await client.aio.models.generate_content(
        model="gemini-2.0-flash",
        contents="Reply with exactly one word: world",
    )
    print(f"  Async OK: {response.text.strip()}")

    print("\nAll tests passed. SDK is working.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_genai.py YOUR_API_KEY")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
