"""List models or test one synthetic card without displaying credentials or card contents."""
from __future__ import annotations
import argparse
import asyncio
import io
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import anthropic
from dotenv import load_dotenv, set_key
from fastapi import HTTPException
from PIL import Image, ImageDraw, ImageFont


def synthetic_card() -> tuple[bytes, dict[str, str]]:
    fields = {
        "name": "Alex Example", "company_name": "Example Labs", "department": "Engineering",
        "title": "Software Engineer", "email": "alex@example.test", "phone": "+1 202 555 0147",
        "address": "123 Example Street", "website": "https://example.test",
    }
    image = Image.new("RGB", (1100, 650), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 34)
    for index, value in enumerate(fields.values()):
        draw.text((50, 30 + index * 73), value, fill="#183c44", font=font)
    output = io.BytesIO()
    image.save(output, "PNG")
    return output.getvalue(), fields


async def run(args) -> int:
    load_dotenv(ROOT / ".env", override=False)
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        print("ANTHROPIC_API_KEY is empty in .env.")
        return 2
    try:
        async with anthropic.AsyncAnthropic(api_key=key, timeout=20, max_retries=0) as client:
            models = [model async for model in client.models.list(limit=100)]
    except anthropic.APIError as exc:
        print("Model listing failed:", type(exc).__name__, "(credentials and raw response omitted)")
        return 1
    models.sort(key=lambda item: str(item.created_at), reverse=True)
    print("Available model IDs:")
    for model in models:
        print(" -", model.id)
    current = os.getenv("ANTHROPIC_MODEL", "").strip()
    if args.select_model and not current:
        candidates = [m for m in models if "opus" in m.id] or [m for m in models if "sonnet" in m.id] or models
        if not candidates:
            print("No models available.")
            return 1
        current = candidates[0].id
        set_key(ROOT / ".env", "ANTHROPIC_MODEL", current)
        os.environ["ANTHROPIC_MODEL"] = current
        print("Selected model:", current)
    if not args.smoke_test:
        return 0
    if not current:
        print("Set ANTHROPIC_MODEL or pass --select-model.")
        return 2
    from app.ai import extract_fields
    image_bytes, expected = synthetic_card()
    try:
        fields = await extract_fields(image_bytes, "image/png")
    except HTTPException as exc:
        print("Synthetic image extraction failed:", exc.status_code, exc.detail.get("code", "unknown"))
        return 1
    comparisons = {key: fields[key] == value for key, value in expected.items()}
    output_dir = ROOT / "test-inputs"
    output_dir.mkdir(exist_ok=True)
    (output_dir / "synthetic-card.png").write_bytes(image_bytes)
    (output_dir / "synthetic-ai-result.json").write_text(
        json.dumps({"model": current, "expected": expected, "actual": fields, "matches": comparisons}, indent=2),
        encoding="utf-8",
    )
    print("Synthetic card exact matches:", sum(comparisons.values()), "/", len(comparisons))
    print("Field results:", comparisons)
    print("Local details: test-inputs/synthetic-ai-result.json (gitignored)")
    return 0 if all(comparisons.values()) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--select-model", action="store_true", help="Choose newest available Opus, then Sonnet, only if model is empty.")
    parser.add_argument("--smoke-test", action="store_true", help="Send one synthetic image to the provided API.")
    raise SystemExit(asyncio.run(run(parser.parse_args())))
