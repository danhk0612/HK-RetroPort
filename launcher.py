from dataclasses import dataclass
from hashlib import sha256
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path, PureWindowsPath
import re
from shutil import copyfile, copyfileobj
from subprocess import Popen, TimeoutExpired
from threading import Lock
from urllib.parse import urlsplit


LIBRARY = Path("/library")
EMULATORS = LIBRARY / "Emulator"
SAVES = Path("/config/games")
SETTINGS_FILE = Path("/settings/launcher.json")
SETTING_RANGES = {"dos_cycles": (100, 200000), "dos_memory": (1, 128), "volume": (0, 100), "pc98_memory": (1, 128), "pc98_clock": (1, 32), "pc88_clock": (1, 16)}
FLOPPY_EXTENSIONS = {".fdi", ".d88", ".d98", ".hdm"}
HARD_DISK_EXTENSIONS = {".hdi"}


@dataclass(frozen=True)
class Game:
    title: str
    genre: str
    note: str
    floppies: tuple[Path, ...]
    hard_disks: tuple[Path, ...]
    font: Path | None
    pc88: bool
    platform: str = "pc98"
    root: Path | None = None
    commands: str = ""
    cd: str = ""
    original_floppies: tuple[Path, ...] = ()
    original_hard_disks: tuple[Path, ...] = ()

    @property
    def playable(self):
        return bool(self.floppies or self.hard_disks or (self.platform in ("dos", "windows") and self.commands) or (self.platform == "windows" and self.cd))

    @property
    def browser(self):
        return self.platform != "windows" and self.playable and len(self.hard_disks) <= 2


def local_setting(files, value):
    name = PureWindowsPath(value).name.casefold()
    return files.get(name)


def disk_order(files, settings, keys, extensions):
    configured = (local_setting(files, settings.get(key, "")) for key in keys)
    disks = [path for path in configured if path and path.suffix.lower() in extensions]
    disks.extend(path for path in files.values() if path.suffix.lower() in extensions)
    return tuple(dict.fromkeys(disks))


def load_profile(directory, emulator, korean):
    files = {
        path.name.casefold(): path for path in sorted(directory.iterdir())
        if path.is_file() and not path.is_symlink()
    }
    settings = {}
    for name, pattern in (
        ("anex.reg", r'^"([^"]+)"="(.*)"$'),
        ("np21nt.ini", r'^([^=\n]+)=(.*)$'),
    ):
        if name in files and (name != "np21nt.ini" or emulator in ("16", "17") or korean):
            content = files[name].read_text(encoding="cp949", errors="replace")
            settings.update(
                (key.casefold(), value.replace("\\\\", "\\"))
                for key, value in re.findall(pattern, content, re.MULTILINE)
            )
    if emulator in ("16", "17"):
        floppy_keys = ("fd1name0", "fd2name0", "fdd1", "fdd2")
        hard_keys = ("hdd1file", "hdd2file", "hdd1", "hdd2")
    else:
        floppy_keys = ("fdd1", "fdd2", "fd1name0", "fd2name0")
        hard_keys = ("hdd1", "hdd2", "hdd1file", "hdd2file")
    font = local_setting(files, settings.get("fontfile") or settings.get("font", ""))
    if korean and not font:
        font = next((path for path in files.values() if path.suffix.lower() == ".bmp"), None)
    return (
        disk_order(files, settings, floppy_keys, {".d88"} if emulator == "17" else FLOPPY_EXTENSIONS),
        disk_order(files, settings, hard_keys, HARD_DISK_EXTENSIONS) if emulator != "17" else (),
        font,
    )


