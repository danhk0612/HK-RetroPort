import filecmp
import core_install
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from contextlib import closing
from pathlib import Path
from threading import RLock
from subprocess import Popen, run
from urllib.parse import urlsplit, unquote, parse_qs
from http.server import ThreadingHTTPServer
from launcher import Handler, Launcher, SAVES, stage_disks, validate_settings
from df3font import prepare_df3
from catalog import (
    DB,
    ROOT,
    STAGE,
    FIELDS,
    active,
    bundle,
    connect,
    detect,
    dos_config,
    disk_batch,
    extract_archive,
    files,
    finish_purge,
    ident,
    initialize,
    local,
    validate_meta,
)

PLATFORMS = ("dos", "pc98", "pc88", "windows")
EDITOR = ident("dos/KAKYUHAN_E")
KAKYU = ident("dos/KAKYUHAN")


def registry_file(root, name):
    # Packages may keep these files beside the executable or in a settings folder.
    for path in (root / name, *sorted(root.glob("*/" + name))):
        if path.is_file() and path.resolve().is_relative_to(root.resolve()):
            return path
    return None


def wine_game(game):
    if game.platform == "windows":
        entry = game.commands.casefold()
        if entry == "adf.exe" and registry_file(game.root, "CompileNT.reg"):
            return entry
        if entry == "fifawc.exe" or (entry == "mystic.exe" and registry_file(game.root, "_mystic.reg")):
            return entry
    return None


