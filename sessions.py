import hashlib
import hmac
import http.client
import logging
import ntpath
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import socketserver
from threading import Lock, Thread
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit

import docker
from docker.errors import NotFound
from docker.types import Mount

LOG = logging.getLogger("sessions")
client = docker.from_env(timeout=90)
project = client.containers.get(socket.gethostname()).labels["com.docker.compose.project"]
labels = {"retroport.owner": project, "retroport.role": "player"}
lock = Lock()
seen = {}
limit = int(os.environ.get("RETROPORT_MAX_SESSIONS", "4"))
idle = int(os.environ.get("RETROPORT_IDLE_SECONDS", "1800"))
key_path = Path("/identity/cookie.key")
if not key_path.exists():
    key_path.write_bytes(secrets.token_bytes(32))
    key_path.chmod(0o600)
key = key_path.read_bytes()


def signed(value):
    return value + "." + hmac.digest(key, value.encode(), "sha256").hex()


def ready(endpoint):
    conn = http.client.HTTPConnection("localhost", timeout=2)
    try:
        conn.sock = socket.socket(socket.AF_UNIX)
        conn.sock.settimeout(2)
        conn.sock.connect(str(endpoint))
        conn.request("GET", "/library/")
        return conn.getresponse().status == 200
    except OSError:
        return False
    finally:
        conn.close()


def child_path(parent, child):
    return ntpath.join(parent, child) if ntpath.splitdrive(parent)[0] else str(Path(parent) / child)


def worker(uid, start):
    # Called under lock. The browser supplies neither paths nor Docker options.
    name = f"{project}-session-{uid}"
    endpoint = Path("/endpoints") / uid
    try:
        container = client.containers.get(name)
        if not all(container.labels.get(k) == v for k, v in labels.items()):
            raise ValueError("worker label mismatch")
        if container.status != "running":
            container.remove(force=True)
            raise NotFound("inactive worker")
    except NotFound:
        if not start:
            return False
        if len(client.containers.list(filters={"label": [f"{k}={v}" for k,v in labels.items()]})) >= limit:
            return False
        admin, = client.containers.list(filters={"label": [
            f"com.docker.compose.project={project}", "retroport.catalog=true"]})
        own = client.containers.get(socket.gethostname())
        hosts = {m["Destination"]: m["Source"] for m in own.attrs["Mounts"]}
        (Path("/players") / uid).mkdir(exist_ok=True)
        endpoint.mkdir(exist_ok=True)
        (endpoint / "stream.sock").unlink(missing_ok=True)
        mounts = [Mount(m["Destination"], m["Source"], type="bind", read_only=True)
                  for m in admin.attrs["Mounts"] if m["Destination"] in ("/collections", "/settings", "/library")]
        for target, parent in (("/config", "/players"), ("/endpoint", "/endpoints")):
            mounts.append(Mount(target, child_path(hosts[parent], uid), type="bind"))
        container = client.containers.run(admin.image.id, detach=True, name=name, labels=labels | {"com.docker.compose.project": project + "-players", "com.docker.compose.service": "runtime"},
            network_mode="none", mounts=mounts, shm_size="1g",
            environment={"RETROPORT_PLAYER":"1","START_DOCKER":"false","PIXELFLUX_WAYLAND":"false",
                         "TITLE":"HK-RetroPort","PUID":os.environ.get("PUID","911"),"PGID":os.environ.get("PGID","911")},
            entrypoint=["/bin/sh","-ec"], command=[
                "sed -i '/listen 3000 default_server;/a\\  listen unix:/endpoint/stream.sock;' /defaults/default.conf\nexec /init"])
    seen[uid] = time.monotonic()
    if start:
        for _ in range(120):
            if ready(endpoint / "stream.sock"):
                return True
            time.sleep(.5)
        LOG.error("Worker startup timed out: %s", name)
        container.remove(force=True)
        return False
    return True


class Auth(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # Never log visitor cookies.

    def do_GET(self):
        route = urlsplit(self.headers.get("X-Route", "")).path
        method = self.headers.get("X-Method")
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        cookie_name = os.environ.get("RETROPORT_STORAGE_NAMESPACE", "retroport") + "_player"
        item = cookie.get(cookie_name)
        token = item.value if item else ""
        valid = bool(re.fullmatch(r"[0-9a-f]{48}\.[0-9a-f]{64}", token)) and hmac.compare_digest(token, signed(token[:48]))
        if self.path != "/authorize":
            return self.send_error(404)
        if route == "/library/" and method in ("GET", "HEAD"):
            self.send_response(204)
            if not valid:
                token = signed(secrets.token_hex(24))
                self.send_header("Set-Cookie", f"{cookie_name}={token}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax")
            self.end_headers()
            return
        if not valid:
            return self.send_error(403)
        origin = self.headers.get("Origin", "")
        allowed = ["http://" + self.headers["X-Public-Host"], "https://" + self.headers["X-Public-Host"]]
        if (method != "GET" or origin) and origin not in allowed:
            return self.send_error(403)
        uid = hashlib.sha256(token.encode()).hexdigest()[:32]
        try:
            with lock:
                ok = worker(uid, method == "POST" and re.fullmatch(r"/library/play/[0-9a-f]{32}(?:[0-9a-f]{32})?", route))
            if not ok:
                return self.send_error(403)
        except Exception:
            LOG.exception("Cannot route player")
            return self.send_error(503)
        self.send_response(204)
        self.send_header("X-Worker", uid)
        self.end_headers()


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def remove_worker(container):
    container.stop(timeout=15)
    container.remove()
    seen.pop(container.name.rsplit("-", 1)[-1], None)


def sessions():
    return client.containers.list(all=True, filters={"label":[f"{k}={v}" for k,v in labels.items()]})


def reap():
    while True:
        time.sleep(30)
        try:
            with lock:
                for c in sessions():
                    uid = c.name.rsplit("-", 1)[-1]
                    if time.monotonic() - seen.setdefault(uid,time.monotonic()) < idle:
                        continue
                    # Keep a live Selkies connection even during long games without HTTP requests.
                    if c.status == "running" and c.exec_run(["sh","-c","ss -Htn state established '( sport = :8082 )' | grep -q ."]).exit_code == 0:
                        seen[uid] = time.monotonic()
                    else:
                        remove_worker(c)
        except Exception:
            LOG.exception("Worker cleanup failed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    path = Path("/broker/control.sock")
    path.unlink(missing_ok=True)
    with Server(str(path), Auth) as server:
        path.chmod(0o666)
        Thread(target=reap, daemon=True).start()
        signal.signal(signal.SIGTERM, lambda *_: Thread(target=server.shutdown, daemon=True).start())
        try:
            server.serve_forever()
        finally:
            with lock:
                for c in sessions():
                    remove_worker(c)