def load_games(library):
    games = {}
    root = library / "Games"
    entries = (library / "Gamelist.lst").read_text(encoding="cp949").split("\x02")
    for entry in filter(None, entries):
        folder, titles, genre, note, emulator, _, language, *_ = entry.split("\x01")
        if Path(folder).name != folder or folder in (".", ".."):
            continue
        directory = root / folder
        if directory.is_symlink() or not directory.is_dir():
            continue
        floppies, hard_disks, font = (
            load_profile(directory, emulator, language == "한글")
            if emulator in ("13", "16", "17") else ((), (), None)
        )
        game_id = sha256(folder.encode("utf-8")).hexdigest()
        games[game_id] = Game(titles.split("\x03", 1)[0], genre, note, floppies, hard_disks, font, emulator == "17")
    return games


def disk_slot(source, baseline):
    if source in baseline:
        return baseline.index(source) + 1
    return int(sha256(str(source).encode()).hexdigest()[:15],16) + 10000


def stage_disks(directory, disks, prefix, game):
    names = []
    for index, source in enumerate(disks):
        name = prefix if len(disks) == 1 else f"{prefix}{index + 1}"
        baseline = game.original_hard_disks if source in game.hard_disks else game.original_floppies
        if game.original_floppies or game.original_hard_disks:
            if source not in baseline:
                name = "media" + str(disk_slot(source, baseline))
            elif len(game.original_floppies) + len(game.original_hard_disks) == 1:
                name = "disk"
            else:
                name = "hard" if source in game.hard_disks else "floppy"
                if len(baseline)>1: name += str(disk_slot(source,baseline))
        disk = directory / (name + source.suffix.lower())
        if not disk.exists():
            temporary = disk.with_suffix(".tmp")
            copyfile(source, temporary)
            temporary.replace(disk)
        names.append(disk.name)
    return names


def boot_commands(directory, game):
    if len(game.floppies) + len(game.hard_disks) == 1:
        disk, = stage_disks(directory, game.floppies or game.hard_disks, "disk", game)
        if game.floppies:
            return f"imgmount 0 {disk} -t floppy\nboot a:\n"
        return f"imgmount 2 {disk} -t hdd\nboot c:\n"

    floppies = stage_disks(directory, game.floppies, "floppy", game)
    hard_disks = stage_disks(directory, game.hard_disks[:2], "hard", game)
    commands = [f"imgmount {drive} {disk} -t hdd" for drive, disk in enumerate(hard_disks, 2)]
    if floppies:
        commands.append(f"imgmount 0 {floppies[0]} -t floppy")
    if len(floppies) > 1:
        commands.append(f"imgmount 1 {' '.join(floppies[1:])} -t floppy")
    commands.append("boot a:" if floppies else "boot c:")
    return "\n".join(commands) + "\n"


def m88_command(directory, game, settings):
    emulator = EMULATORS / "M88"
    for source in emulator.iterdir():
        if source.suffix.lower() in (".bmp", ".rom", ".wav") or source.name in ("M88.exe", "M88.ini"):
            target = directory / source.name
            if not target.exists():
                copyfile(source, target)

    # M88 mounts the first two disks of a combined D88 image at startup.
    image = directory / "disks.d88"
    if game.original_floppies and game.floppies!=game.original_floppies:
        order = sha256(repr(game.floppies).encode()).hexdigest()[:16]
        image = directory / ("disks-"+order+".d88")
    if not image.exists():
        temporary = image.with_suffix(".tmp")
        with temporary.open("wb") as output:
            for source in game.floppies:
                with source.open("rb") as disk:
                    copyfileobj(disk, output)
        temporary.replace(image)
    windows_path = "Z:" + str(image).replace("/", "\\")
    clock = [f"-c{settings['pc88_clock']}"] if "pc88_clock" in settings else []
    return ["wine", "M88.exe", *clock, windows_path]