class Library(Launcher):
    def __init__(self):
        if os.environ.get("RETROPORT_PLAYER") != "1":
            initialize()
        manifest = DB.with_name("windows-fields.json")
        self.original_fields = (
            json.loads(manifest.read_text(encoding="utf-8"))
            if manifest.exists()
            else {}
        )
        self.lock = RLock()
        self.process = None
        self.running = None
        with closing(connect()) as db:
            self.games = {}
            self.meta = {}
            for row in db.execute("SELECT * FROM games WHERE state='active'"):
                self.refresh(row)
            self.prefs = {
                r["scope"]: json.loads(r["data"])
                for r in db.execute("SELECT * FROM prefs")
            }

    def refresh(self, row):
        key = row["id"]
        self.games[key] = active(row)
        root = self.games[key].root
        defaults = self.original_fields.get(root.parent.name + "/" + root.name, {})
        self.meta[key] = defaults | json.loads(row["meta"])
        if self.meta[key].get("compression") == "미확인" and defaults:
            self.meta[key]["compression"] = defaults["compression"]
        if not self.meta[key].get("engine"):
            self.meta[key]["engine"] = {
                "dos": "DOSBox",
                "pc98": "Anex86",
                "pc88": "M88",
                "windows": "DOSBox-X",
            }[self.games[key].platform]
        self.meta[key]["engine"] = {"13": "Anex86", "16": "NP21", "17": "M88"}.get(
            self.meta[key]["engine"], self.meta[key]["engine"]
        )
        self.meta[key].pop("choices", None)
        if wine_game(self.games[key]):
            self.meta[key]["engine"] = "Wine"

    def blocked_games(self):
        path = DB.with_name("blocked-games.json")
        return set(json.loads(path.read_text(encoding="utf8"))) if path.exists() else set()

    def defaults(self, scope):
        if scope == "global":
            return {}
        result = dict(self.prefs.get("global", {}))
        if scope in self.games:
            result.update(self.prefs.get(self.games[scope].platform, {}))
        return result

    def effective_settings(self, scope):
        return (
            {"execution": "browser"} | self.defaults(scope) | self.prefs.get(scope, {})
        )

    def save_settings(self, scope, values):
        with self.lock, closing(connect()) as db, db:
            db.execute(
                "INSERT OR REPLACE INTO prefs VALUES(?,?)", (scope, json.dumps(values))
            )
            self.prefs[scope] = values

    def play(self, key, game):
        with self.lock:
            prefs = self.effective_settings(key)
            if profile := wine_game(game):
                self.stop_game()
                directory = SAVES / key
                directory.mkdir(parents=True, exist_ok=True)
                drive = directory / "wine-game"
                if not drive.exists():
                    with tempfile.TemporaryDirectory(dir=directory) as tmp:
                        ready = Path(tmp) / "GAME"
                        image = directory / "hdd.img"
                        if image.exists():
                            run(["mcopy", "-s", "-i", str(image) + "@@32256", "::/GAME", tmp], check=True)
                        else:
                            shutil.copytree(game.root, ready)
                        ready.rename(drive)
                env = dict(os.environ, WINEPREFIX=str(directory / "wine"), WINEARCH="win32",
                           LC_ALL="ko_KR.UTF-8", LIBGL_ALWAYS_SOFTWARE="1",
                           WINEDLLOVERRIDES="ddraw,d3dimm=b;mscoree,mshtml=", PULSE_SERVER="unix:/defaults/native")
                env.pop("LD_PRELOAD", None)
                self.wine_env = env
                desktop = "FIFA,640x480"
                registry = "Fifawc.reg"
                marker = directory / "fifa-reg-imported"
                if profile == "fifawc.exe":
                    ini = drive / "soccer.ini"
                    data = ini.read_bytes()
                    full = re.sub(rb"(?im)^(WINDOWED\s*=\s*)1(?=\s*$)", rb"\g<1>0", data)
                    if full != data:
                        ini.write_bytes(full)
                else:
                    desktop = "Mystic,640x480" if profile == "mystic.exe" else "ADF,640x480"
                    registry = "_mystic.reg" if profile == "mystic.exe" else "CompileNT.reg"
                    marker = directory / ("mystic-reg-imported" if profile == "mystic.exe" else "adf-reg-imported")
                    if profile == "mystic.exe":
                        env["WINEDLLOVERRIDES"] = "ddraw=n,b;mscoree,mshtml="
                    fonts = directory / "wine/drive_c/windows/Fonts"
                    fonts.mkdir(parents=True, exist_ok=True)
                    if not (fonts / "gulim.ttc").exists():
                        shutil.copyfile(ROOT / ".base/gulim.ttc", fonts / "gulim.ttc")
                wine = ["taskset", "-c", str(min(os.sched_getaffinity(0))), "wine"]
                with (directory / "wine.log").open("wb") as log:
                    options = dict(env=env, cwd=drive, stdout=log, stderr=log)
                    run([*wine, "reg", "add", r"HKCU\Software\Wine\X11 Driver", "/v", "UseXVidMode", "/d", "N", "/f"], check=True, **options)
                    if profile in ("fifawc.exe", "adf.exe"):
                        warp = "force" if profile == "adf.exe" else "disable"
                        run([*wine, "reg", "add", r"HKCU\Software\Wine\DirectInput", "/v", "MouseWarpOverride", "/d", warp, "/f"], check=True, **options)
                    registration = registry_file(drive, registry)
                    if registration and not marker.exists():
                        imports = [registration]
                        if profile == "adf.exe":
                            imports.append(registration.with_name("DirectDraw_Fix.reg"))
                        for path in imports:
                            run([*wine, "regedit", "/S", str(path.relative_to(drive)).replace("/", "\\")], check=True, **options)
                        marker.touch()
                    self.process = Popen([*wine, "explorer", "/desktop=" + desktop, game.commands], **options)
            elif (
                game.platform == "pc98"
                and prefs.get("pc98_server") == "anex"
                and len(game.hard_disks) == 1
                and not game.floppies
            ):
                self.stop_game()
                directory = SAVES / key
                directory.mkdir(parents=True, exist_ok=True)
                exe = directory / "anex"
                shutil.copytree(ROOT / "pc98/anex", exe, dirs_exist_ok=True)
                (disk_name,) = stage_disks(directory, game.hard_disks, "disk", game)
                disk = directory / disk_name
                font = game.font or exe / "anex86.bmp"
                shutil.copyfile(font, disk.with_suffix(".bmp"))
                env = {
                    **os.environ,
                    "WINEARCH": "win32",
                    "WINEPREFIX": "/config/anex-wine",
                    "WINEDLLOVERRIDES": "mscoree,mshtml=",
                    "PULSE_SERVER": "unix:/defaults/native",
                }
                env.pop("LD_PRELOAD", None)
                with (directory / "anex.log").open("wb") as log:
                    self.process = Popen(
                        ["wine", "anex.exe", "Z:" + str(disk).replace("/", "\\")],
                        env=env,
                        cwd=exe,
                        stdout=log,
                        stderr=log,
                    )
                self.wine_env = env
            else:
                super().play(key, game)
            self.running = key

    def stop_game(self):
        if getattr(self, "wine_env", None):
            run(["wineserver", "-k"], env=self.wine_env, timeout=15, check=False)
            self.wine_env = None
        super().stop_game()
        self.running = None

    def dosbox_command(self, directory, game, preferences):
        if game.platform not in ("dos", "windows"):
            return super().dosbox_command(directory, game, preferences)
        if game.cd:
            source = local(game.root, game.cd)
            link = directory / "disc.iso"
            link.unlink(missing_ok=True)
            link.symlink_to(source)
        if game.platform == "windows":
            first = not (directory / "hdd.img").exists()
            commands = (["imgmake hdd.img -t hd_2gig"] if first else []) + [
                "imgmount c hdd.img -ide 1m",
                "imgmount d disc.iso -ide 2m",
            ]
            edition = "WIN98" if game.commands or "98" in game.root.name else "WIN95"
            commands.extend(
                [
                    r"if exist C:\WINDOWS\WIN.COM goto installed",
                    r"if exist C:\SETUPLOG.TXT goto installed",
                    f"if exist C:\\{edition}\\SETUP.EXE goto localsetup",
                    "D:",
                    "cd " + edition,
                    "setup /is",
                    "goto done",
                    ":localsetup",
                    "C:",
                    "cd " + edition,
                    "setup /is",
                    "goto done",
                    ":installed",
                    "boot c:",
                    ":done",
                ]
            )
            base = ROOT / ".base" / (edition.lower() + ".img")
            if game.commands and not base.is_file():
                raise ValueError("Windows 98 기본 이미지가 필요합니다.")
            if base.is_file():
                if first:
                    with tempfile.TemporaryDirectory(dir=directory) as tmp:
                        copy = Path(tmp) / "hdd.img"
                        run(["cp", "--sparse=always", base, copy], check=True)
                        if game.commands:
                            volume = str(copy) + "@@32256"
                            run(["mmd", "-i", volume, "::/GAME"], check=True)
                            run(["mcopy", "-s", "-i", volume, *sorted(game.root.iterdir()), "::/GAME/"], check=True)
                        copy.replace(directory / "hdd.img")
                if game.commands:
                    entry = local(game.root, game.commands)
                    if entry.parent != game.root or not re.fullmatch(r"[\w-]{1,8}\.exe", entry.name, re.I | re.ASCII) or not entry.is_file():
                        raise ValueError("게임 폴더의 DOS 8.3 형식 EXE를 선택하세요.")
                    volume = str(directory / "hdd.img") + "@@32256"
                    launch_name = entry.name
                    if entry.name.lower() == "devilf.exe":
                        launch_name = prepare_df3(entry, volume, ROOT / ".base/gulim.ttc", directory)
                    startup = directory / "HKGAME.BAT"
                    if not startup.exists():
                        for saved in directory.glob("*GAME.BAT"):
                            if re.fullmatch(rb"@echo off\r\ncd \\GAME\r\nstart [\w.-]+\r\nexit\r\n", saved.read_bytes(), re.I):
                                startup = saved
                                break
                    startup.write_bytes(("@echo off\r\ncd \\GAME\r\nstart " + launch_name + "\r\nexit\r\n").encode("cp949"))
                    run(["mcopy", "-o", "-i", volume, startup, "::/WINDOWS/Start Menu/Programs/StartUp/" + startup.name], check=True)
                commands = [
                    "imgmount 2 hdd.img -t hdd -fs none -size 512,63,64,1023 -ide 1m",
                    "boot c:",
                ]
                volume = str(directory / "hdd.img") + "@@32256"
                system_ini = "::/WINDOWS/SYSTEM.INI"
                system = run(["mtype", "-i", volume, system_ini], capture_output=True, check=True).stdout
                absolute_mouse = re.sub(rb"(?im)^(mouse\.drv\s*=\s*)(?:vmw)?mouse\.drv(?=\r?$)", rb"\g<1>vbmouse.drv", system)
                if absolute_mouse != system:
                    run(["mcopy", "-o", "-i", volume, "/opt/retroport/VBMOUSE.DRV", "::/WINDOWS/SYSTEM/VBMOUSE.DRV"], check=True)
                    run(["mcopy", "-o", "-i", volume, "/opt/retroport/VBMOUSE.EXE", "::/VBMOUSE.EXE"], check=True)
                    names = run(["mdir", "-b", "-i", volume, "::/"], capture_output=True, check=True).stdout.upper().splitlines()
                    auto = (run(["mtype", "-i", volume, "::/AUTOEXEC.BAT"], capture_output=True, check=True).stdout
                            if b"::/AUTOEXEC.BAT" in names else b"")
                    if b"C:\\VBMOUSE.EXE" not in auto.upper().splitlines():
                        run(["mcopy", "-o", "-i", volume, "-", "::/AUTOEXEC.BAT"], input=b"C:\\VBMOUSE.EXE\r\n" + auto, check=True)
                    run(["mcopy", "-o", "-i", volume, "-", system_ini], input=absolute_mouse, check=True)
                if edition == "WIN98":
                    original = run(["mtype", "-i", volume, "::/MSDOS.SYS"], capture_output=True, check=True).stdout
                    updated = re.sub(rb"(?im)^AutoScan=[12](?=\r?$)", b"AutoScan=0", original)
                    if updated != original:
                        run(["mattrib", "-i", volume, "-r", "-s", "-h", "::/MSDOS.SYS"], check=True)
                        try:
                            run(["mcopy", "-o", "-i", volume, "-", "::/MSDOS.SYS"], input=updated, check=True)
                        finally:
                            run(["mattrib", "-i", volume, "+r", "+s", "+h", "::/MSDOS.SYS"], check=True)
            core = "normal" if edition == "WIN98" else "auto"
            sound = "[sblaster]\nsbtype=sb16\nsbbase=240\nirq=10\ndma=3\nhdma=7\n" if edition == "WIN98" else ""
            display = "fullscreen=false\nwindowposition=0,0\nshowmenu=false\nmouse_emulation=never\n" if game.commands.lower() == "devilf.exe" else ""
            conf = (
                f"[sdl]\n{display}autolock=false\nclip_mouse_button=none\n"
                f"[dosbox]\nquit warning=false\nmachine=svga_s3\nmemsize=64\n[cpu]\ncore={core}\ncputype=pentium_mmx\ncycles=60000\n{sound}[dos]\nver=7.1\n[autoexec]\n"
                + "\n".join(commands)
            )
        else:
            drive = directory / "drive"
            if not drive.exists():
                with tempfile.TemporaryDirectory(dir=directory) as tmp:
                    ready = Path(tmp) / "drive"
                    shutil.copytree(
                        game.root, ready, ignore=shutil.ignore_patterns("DOSBox-0.73")
                    )
                    ready.rename(drive)
            if patched := disk_batch(game):
                entry = drive / "DK4SP.BAT"
                if entry.read_bytes() == (game.root / "DK4SP.BAT").read_bytes():
                    tmp = entry.with_suffix(".tmp")
                    tmp.write_bytes(patched)
                    tmp.replace(entry)
            if directory.name == EDITOR:
                src = SAVES / KAKYU / "drive"
                if not src.is_dir():
                    raise ValueError("먼저 서버에서 하급생을 실행해 주세요.")
                for f in src.iterdir():
                    if f.is_file() and f.name.upper().startswith("FLAG"):
                        shutil.copyfile(f, drive / f.name)
            conf = dos_config(game, preferences, True)
        config = directory / "dosbox.conf"
        config.write_text(conf, encoding="cp949")
        return ["dosbox-x", "-conf", config, "-fastlaunch"]


