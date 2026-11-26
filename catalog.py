import os
import configparser
import json
import re
import shutil
import sqlite3
import hashlib
from pathlib import Path
from contextlib import closing
from zipfile import ZipFile, ZIP_DEFLATED
from launcher import Game, LIBRARY, SAVES, SETTINGS_FILE, load_profile

ROOT = Path("/collections")
DB = SETTINGS_FILE.with_name("catalog.sqlite")
STAGE = ROOT / ".incoming"
FIELDS = (
    "title",
    "english",
    "genre",
    "note",
    "publisher",
    "language",
    "year",
    "region",
    "description",
    "work",
    "verification",
    "icon",
    "screenshots",
    "manual",
    "font",
    "commands",
    "cd",
    "disks",
)



def ident(value):
    return hashlib.sha256(value.encode()).hexdigest()


def connect():
    readonly = os.environ.get("RETROPORT_PLAYER") == "1"
    db = sqlite3.connect(DB.as_uri() + "?mode=ro" if readonly else DB, uri=readonly, timeout=30)
    db.row_factory = sqlite3.Row
    return db


def local(root, name):
    p = Path(name.replace("\\", "/"))
    if not name or p.is_absolute() or ".." in p.parts or ":" in name or "\x00" in name:
        raise ValueError("상대 경로를 확인하세요.")
    dest = (root / p).resolve()
    if not dest.is_relative_to(root.resolve()) or dest == root.resolve():
        raise ValueError("폴더 밖의 파일입니다.")
    return dest


def files(root):
    return sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and not p.is_symlink()
    )


def detect(root, platform=None):
    names = files(root)
    disks = [
        n
        for n in names
        if Path(n).suffix.lower() in {".hdi", ".fdi", ".hdm", ".d88", ".d98"}
    ]
    platform = platform or ("pc98" if disks else "dos")
    choices = [
        n
        for n in names
        if Path(n).suffix.lower() in {".exe", ".bat", ".com"}
        and not any(x.lower().startswith("dosbox") for x in Path(n).parts[:-1])
    ]
    stem = root.name
    profiles = DB.with_name("import-profiles.json")
    presets = json.loads(profiles.read_text(encoding="utf-8")) if profiles.is_file() else {}
    preset = presets.get(platform, {}).get(stem, {})
    cmd = preset.get("commands", "")
    if platform == "windows" and cmd not in choices:
        cmd = ""
    if platform != "pc98" and not cmd and len(choices) == 1:
        cmd = choices[0]
    font = next((n for n in names if n.casefold() == (stem + ".bmp").casefold()), "")
    return dict(
        title=preset.get("title", stem),
        platform=platform,
        commands=cmd,
        choices=choices,
        disks="\n".join(disks),
        language=preset.get("language", ""),
        description=preset.get("description", ""),
        font=font,
        archived="없음",
        compression="미확인",
    )


def finish_purge(db, row):
    key = row["id"]
    root = Path(row["path"]).resolve()
    if not any(root != p and root.is_relative_to(p) for p in (ROOT, LIBRARY / "Games")):
        raise ValueError("게임 경로 오류")
    for path in (root, SAVES / key):
        if path.exists():
            shutil.rmtree(path)
    db.execute(
        "UPDATE games SET state='purged',meta='{}',path=? WHERE id=?",
        ("purged/" + key, key),
    )
    db.execute("DELETE FROM prefs WHERE scope=?", (key,))


