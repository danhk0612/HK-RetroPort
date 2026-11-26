import hashlib
import tempfile
from pathlib import Path
from subprocess import run

from PIL import Image, ImageDraw, ImageFont


def prepare_df3(entry, volume, font_file, directory):
    original = entry.read_bytes()
    if hashlib.sha256(original).hexdigest() != "016eacf123c88d9703319f9918038bc42d80268f89eb2f8e43f999245de77227":
        return entry.name
    dll = Path(__file__).with_name("DF3KR.DLL")
    version = hashlib.sha256(dll.read_bytes()).hexdigest()
    marker = directory / "df3-font-version"
    if marker.exists() and marker.read_text() == version:
        if run(["mdir", "-i", volume, "::/GAME/DF3KO.EXE"], capture_output=True).returncode == 0:
            return "DF3KO.EXE"

    # The three assets live beside the game's saves on its existing Windows 98 disk.
    with tempfile.TemporaryDirectory(dir=directory) as temp:
        folder = Path(temp)
        font = ImageFont.truetype(str(font_file), 16)
        cell = Image.new("1", (16, 16))
        draw = ImageDraw.Draw(cell)
        masks = bytearray(126 * 256 * 32)
        for lead in range(0x81, 0xff):
            for trail in range(0x41, 0xff):
                try:
                    char = bytes((lead, trail)).decode("cp949")
                except UnicodeDecodeError:
                    continue
                cell.paste(0, (0, 0, 16, 16))
                draw.text((0, 0), char, font=font, fill=1)
                offset = ((lead - 0x81) * 256 + trail) * 32
                masks[offset:offset + 32] = cell.tobytes()
        (folder / "DF3FONT.BIN").write_bytes(masks)
        (folder / "DF3KO.EXE").write_bytes(original.replace(b"GDI32.dll\0", b"DF3KR.dll\0", 1))
        for source in (dll, folder / "DF3FONT.BIN", folder / "DF3KO.EXE"):
            run(["mcopy", "-o", "-i", volume, source, "::/GAME/" + source.name], check=True)
    marker.write_text(version)
    return "DF3KO.EXE"