class Web(Handler):
    @property
    def app(self):
        return self.server.launcher

    def sendfile(self, p, kind="application/octet-stream"):
        with p.open("rb") as src:
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(os.fstat(src.fileno()).st_size))
            self.end_headers()
            shutil.copyfileobj(src, self.wfile)

    def do_GET(self):
        path = urlsplit(self.path).path.removeprefix("/library/")
        app = self.app
        if path in (
            "manage/",
            "manage/trash/",
            "dos.html",
            "wine-screen.html",
            "management.js",
            "dos.js",
            "cleanup.js",
        ):
            name = "manage.html" if path.startswith("manage/") else path
            self.sendfile(
                Path("/opt/retroport") / name,
                "text/"
                + ("javascript" if name.endswith(".js") else "html")
                + "; charset=utf-8",
            )
        elif path == "manage/cores":
            if os.environ.get("RETROPORT_PLAYER") == "1":
                return self.send_error(403)
            self.json_response(200, dict(installed=core_install.available(), version=core_install.VERSION,
                                         source=core_install.SOURCE, files=list(core_install.FILES)))
        elif path == "storage.json":
            self.json_response(200, os.environ.get("RETROPORT_STORAGE_NAMESPACE", "retroport"))
        elif path == "player.html":
            page = Path("/opt/retroport/index.html").read_text(encoding="utf8")
            self.respond(200, "text/html; charset=utf-8", page.replace("<html ", "<html data-player ", 1).encode())
        elif path == "games":
            with app.lock:
                blocked = app.blocked_games()
                pc98_browser = core_install.available()
                games = []
                for key, game in app.games.items():
                    execution = app.effective_settings(key)["execution"]
                    browser = game.browser and (game.platform != "pc98" or pc98_browser)
                    needs_core = (game.browser and not browser and execution == "browser"
                                  and app.meta[key].get("server_verified") is not True)
                    games.append({
                        **app.meta[key], "id": key, "browser": browser,
                        "playable": game.playable and key not in blocked and not needs_core,
                        "needs_core": needs_core, "blocked": key in blocked,
                        "pc88": game.pc88, "execution": execution,
                    })
            self.json_response(200, games)
        elif path.startswith("settings/"):
            scope = path.split("/")[-1]
            if scope not in ("global", *PLATFORMS) and scope not in app.games:
                return self.send_error(404)
            self.json_response(
                200, dict(values=app.prefs.get(scope, {}), defaults=app.defaults(scope))
            )
        elif path in ("trash", "purged"):
            with closing(connect()) as db:
                state = "trash" if path == "trash" else "purged"
                self.json_response(
                    200,
                    [
                        dict(id=r[0], title=json.loads(r[1]).get("title", ""))
                        for r in db.execute(
                            "SELECT id,meta FROM games WHERE state=?", (state,)
                        )
                    ],
                )
        elif path.startswith("asset/"):
            key, _, name = path[6:].partition("/")
            meta = app.meta.get(key, {})
            name = unquote(name)
            allowed = [
                meta.get("icon"),
                meta.get("manual"),
                *meta.get("screenshots", "").splitlines(),
            ]
            if not name or name not in allowed:
                return self.send_error(404)
            kind = {
                ".bmp": "image/bmp",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".txt": "text/plain; charset=windows-949",
                ".pdf": "application/pdf",
            }
            self.sendfile(
                local(app.games[key].root, name),
                kind.get(Path(name).suffix.lower(), "application/octet-stream"),
            )
        elif path.startswith("files/"):
            game = app.games.get(path.split("/")[-1])
            if not game:
                return self.send_error(404)
            self.json_response(200, files(game.root))
        elif path.startswith("bundle/"):
            key = path.split("/")[-1]
            with app.lock:
                g = app.games.get(key)
                if not g or g.platform != "dos" or not g.playable:
                    return self.send_error(404)
                prefs = app.effective_settings(key)
                cache = (
                    SAVES
                    / key
                    / ("bundle-" + ident("4/" + dos_config(g, prefs)) + ".jsdos")
                )
                cache.parent.mkdir(parents=True, exist_ok=True)
                if not cache.exists():
                    tmp = cache.with_suffix(".tmp")
                    bundle(g, prefs, tmp)
                    tmp.replace(cache)
            self.sendfile(cache)
        else:
            super().do_GET()

    def post(self, path, data, db):
        app = self.app
        action, _, key = path.partition("/")
        if action == "settings":
            if key not in ("global", *PLATFORMS) and key not in app.games:
                raise ValueError("설정 대상 없음")
            app.save_settings(key, validate_settings(data))
            return {}
        if action == "stage":
            token = uuid.uuid4().hex
            (STAGE / token).mkdir()
            return {"token": token}
        if action in ("preview", "import", "cancel"):
            if not re.fullmatch("[0-9a-f]{32}", key) or not (STAGE / key).is_dir():
                raise ValueError("가져오기 세션 없음")
            stage = STAGE / key
            if action == "cancel":
                shutil.rmtree(stage)
                return {}
            source = stage / "content"
            if not source.is_dir():
                source.mkdir()
                try:
                    extract_archive(stage / "archive", source)
                except Exception:
                    shutil.rmtree(source)
                    raise ValueError("압축 파일을 읽을 수 없습니다.")
            roots = [p for p in sorted(source.iterdir()) if p.is_dir()]
            if any(p.is_file() for p in source.iterdir()) or not roots:
                roots = [source]
            if (
                len(roots) == 1
                and roots[0] != source
                and not any(p.is_file() for p in roots[0].iterdir())
            ):
                nested = [p for p in sorted(roots[0].iterdir()) if p.is_dir()]
                if nested:
                    roots = nested
            if len(roots) == 1:
                container = roots[0]
                bundled = [
                    p
                    for p in sorted(container.iterdir())
                    if p.is_dir()
                    and (
                        (p / "DOSBox-0.73" / "text.bat").is_file()
                        or (p / (p.name + ".hdi")).is_file()
                    )
                ]
                if bundled and any(
                    p.suffix.lower() == ".bat"
                    for p in container.iterdir()
                    if p.is_file()
                ):
                    roots = bundled
            if action == "preview":
                return [
                    dict(detect(p), folder=p.relative_to(source).as_posix())
                    for p in roots
                ]
            results = []
            for item in data["items"]:
                root = (
                    source if item["folder"] == "." else local(source, item["folder"])
                )
                if root not in roots:
                    raise ValueError("등록 폴더를 확인하세요.")
                meta = detect(root, item["platform"])
                if meta["platform"] not in ("dos", "pc98", "pc88"):
                    raise ValueError("기종을 확인하세요.")
                meta.update({k: item[k] for k in FIELDS if k in item})
                if meta["platform"] == "dos" and not meta.get("commands", "").strip():
                    raise ValueError("DOS 시작 명령을 선택하세요.")
                validate_meta(root, meta)
                digest = hashlib.sha256()
                for n in files(root):
                    digest.update(n.encode() + b"\0")
                    with (root / n).open("rb") as f:
                        digest.update(hashlib.file_digest(f, "sha256").digest())
                seeded = ROOT / meta["platform"] / root.name
                if seeded.is_dir() and files(seeded) == files(root):
                    if all(
                        filecmp.cmp(root / n, seeded / n, shallow=False)
                        for n in files(root)
                    ):
                        existing = db.execute(
                            "SELECT id,state FROM games WHERE path=?", (str(seeded),)
                        ).fetchone()
                        if existing:
                            results.append(dict(id=existing[0], state=existing[1]))
                            continue
                legacy = ROOT / "imports" / (meta["platform"] + "-" + digest.hexdigest())
                dest = ROOT / meta["platform"] / digest.hexdigest()
                existing = db.execute(
                    "SELECT id,state FROM games WHERE path IN (?,?)", (str(dest), str(legacy))
                ).fetchone()
                if existing:
                    results.append(dict(id=existing[0], state=existing[1]))
                    continue
                dest.parent.mkdir(exist_ok=True)
                if not dest.exists():
                    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
                        ready = Path(tmp) / "game"
                        shutil.copytree(root, ready)
                        ready.rename(dest)
                game_id = uuid.uuid4().hex
                meta["archived"] = "있음" if (stage / "archive").exists() else "없음"
                db.execute(
                    "INSERT INTO games(id,path,meta) VALUES(?,?,?)",
                    (game_id, str(dest), json.dumps(meta)),
                )
                results.append(dict(id=game_id, state="added"))
            db.commit()
            for r in results:
                if r["state"] == "added":
                    app.refresh(
                        db.execute(
                            "SELECT * FROM games WHERE id=?", (r["id"],)
                        ).fetchone()
                    )
            shutil.rmtree(stage)
            return results
        row = db.execute("SELECT * FROM games WHERE id=?", (key,)).fetchone()
        if not row:
            raise ValueError("게임 없음")
        if action == "edit" and row["state"] == "active":
            meta = json.loads(row["meta"])
            if (
                "disks" in data
                and "initial_disks" not in meta
                and meta["platform"] in ("pc98", "pc88")
            ):
                old = app.games[key]
                meta["initial_disks"] = "\n".join(
                    p.relative_to(old.root).as_posix()
                    for p in (*old.floppies, *old.hard_disks)
                )
            meta.update(
                {k: v for k, v in data.items() if k in FIELDS and isinstance(v, str)}
            )
            validate_meta(Path(row["path"]), meta)
            db.execute("UPDATE games SET meta=? WHERE id=?", (json.dumps(meta), key))
        elif action == "trash" and row["state"] == "active":
            db.execute("UPDATE games SET state='trash' WHERE id=?", (key,))
        elif action == "restore" and row["state"] == "trash":
            db.execute("UPDATE games SET state='active' WHERE id=?", (key,))
        elif (
            action == "purge"
            and row["state"] in ("trash", "purging")
            and data.get("confirm") == key
        ):
            db.execute("UPDATE games SET state='purging' WHERE id=?", (key,))
            db.commit()
            finish_purge(db, row)
            app.prefs.pop(key, None)
        elif action == "apply" and key == EDITOR and row["state"] == "active":
            if app.running:
                raise ValueError("서버 게임을 종료한 뒤 적용하세요.")
            if KAKYU not in app.games:
                raise ValueError("하급생이 목록에 없습니다.")
            source = SAVES / key / "drive"
            target = SAVES / KAKYU / "drive"
            if not source.is_dir() or not target.is_dir():
                raise ValueError("먼저 게임과 에디터를 실행하세요.")
            for p in source.iterdir():
                if p.is_file() and p.name.upper().startswith("FLAG"):
                    tmp = target / (p.name + ".tmp")
                    shutil.copyfile(p, tmp)
                    tmp.replace(target / p.name)
            return {}
        else:
            raise ValueError("현재 상태에서는 처리할 수 없습니다.")
        db.commit()
        if action in ("edit", "restore"):
            app.refresh(db.execute("SELECT * FROM games WHERE id=?", (key,)).fetchone())
        else:
            if app.running == key:
                app.stop_game()
            app.games.pop(key, None)
            app.meta.pop(key, None)
        return {}

    def do_POST(self):
        path = urlsplit(self.path).path.removeprefix("/library/")
        if (
            self.headers.get("Origin")
            != f"{self.headers.get('X-Forwarded-Proto')}://{self.headers.get('Host')}"
        ):
            return self.json_response(403, {"error": "목록 페이지에서 실행하세요."})
        try:
            if path.startswith("play/") and path[5:] in self.app.blocked_games():
                return self.json_response(403, {"error": "운영자가 실행을 보류한 게임입니다."})
            if os.environ.get("RETROPORT_PLAYER") == "1":
                if path.startswith("play/"):
                    key = path.removeprefix("play/")
                    with closing(connect()) as db, self.app.lock:
                        row = db.execute("SELECT * FROM games WHERE id=? AND state='active'", (key,)).fetchone()
                        if row is None:
                            return self.send_error(404)
                        self.app.refresh(row)
                        self.app.prefs = {r["scope"]: json.loads(r["data"]) for r in db.execute("SELECT * FROM prefs")}
                elif path != "stop" and path != "apply/" + EDITOR:
                    return self.send_error(403)
            if path.startswith("play/") or path == "stop":
                return super().do_POST()
            length = int(self.headers.get("Content-Length", 0))
            if path == "manage/cores/pc98":
                if not 0 < length <= core_install.LIMIT:
                    raise ValueError("코어 파일 크기를 확인하세요.")
                body = self.rfile.read(length)
                with self.app.lock:
                    core_install.install(self.headers.get("Content-Type", ""), body)
                return self.json_response(200, {})
            if path.startswith("attachment/"):
                key = path.split("/")[-1]
                query = parse_qs(urlsplit(self.path).query)
                field = query["field"][0]
                ext = Path(query["name"][0]).suffix.lower()
                allowed = {
                    "icon": {".png", ".jpg", ".jpeg", ".bmp", ".gif"},
                    "screenshots": {".png", ".jpg", ".jpeg", ".bmp", ".gif"},
                    "manual": {".txt", ".pdf", ".png"},
                }
                if (
                    field not in allowed
                    or ext not in allowed[field]
                    or not 0 < length <= 128 * 1024 * 1024
                ):
                    raise ValueError("첨부 형식이나 크기를 확인하세요.")
                with self.app.lock, closing(connect()) as db, db:
                    g = self.app.games.get(key)
                    if not g:
                        raise ValueError("게임 없음")
                    root = g.root / "web-media"
                    root.mkdir(exist_ok=True)
                    name = uuid.uuid4().hex + ext
                    dest = root / name
                    try:
                        with dest.open("xb") as f:
                            while length:
                                block = self.rfile.read(min(1024 * 1024, length))
                                if not block:
                                    raise ValueError("업로드 중단")
                                f.write(block)
                                length -= len(block)
                        ref = "web-media/" + name
                        value = (
                            (self.app.meta[key].get(field, "") + "\n" + ref).strip()
                            if field == "screenshots"
                            else ref
                        )
                        self.post("edit/" + key, {field: value}, db)
                    except Exception:
                        dest.unlink(missing_ok=True)
                        raise
                return self.json_response(200, {})
            if path.startswith("upload/"):
                token = path.split("/")[-1]
                if (
                    not re.fullmatch("[0-9a-f]{32}", token)
                    or not (STAGE / token).is_dir()
                ):
                    raise ValueError("세션 없음")
                q = parse_qs(urlsplit(self.path).query)
                dest = (
                    local(STAGE / token / "content", q["file"][0])
                    if "file" in q
                    else STAGE / token / "archive"
                )
                dest.parent.mkdir(parents=True, exist_ok=True)
                with dest.open("xb") as out:
                    while length:
                        block = self.rfile.read(min(length, 1024 * 1024))
                        if not block:
                            raise ValueError("업로드 중단")
                        out.write(block)
                        length -= len(block)
                return self.json_response(200, {})
            if length > 1024 * 1024:
                raise ValueError("요청 크기 초과")
            data = json.loads(self.rfile.read(length)) if length else {}
            with self.app.lock, closing(connect()) as db, db:
                result = self.post(path, data, db)
            self.json_response(200, result)
        except (ValueError, OSError, KeyError, TypeError) as error:
            self.json_response(400, {"error": str(error) or "설정 값을 확인하세요."})


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8090), Web)
    server.launcher = Library()
    server.serve_forever()
