"""Device-owned attachment presentation; model vision prompts are never UI text."""
from pathlib import Path
from functools import lru_cache
import base64
import io


def attachment_path(turn_id, meta):
    from plugins.plugin_storage import plugin_data_dir
    root = (plugin_data_dir('kissne_mobile') / 'uploads').resolve()
    name = str(meta.get('stored_name') or '')
    if not name:
        label = str(meta.get('file_name') or meta.get('label') or '')
        # Match only files admitted under this device-owned turn, never an arbitrary path.
        candidates = list(root.glob(str(turn_id) + '_*')) if str(turn_id).startswith('kbm_turn_') else []
        import re
        safe_name = re.sub(r'[^A-Za-z0-9._-]+', '_', Path(label).name).strip('._')[:120] or 'upload.bin'
        candidates = [p for p in candidates if p.name.endswith('_' + safe_name)]
        if len(candidates) != 1:
            return None
        name = candidates[0].name
    target = (root / Path(name).name).resolve()
    return target if target.parent == root and target.is_file() else None


@lru_cache(maxsize=32)
def thumbnail(path, modified):
    from PIL import Image
    with Image.open(path) as im:
        im.thumbnail((900, 900))
        out = io.BytesIO()
        im.convert('RGBA').save(out, format='WEBP', quality=78)
    return 'data:image/webp;base64,' + base64.b64encode(out.getvalue()).decode()


def enrich_attachments(turn_id, attachments):
    result = []
    for index, source in enumerate(attachments):
        meta = dict(source)
        meta['turn_id'] = turn_id
        meta['attachment_index'] = index
        path = attachment_path(turn_id, meta)
        if path and meta.get('type') in {'image', 'photo'}:
            try:
                meta['preview'] = thumbnail(str(path), path.stat().st_mtime_ns)
            except (ImportError, OSError, ValueError):
                pass
        # Storage paths are internal; retrieval is authenticated by turn ownership.
        meta.pop('stored_name', None)
        result.append(meta)
    return result


def visible_media_text(text, attachments):
    if not attachments:
        return text
    import re
    text = re.sub(r'\[The user sent an image[\s\S]*?\]', '', text, flags=re.I)
    text = re.sub(r'\[If you need a closer look,[\s\S]*?\]', '', text, flags=re.I)
    return re.sub(r'[\[【]\s*(?:照片|文件|表情包)\s*[:：][^\]】]+[\]】]', '', text).strip()
