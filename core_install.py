from email import policy
from email.parser import BytesParser
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZipFile

ROOT = Path("/operator-cores")
VERSION = "0fe85a59622645740dfb4cdb6abd59c8bb3c927b"
SOURCE = f"https://github.com/uraraworks/WebNP2/tree/{VERSION}/public/core"
FILES = {
    "emnp21kai_sdl2.js": "953419968b5c4375177c471c1c2b326d03b05c0adb18355011df7527f3da2e77",
    "emnp21kai_sdl2.wasm": "95244f8001ee7b2f7e26fb104065eb34ac007623798f4b6b3dd576d13438201a",
    "LICENSE.NP2kai": "4dcb041b83a1bee1cfb542dc8f815c731f3c5b8dbb5268b2eb7fc932c3ff63fe",
}
LIMIT = 12 * 1024 * 1024


def available():
    return all((ROOT / VERSION / name).is_file() for name in FILES)


def install(content_type, body):
    if content_type == "application/zip":
        try:
            with ZipFile(BytesIO(body)) as archive:
                selected = [i for i in archive.infolist() if Path(i.filename).name in FILES]
                if len(selected) != len(FILES) or sum(i.file_size for i in selected) > LIMIT:
                    raise ValueError("지원 버전의 코어 파일 세 개를 선택하세요.")
                parts = [(Path(i.filename).name, archive.read(i)) for i in selected]
        except (BadZipFile, RuntimeError, NotImplementedError) as error:
            raise ValueError("지원하는 ZIP 파일을 선택하세요.") from error
    elif content_type.startswith("multipart/form-data;"):
        message = BytesParser(policy=policy.default).parsebytes(
            b"Content-Type: " + content_type.encode("ascii") + b"\r\n\r\n" + body
        )
        parts = [(p.get_filename(), p.get_payload(decode=True)) for p in message.iter_parts()]
    else:
        raise ValueError("ZIP 또는 코어 파일을 선택하세요.")
    if len(parts) != len(FILES) or {name for name, _ in parts} != FILES.keys():
        raise ValueError("필수 파일의 이름과 개수를 확인하세요.")
    with TemporaryDirectory(dir=ROOT) as tmp:
        ready = Path(tmp) / "core"
        ready.mkdir()
        for name, payload in parts:
            if sha256(payload or b"").hexdigest() != FILES[name]:
                raise ValueError(f"{name} 파일이 지원 버전과 다릅니다.")
            (ready / name).write_bytes(payload)
        if not available():
            ready.rename(ROOT / VERSION)
