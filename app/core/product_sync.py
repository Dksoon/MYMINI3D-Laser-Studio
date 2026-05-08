"""Product list export / import / sync — never touches jobs or machines."""
from __future__ import annotations
import json
import sys
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional


def _bundle_path() -> Path:
    """Where the installer places the master products file."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "products_default.json"
    return Path(__file__).parent.parent.parent / "products_default.json"


# ──────────────────────────────────────────────────────────────────────
# Export
# ──────────────────────────────────────────────────────────────────────

def export_products(dest_path: str) -> tuple[bool, str]:
    from app.core.database import get_session, Product
    try:
        with get_session() as s:
            products = (
                s.query(Product)
                .order_by(Product.category, Product.name)
                .all()
            )
            rows = [{"name": p.name, "category": p.category or ""} for p in products]

        payload = {
            "version":      "1.0",
            "exported_at":  datetime.now().strftime("%Y-%m-%d %H:%M"),
            "product_count": len(rows),
            "products":     rows,
        }
        Path(dest_path).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return True, f"Exported {len(rows)} products."
    except Exception as e:
        return False, str(e)


# ──────────────────────────────────────────────────────────────────────
# Import / Sync
# ──────────────────────────────────────────────────────────────────────

def import_products(src_path: str, replace_all: bool = False) -> tuple[bool, str]:
    """
    replace_all=False  → merge (add missing, keep existing)
    replace_all=True   → sync (delete all products, load from file)
    Jobs and machines are never touched.
    """
    from app.core.database import get_session, Product
    try:
        raw  = Path(src_path).read_text(encoding="utf-8")
        data = json.loads(raw)
        rows = data.get("products", [])

        with get_session() as s:
            if replace_all:
                s.query(Product).delete()
                s.flush()
                for r in rows:
                    name = r.get("name", "").strip()
                    cat  = r.get("category", "").strip()
                    if name:
                        s.add(Product(name=name, category=cat or None))
                added   = len(rows)
                skipped = 0
            else:
                existing = {
                    (p.name.strip().lower(), (p.category or "").strip().lower())
                    for p in s.query(Product).all()
                }
                added = skipped = 0
                for r in rows:
                    name = r.get("name", "").strip()
                    cat  = r.get("category", "").strip()
                    key  = (name.lower(), cat.lower())
                    if name and key not in existing:
                        s.add(Product(name=name, category=cat or None))
                        existing.add(key)
                        added += 1
                    else:
                        skipped += 1
            s.commit()

        verb = "Synced" if replace_all else "Merged"
        return True, f"{verb}: {added} added, {skipped} unchanged."
    except Exception as e:
        return False, str(e)


# ──────────────────────────────────────────────────────────────────────
# Bundled-file helpers (used by startup sync check)
# ──────────────────────────────────────────────────────────────────────

def bundled_path() -> Optional[Path]:
    p = _bundle_path()
    return p if p.exists() else None


def bundled_hash() -> str:
    p = bundled_path()
    if not p:
        return ""
    return hashlib.md5(p.read_bytes()).hexdigest()


def bundled_count() -> int:
    p = bundled_path()
    if not p:
        return 0
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("product_count", 0)
    except Exception:
        return 0
