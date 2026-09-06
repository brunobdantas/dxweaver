from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import logging
import os
import re
import time
import urllib.request

log = logging.getLogger("autoft8.cty")
_MOD_RE = re.compile(r"[\(\[\{<~].*$")


@dataclass(frozen=True)
class Entity:
    name: str
    cq_zone: str
    itu_zone: str
    continent: str
    main_prefix: str


class CtyResolver:
    """Resolve callsigns using the standard AD1C CTY.DAT format.

    The resolver deliberately uses entity names as the cross-source key because HRD and
    ADIF both expose country/entity names, while CTY.DAT does not carry ADIF numeric DXCC IDs.
    """

    def __init__(self) -> None:
        self.prefixes: dict[str, Entity] = {}
        self.exact: dict[str, Entity] = {}
        self.loaded_path = ""
        self.loaded_entities = 0

    def load(self, path: str | Path) -> int:
        p = Path(path)
        if not p.exists():
            return 0
        text = p.read_text(encoding="utf-8", errors="replace")
        self.prefixes.clear(); self.exact.clear(); self.loaded_entities = 0
        current: Entity | None = None
        token_buf = ""
        for raw in text.splitlines():
            if raw and not raw[0].isspace():
                parts = raw.split(":")
                if len(parts) >= 8:
                    current = Entity(
                        name=parts[0].strip(), cq_zone=parts[1].strip(), itu_zone=parts[2].strip(),
                        continent=parts[3].strip(), main_prefix=parts[7].strip().lstrip("*"),
                    )
                    self.loaded_entities += 1
                    token_buf = ""
                else:
                    current = None
                continue
            if not current:
                continue
            token_buf += raw.strip()
            while ";" in token_buf:
                block, token_buf = token_buf.split(";", 1)
                self._add_tokens(current, block)
            # Most physical lines end with comma, but can be safely processed incrementally.
            if token_buf.endswith(","):
                self._add_tokens(current, token_buf[:-1])
                token_buf = ""
        if current and token_buf:
            self._add_tokens(current, token_buf)
        self.loaded_path = str(p)
        return self.loaded_entities

    def _add_tokens(self, entity: Entity, block: str) -> None:
        for raw_token in block.split(","):
            token = raw_token.strip()
            if not token:
                continue
            token = _MOD_RE.sub("", token).strip().lstrip("*")
            if not token:
                continue
            if token.startswith("="):
                self.exact[token[1:].upper()] = entity
            else:
                self.prefixes[token.upper()] = entity

    def resolve(self, callsign: str) -> Entity | None:
        call = callsign.upper().strip().strip("<>")
        if not call:
            return None
        if call in self.exact:
            return self.exact[call]
        # Try the full portable call first, then plausible slash components.
        variants = [call]
        if "/" in call:
            variants.extend([p for p in call.split("/") if p and p not in {"P", "M", "MM", "QRP"}])
        best: tuple[int, Entity] | None = None
        for variant in variants:
            if variant in self.exact:
                return self.exact[variant]
            for n in range(len(variant), 0, -1):
                e = self.prefixes.get(variant[:n])
                if e and (best is None or n > best[0]):
                    best = (n, e)
                    break
        return best[1] if best else None


def ensure_cty_file(path: str | Path, url: str, auto_update: bool, max_age_days: int) -> tuple[Path, str]:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    p.parent.mkdir(parents=True, exist_ok=True)
    needs = not p.exists()
    if p.exists() and max_age_days > 0:
        needs = (time.time() - p.stat().st_mtime) > max_age_days * 86400
    if auto_update and needs:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AutoFT8Manager/0.2"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = r.read()
            if len(data) > 10000 and b":" in data:
                tmp = p.with_suffix(p.suffix + ".tmp")
                tmp.write_bytes(data); os.replace(tmp, p)
                return p, f"updated {len(data)} bytes"
        except Exception as exc:
            log.warning("CTY.DAT update failed: %s", exc)
            return p, f"update failed: {exc}"
    return p, "cached" if p.exists() else "missing"
