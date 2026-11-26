"""Set the sole operator credential from the Docker host."""
import getpass
import os
from pathlib import Path
import subprocess
import sys
import tempfile

if not sys.stdin.isatty():
    sys.exit("대화형 터미널에서 실행하세요.")
password = getpass.getpass("운영자(admin) 새 암호: ")
if not password or password != getpass.getpass("암호 확인: "):
    sys.exit("암호가 비었거나 일치하지 않습니다.")
hashed = subprocess.check_output(
    ["openssl", "passwd", "-6", "-stdin"], input=password + "\n", text=True
).strip()
with tempfile.NamedTemporaryFile(mode="w", dir="/auth", delete=False) as out:
    out.write("admin:" + hashed + "\n")
    os.fchown(out.fileno(), 0, 33)
    os.fchmod(out.fileno(), 0o640)
os.replace(out.name, Path("/auth/htpasswd"))
print("운영자 암호를 저장했습니다.")