def browser_media(game):
    media = {}
    for prefix, disks in (("fd", game.floppies), ("hd", game.hard_disks)):
        for index, source in enumerate(disks, 1):
            baseline=game.original_floppies if prefix=="fd" else game.original_hard_disks
            slot=disk_slot(source,baseline) if baseline else index
            media[f"{prefix}{slot}{source.suffix.lower()}"] = source
    if game.pc88:
        rom_directory = EMULATORS / "M88"
        rom_names = {
            "N88.ROM": "N88.ROM", "N88N.ROM": "N80.ROM", "N88SUB.ROM": "DISK.ROM",
            "N88KNJ1.ROM": "KANJI1.ROM", "N88KNJ2.ROM": "KANJI2.ROM",
            **{f"N88EXT{i}.ROM": f"N88_{i}.ROM" for i in range(4)},
        }
        media.update({name: rom_directory / source for name, source in rom_names.items()})
    else:
        rom_directory = EMULATORS / "NP21nt"
        media["sound.rom"] = rom_directory / "SOUND.ROM"
        if game.font:
            media["font.bmp"] = game.font
        else:
            media["font.rom"] = rom_directory / "FONT.ROM"
    return {name: path for name, path in media.items() if path.is_file()}


def validate_settings(values):
    if not isinstance(values, dict):
        raise ValueError
    for key, value in values.items():
        if key == "pc98_server" and value in ("dosbox","anex"): continue
        if key == "render" and value in ("pixelated","smooth"): continue
        if key == "exitkey" and value in ("None","F9","F10"): continue
        if key == "execution" and value in ("browser", "server"):
            continue
        if key in SETTING_RANGES and type(value) is int:
            low, high = SETTING_RANGES[key]
            if low <= value <= high:
                continue
        raise ValueError
    return values


