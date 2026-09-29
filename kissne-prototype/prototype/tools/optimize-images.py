# -*- coding: utf-8 -*-
"""Optimize shipped Kissne prototype raster assets in-place.

PNG/JPEG -> WebP, preserves alpha, keeps conservative UI size caps, removes
verified-unused splash intermediates, rewrites runtime references, and emits a
small budget report. Safe to rerun.
"""
from __future__ import annotations

import json
from pathlib import Path
from PIL import Image, ImageOps

HERE = Path(__file__).resolve().parent
PROTOTYPE = HERE.parent
ASSETS = PROTOTYPE / "assets"
REAL = ASSETS / "real"
REPORT = ASSETS / "image-budget.json"
RASTER_EXTS = {".png", ".jpg", ".jpeg"}
TEXT_EXTS = {".js", ".json", ".html", ".css", ".md", ".py"}

# Verified against every prototype text file on 2026-09-21: not runtime inputs.
UNUSED_SPLASH = {
    "real/splash-generated/duo-strip.png",
    "real/splash-generated/fox-strip.png",
    "real/splash-generated/sheep-strip.png",
    "real/splash-generated/splash-logo.png",
    "real/splash-generated/frames/logo/frame-0.png",
    "real/splash-generated/frames/logo/frame-1.png",
    "real/splash-generated/frames/logo/frame-2.png",
    "real/splash-generated/frames/logo/frame-3.png",
}

def policy(rel: str):
    low = rel.lower()
    if "/stickers/" in low:
        return 256, 90
    if "/splash-generated/" in low:
        return None, 88
    name = Path(low).name
    if "avatar" in name or name.startswith(("fox-chat-", "user-avatar")):
        return 256, 90
    if "home-card" in name:
        return 720, 86
    return 512, 88

def resize_if_needed(im, max_side):
    if not max_side or max(im.size) <= max_side:
        return im
    out = im.copy()
    out.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return out

def has_useful_alpha(im):
    if "A" in im.getbands():
        return im.getchannel("A").getextrema()[0] < 255
    if im.mode == "P" and "transparency" in im.info:
        return im.convert("RGBA").getchannel("A").getextrema()[0] < 255
    return False

def optimize_one(src):
    rel = src.relative_to(ASSETS).as_posix()
    max_side, quality = policy(rel)
    before = src.stat().st_size
    try:
        with Image.open(src) as opened:
            im = ImageOps.exif_transpose(opened)
            alpha = has_useful_alpha(im)
            im = im.convert("RGBA" if alpha else "RGB")
            im = resize_if_needed(im, max_side)
            dst = src.with_suffix(".webp")
            tmp = dst.with_name(dst.name + ".tmp")
            kwargs = {"format": "WEBP", "quality": quality, "method": 6}
            if alpha:
                kwargs["exact"] = True
            im.save(tmp, **kwargs)
    except Exception as exc:
        print(f"! skip {rel}: {exc}")
        return None, before, before

    after = tmp.stat().st_size
    # Never replace with a larger file; 2% margin avoids format churn for near-ties.
    if after >= int(before * 0.98):
        tmp.unlink(missing_ok=True)
        print(f"= keep {rel}: {before} -> {after} bytes")
        return None, before, before
    if dst.exists():
        dst.unlink()
    tmp.replace(dst)
    src.unlink()
    print(f"+ {rel} -> {dst.relative_to(ASSETS).as_posix()}: {before} -> {after}")
    return dst, before, after

def rewrite_refs(mapping):
    changed = 0
    for path in PROTOTYPE.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTS:
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        try:
            old_text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new_text = old_text
        for old, new in mapping.items():
            new_text = new_text.replace(old, new)
            prefix = "real/splash-generated/"
            if old.startswith(prefix) and path.name == "screens-a.js":
                new_text = new_text.replace(old[len(prefix):], new[len(prefix):])
        if new_text != old_text:
            path.write_text(new_text, encoding="utf-8", newline="\n")
            changed += 1
            print("~ refs", path.relative_to(PROTOTYPE).as_posix())
    return changed

def count_rasters():
    files = [p for p in REAL.rglob("*")
             if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
    return len(files), sum(p.stat().st_size for p in files)

def main():
    if not REAL.is_dir():
        raise SystemExit(f"missing assets directory: {REAL}")
    before_count, before_bytes = count_rasters()

    removed = 0
    for rel in sorted(UNUSED_SPLASH):
        p = ASSETS / rel
        if p.exists():
            p.unlink()
            removed += 1
            print("- unused", rel)

    mapping = {}
    converted = 0
    for src in sorted(p for p in REAL.rglob("*")
                      if p.is_file() and p.suffix.lower() in RASTER_EXTS):
        old_rel = src.relative_to(ASSETS).as_posix()
        dst, _before, _after = optimize_one(src)
        if dst is not None:
            mapping[old_rel] = dst.relative_to(ASSETS).as_posix()
            converted += 1

    ref_files = rewrite_refs(mapping)
    after_count, after_bytes = count_rasters()
    report = {
        "format": "kissne-image-budget-v1",
        "before": {"files": before_count, "bytes": before_bytes},
        "after": {"files": after_count, "bytes": after_bytes},
        "converted": converted,
        "unused_removed": removed,
        "reference_files_rewritten": ref_files,
        "bytes_saved": before_bytes - after_bytes,
        "percent_saved": round((before_bytes - after_bytes) * 100.0 / before_bytes, 2)
                         if before_bytes else 0.0,
        "policies": {
            "stickers": "WebP q90, <=256px",
            "avatars": "WebP q90, <=256px",
            "home_cards": "WebP q86, <=720px",
            "splash": "WebP q88, dimensions preserved",
            "fallback": "WebP q88, <=512px",
        },
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
