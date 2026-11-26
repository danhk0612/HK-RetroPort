"""Record Windows-only library attributes before starting the Linux container."""

import json
import stat
from pathlib import Path

library = Path(__file__).resolve().parent / "data"
records = {}
for parent in (
    library / "library/Games",
    library / "collections/dos",
    library / "collections/pc98",
):
    if not parent.exists():
        continue
    for root in parent.iterdir():
        if not root.is_dir():
            continue
        platform = "Games" if parent.name == "Games" else parent.name
        paths = [p for p in root.rglob("*") if p.is_file()]
        compressed = any(
            getattr(p.stat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_COMPRESSED
            for p in paths
        )
        data = {"compression": "압축" if compressed else "비압축"}
        if platform == "Games":
            names = [p.relative_to(root).as_posix() for p in paths]
            data["icon"] = next(
                (n for n in names if n.lower().startswith("dosbox/icon.")), ""
            )
            data["screenshots"] = "\n".join(
                sorted(
                    n
                    for n in names
                    if n.lower().startswith("dosbox/")
                    and Path(n).stem.isdecimal()
                    and Path(n).suffix.lower() in (".png", ".bmp", ".jpg")
                )
            )
            data["manual"] = next(
                (
                    n
                    for n in names
                    if "manual" in n.lower()
                    and Path(n).suffix.lower() in (".txt", ".pdf", ".png")
                ),
                "",
            )
            info = next((p for p in paths if p.name.lower() == "extrainfo.txt"), None)
            if info:
                data["description"] = info.read_text(
                    encoding="cp949", errors="replace"
                ).strip()
        records[platform + "/" + root.name] = data
dest = library / "settings" / "windows-fields.json"
dest.with_suffix(".tmp").write_text(
    json.dumps(records, ensure_ascii=False), encoding="utf-8"
)
dest.with_suffix(".tmp").replace(dest)