class Launcher:
    def __init__(self):
        self.games = load_games(LIBRARY)
        self.process = None
        self.lock = Lock()
        self.settings = (
            json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if SETTINGS_FILE.exists() else {"global": {}, "games": {}}
        )

    def effective_settings(self, game_id):
        saved = self.settings
        return {"execution": "browser"} | saved["global"] | saved["games"].get(game_id, {})

    def save_settings(self, scope, values):
        with self.lock:
            saved = {"global": self.settings["global"], "games": self.settings["games"].copy()}
            if scope == "global":
                saved["global"] = values
            elif values:
                saved["games"][scope] = values
            else:
                saved["games"].pop(scope, None)
            temporary = SETTINGS_FILE.with_suffix(".tmp")
            temporary.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary.replace(SETTINGS_FILE)
            self.settings = saved

    def stop_game(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.process = None

    def dosbox_command(self, directory, game, preferences):
        roms = EMULATORS / "NP21nt"
        for name in ("FONT.ROM", "SOUND.ROM"):
            if (roms / name).is_file():
                copyfile(roms / name, directory / name)

        settings = [
            "[sdl]\noutput=surface\n",
            "[dosbox]\nmachine=pc98\nlocking disk image mount=false\n",
        ]
        if "pc98_memory" in preferences:
            settings.append(f"memsize={preferences['pc98_memory']}\n")
        settings.extend(("[midi]\nmididevice=none\n", "[pc98]\npc-98 fm board=board86\n"))
        if game.font:
            copyfile(game.font, directory / "game-font.bmp")
            settings.append("pc-98 try font rom=false\npc-98 anex86 font=game-font.bmp\n")
        settings.extend(("[autoexec]\n", boot_commands(directory, game)))
        config = directory / "dosbox.conf"
        config.write_text("".join(settings), encoding="ascii")
        command = ["dosbox-x", "-conf", config, "-fastlaunch"]
        if len(game.floppies) <= 2:
            command.append("-nomenu")
        return command

    def play(self, game_id, game):
        with self.lock:
            self.stop_game()
            directory = SAVES / game_id
            directory.mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            settings = self.effective_settings(game_id)
            if game.pc88:
                command = m88_command(directory, game, settings)
                env.pop("LD_PRELOAD", None)
                env.update(WINEARCH="win32", WINEPREFIX="/config/wine",
                           WINEDLLOVERRIDES="mscoree,mshtml=", PULSE_SERVER="unix:/defaults/native")
            else:
                command = self.dosbox_command(directory, game, settings)
                env.update(SDL_VIDEODRIVER="x11", SDL_AUDIODRIVER="pulseaudio")
            with (directory / ("m88.log" if game.pc88 else "dosbox.log")).open("wb") as log:
                self.process = Popen(
                    command,
                    cwd=directory,
                    env=env,
                    stdout=log,
                    stderr=log,
                )


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, content_type, content):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def json_response(self, status, data):
        self.respond(status, "application/json", json.dumps(data).encode("utf-8"))

    def do_GET(self):
        path = urlsplit(self.path).path
        launcher = self.server.launcher
        if path == "/library/":
            self.respond(200, "text/html; charset=utf-8", Path("/opt/retroport/index.html").read_bytes())
        elif path == "/library/browser.html":
            self.respond(200, "text/html; charset=utf-8", Path("/opt/retroport/browser.html").read_bytes())
        elif path == "/library/browser.js":
            self.respond(200, "text/javascript; charset=utf-8", Path("/opt/retroport/browser.js").read_bytes())
        elif path == "/library/games":
            self.json_response(200, [
                {"id": key, "title": game.title, "genre": game.genre, "note": game.note,
                 "playable": game.playable, "browser": game.browser, "pc88": game.pc88,
                 "execution": launcher.effective_settings(key)["execution"]}
                for key, game in launcher.games.items()
            ])
        elif path.startswith("/library/settings/"):
            scope = path.removeprefix("/library/settings/")
            saved = launcher.settings
            if scope == "global":
                self.json_response(200, {"values": saved["global"], "defaults": {}})
            elif scope in launcher.games:
                self.json_response(200, {"values": saved["games"].get(scope, {}), "defaults": saved["global"]})
            else:
                self.send_error(404)
        elif path.startswith("/library/media/"):
            game_id, _, name = path.removeprefix("/library/media/").partition("/")
            game = self.server.launcher.games.get(game_id)
            if not game or not game.browser:
                self.send_error(404)
                return
            media = browser_media(game)
            if not name:
                self.json_response(200, {"title": game.title, "pc88": game.pc88, "files": list(media),
                                         "settings": launcher.effective_settings(game_id)})
            elif name in media:
                with media[name].open("rb") as source:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(os.fstat(source.fileno()).st_size))
                    self.end_headers()
                    copyfileobj(source, self.wfile)
            else:
                self.send_error(404)
        else:
            self.send_error(404)

    def do_POST(self):
        origin = f"{self.headers.get('X-Forwarded-Proto')}://{self.headers.get('Host')}"
        if self.headers.get("Origin") != origin:
            self.json_response(403, {"error": "게임 목록에서 실행해 주세요."})
            return
        if self.path.startswith("/library/settings/"):
            self.update_settings(self.path.removeprefix("/library/settings/"))
            return
        if self.path == "/library/stop":
            with self.server.launcher.lock:
                self.server.launcher.stop_game()
            self.json_response(200, {})
            return
        game_id = self.path.removeprefix("/library/play/")
        game = self.server.launcher.games.get(game_id)
        if not game or not game.playable:
            self.json_response(404, {"error": "이 게임의 실행 설정이 아직 준비되지 않았습니다."})
            return
        try:
            self.server.launcher.play(game_id, game)
        except OSError as error:
            self.log_error("%s", error)
            self.json_response(500, {"error": "게임을 시작하지 못했습니다."})
            return
        self.json_response(200, {})

    def update_settings(self, scope):
        launcher = self.server.launcher
        if scope != "global" and scope not in launcher.games:
            self.json_response(404, {"error": "게임 설정을 찾을 수 없습니다."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError
            values = validate_settings(json.loads(self.rfile.read(length)))
        except ValueError:
            self.json_response(400, {"error": "설정 값의 범위를 확인해 주세요."})
            return
        try:
            launcher.save_settings(scope, values)
        except OSError as error:
            self.log_error("%s", error)
            self.json_response(500, {"error": "설정을 저장하지 못했습니다."})
            return
        self.json_response(200, {})


if __name__ == "__main__":
    import sys
    os.execv(sys.executable, [sys.executable, str(Path(__file__).with_name("service.py"))])