def initialize():
    STAGE.mkdir(parents=True, exist_ok=True)
    with closing(connect()) as db, db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS games(id TEXT PRIMARY KEY, path TEXT UNIQUE, meta TEXT, state TEXT DEFAULT 'active');
        CREATE TABLE IF NOT EXISTS prefs(scope TEXT PRIMARY KEY, data TEXT);
        """)
        for row in db.execute("SELECT * FROM games WHERE state='purging'").fetchall():
            finish_purge(db, row)
        if not db.execute("SELECT 1 FROM prefs LIMIT 1").fetchone():
            old = (
                json.loads(SETTINGS_FILE.read_text()) if SETTINGS_FILE.exists() else {}
            )
            for k, v in {
                "global": old.get("global", {}),
                **old.get("games", {}),
            }.items():
                db.execute("INSERT INTO prefs VALUES(?,?)", (k, json.dumps(v)))
        for entry in (
            (LIBRARY / "Gamelist.lst").read_text(encoding="cp949").split("\x02")
            if (LIBRARY / "Gamelist.lst").is_file() else ()
        ):
            if not entry:
                continue
            folder, titles, genre, note, engine, publisher, lang, year, region, *_ = (
                entry.split("\x01")
            )
            root = local(LIBRARY / "Games", folder)
            key = ident(folder)
            if (
                db.execute("SELECT 1 FROM games WHERE id=?", (key,)).fetchone()
                or not root.is_dir()
            ):
                continue
            ko, _, en = titles.partition("\x03")
            meta = dict(
                title=ko,
                english=en,
                genre=genre,
                note=note,
                publisher=publisher,
                language=lang,
                year=year,
                region=region,
                platform="pc88" if engine == "17" else "pc98",
                engine=engine,
                compression="미확인",
                archived="있음"
                if any(
                    p.suffix.lower() in (".zip", ".7z", ".rar") for p in root.iterdir()
                )
                else "없음",
            )
            db.execute(
                "INSERT INTO games(id,path,meta) VALUES(?,?,?)",
                (key, str(root), json.dumps(meta)),
            )
        for platform in ("dos", "pc98", "windows"):
            parent = ROOT / platform
            for root in sorted(parent.iterdir()) if parent.exists() else ():
                if not root.is_dir() or root.name.lower() == "anex":
                    continue
                key = ident(platform + "/" + root.name)
                if db.execute(
                    "SELECT 1 FROM games WHERE id=? OR path=?", (key, str(root))
                ).fetchone():
                    continue
                meta = detect(root, platform)
                if platform == "windows" and any(n.lower().endswith(".iso") for n in files(root)):
                    meta.update(
                        cd=next(
                            (n for n in files(root) if n.lower().endswith(".iso")), ""
                        ),
                        commands="",
                        description="설치 매체 · 플레이 미검증",
                    )
                db.execute(
                    "INSERT INTO games(id,path,meta) VALUES(?,?,?)",
                    (key, str(root), json.dumps(meta)),
                )


def active(row):
    meta = json.loads(row["meta"])
    root = Path(row["path"])
    platform = meta["platform"]
    if platform in ("pc88", "pc98"):
        fd, hd, font = load_profile(
            root, meta.get("engine", "13"), meta.get("language") == "한글"
        )
        original_fd, original_hd = fd, hd
        if "disks" in meta:
            baseline = [
                local(root, n)
                for n in meta.get("initial_disks", meta["disks"]).splitlines()
                if n
            ]
            original_fd = tuple(p for p in baseline if p.suffix.lower() != ".hdi")
            original_hd = tuple(p for p in baseline if p.suffix.lower() == ".hdi")
            disks = [local(root, n) for n in meta["disks"].splitlines() if n]
            hd = tuple(p for p in disks if p.suffix.lower() == ".hdi")
            fd = tuple(p for p in disks if p not in hd)
        if "font" in meta:
            font = local(root, meta["font"]) if meta["font"] else None
    else:
        fd, hd, font = (), (), None
    return Game(
        meta["title"],
        meta.get("genre", ""),
        meta.get("note", ""),
        fd,
        hd,
        font,
        platform == "pc88",
        platform,
        root,
        meta.get("commands", ""),
        meta.get("cd", ""),
        original_fd if platform in ("pc98", "pc88") else (),
        original_hd if platform in ("pc98", "pc88") else (),
    )


def dos_config(game, settings, server=False):
    commands = game.commands.splitlines()
    cfg = configparser.ConfigParser(
        interpolation=None, allow_no_value=True, strict=False
    )
    origin = game.root / "DOSBox-0.73" / "origin.conf"
    if origin.exists():
        cfg.read_string(
            origin.read_text(encoding="cp949", errors="replace").split("[autoexec]")[0]
        )
    sections = ("dosbox", "cpu", "mixer", "sblaster", "midi", "gus", "speaker", "dos")
    for section in sections:
        if not cfg.has_section(section):
            cfg.add_section(section)
    cfg["dosbox"]["machine"] = "svga_s3"
    cfg["dosbox"]["memsize"] = str(settings.get("dos_memory", 32))
    cfg["cpu"]["cycles"] = str(settings.get("dos_cycles", 10000))
    cfg["sblaster"]["sbtype"] = "sb16"
    cfg["dos"].update({"xms": "true", "ems": "true"})
    if server:
        cfg["midi"].update(
            {
                "mididevice": "fluidsynth",
                "fluid.soundfont": "/usr/share/sounds/sf2/TimGM6mb.sf2",
            }
        )
    # Import only hardware values. Host paths and commands are generated locally.
    allowed = set(
        "machine memsize core cycles cycleup cycledown nosound rate blocksize prebuffer mpu401 mididevice fluid.soundfont sbtype sbbase irq dma hdma mixer oplmode oplrate gus gusrate gusbase irq1 irq2 dma1 dma2 pcspeaker pcrate tandy tandyrate disney xms ems umb keyboardlayout".split()
    )
    hardware = []
    for section in sections:
        hardware.append("[" + section + "]")
        hardware.extend(
            k + "=" + v
            for k, v in cfg[section].items()
            if v and "\n" not in v and k in allowed
        )
    return "\n".join(
        [
            *hardware,
            "[autoexec]",
            'mount c "drive"' if server else "mount c .",
            *(
                ['imgmount d "disc.iso" -t iso']
                if server and game.cd
                else ['imgmount d "C:\\' + game.cd.replace("/", "\\") + '" -t iso']
                if game.cd
                else []
            ),
            "c:",
            *(["Z:\\SYSTEM\\CONFIG.COM -securemode"] if server else []),
            *(
                [
                    r"if exist HKFLAGS\FLAG* copy HKFLAGS\FLAG* .",
                    r"if exist HKFLAGS\FLAG* del HKFLAGS\FLAG*",
                ]
                if not server and game.root.name in ("KAKYUHAN", "KAKYUHAN_E")
                else []
            ),
            *commands,
            "",
        ]
    )


def validate_meta(root, meta):
    if not meta.get("title", "").strip():
        raise ValueError("제목을 입력하세요.")
    names = {n.casefold(): n for n in files(root)}
    if any(c in meta.get("cd", "") for c in '\r\n"'):
        raise ValueError("CD 파일 경로를 확인하세요.")
    media_ext = {"pc88": {".d88"}, "pc98": {".hdi", ".fdi", ".d88", ".d98", ".hdm"}}
    for n in meta.get("disks", "").splitlines():
        if (
            meta["platform"] in media_ext
            and Path(n).suffix.lower() not in media_ext[meta["platform"]]
        ):
            raise ValueError("기종에 맞는 디스크 이미지를 선택하세요.")
    for k in ("icon", "screenshots", "manual", "cd", "disks", "font"):
        for n in meta.get(k, "").splitlines():
            if n and not local(root, n).is_file():
                raise ValueError("파일 없음 · " + n)
    if meta["platform"] != "dos":
        return
    for command in meta.get("commands", "").splitlines():
        if not re.fullmatch(r"[\w.\\/-]+(?: [\w. /:+-]+)*", command):
            raise ValueError("실행 파일과 인수를 확인하세요.")
        exe = command.split()[0].replace("\\", "/").lower()
        if not any(exe + ext in names for ext in ("", ".com", ".exe", ".bat")):
            raise ValueError("실행 파일 없음 · " + exe)


def disk_batch(game):
    # The special edition starts BOOTUP.MES on disk A and requests disk B in drive 2.
    original = game.root / "DK4SP.BAT"
    if game.root.name == "DK4SP" and original.is_file():
        source = original.read_bytes()
        line = b"ai5v bootup.mes E x\r\n"
        if line in source:
            return source.replace(line, b"ai5v bootup.mes A B\r\n")
    return None


def bundle(game, settings, target):
    with ZipFile(
        target, "w", ZIP_DEFLATED, compresslevel=1, strict_timestamps=False
    ) as z:
        entries = files(game.root)
        directories = sorted(
            {
                str(parent)
                for n in entries
                for parent in Path(n).parents
                if str(parent) != "." and parent.parts[0].lower() != "dosbox-0.73"
            }
        )
        if game.root.name in ("KAKYUHAN", "KAKYUHAN_E"):
            directories.append("HKFLAGS")
        for name in [".jsdos", *directories]:
            z.writestr(name + "/", b"")
        for n in entries:
            if n.split("/")[0].lower() == "dosbox-0.73" or n.lower().startswith(
                ".jsdos/"
            ):
                continue
            if n == "DK4SP.BAT" and (patched := disk_batch(game)):
                z.writestr(n, patched)
            else:
                z.write(game.root / n, n)
        z.writestr(".jsdos/dosbox.conf", dos_config(game, settings).encode("cp949"))
        z.writestr(".jsdos/jsdos.json", '{"version":"8"}')


def extract_archive(source, dest):
    import libarchive

    with libarchive.file_reader(str(source)) as archive:
        for entry in archive:
            if entry.isdir:
                continue
            if not entry.isfile or entry.linkpath:
                raise ValueError("일반 파일만 가져올 수 있습니다.")
            path = local(dest, entry.pathname)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as out:
                for block in entry.get_blocks():
                    out.write(block)
