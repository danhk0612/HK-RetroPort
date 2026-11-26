// SPDX-License-Identifier: GPL-2.0-only
const id = new URLSearchParams(location.search).get("game"),
  $ = (id) => document.getElementById(id);
const data = await (await fetch("/library/games")).json(),
  g = data.find((g) => g.id === id);
if (!g) throw Error("게임 없음");
$("title").textContent = g.title;
const resp = await (await fetch("/library/settings/" + id)).json(),
  prefs = { ...resp.defaults, ...resp.values };
const target = "d91019cc8090a8a5e086f78cd456370a8dc324dc95cf767768f8e3c6f5f62e89"; // catalog ID for dos/KAKYUHAN
const editor = g.commands === "KKSEDIT.EXE" && g.platform === "dos";
const flagKey = (editor ? "flags-" : "apply-") + target;
const flags = JSON.parse(localStorage.getItem(flagKey) || "{}");
let ci,
  muted = false;
async function readFlags() {
  const tree = await ci.fsTree(),
    out = {};
  for (const item of tree.nodes || [])
    if (/^FLAG[\w.]*$/i.test(item.name))
      out[item.name] = Array.from(await ci.fsReadFile(item.name));
  return out;
}
const props = Dos($("game"), {
  url:
    location.origin +
    "/library/bundle/" +
    id +
    "?v=5-" +
    encodeURIComponent(
      [g.commands, g.cd, prefs.dos_cycles, prefs.dos_memory].join("|"),
    ),
  pathPrefix: "/library/cores/jsdos/emulators/",
  opfsRoot: (await (await fetch("/library/storage.json")).json()) + "-" + id,
  backend: "dosbox",
  backendLocked: true,
  workerThread: true,
  autoStart: true,
  autoSave: true,
  noCloud: true,
  volume: (prefs.volume ?? 100) / 100,
  imageRendering: prefs.render ?? "pixelated",
  fsChanges: {
    local: true,
    urlToKey: () => location.origin + "/library/bundle/" + id + ".changes",
  },
  initFs:
    editor || id === target
      ? Object.entries(flags).map(([path, bytes]) => ({
          path: "HKFLAGS/" + path,
          contents: Uint8Array.from(bytes),
        }))
      : [],
  onEvent: async (event, command) => {
    if (event === "ci-ready") {
      if (editor || id === target) {
        for (const [path, bytes] of Object.entries(flags))
          await command.fsWriteFile(path, Uint8Array.from(bytes));
      }
      ci = command;
      $("status").textContent =
        "게임 화면을 클릭해 입력과 소리를 활성화하세요.";
    }
  },
});
$("exit").onclick = async () => {
  try {
    if (ci) {
      if (id === target)
        localStorage.setItem(
          "flags-" + target,
          JSON.stringify(await readFlags()),
        );
      if (!(await props.save())) throw Error("브라우저 저장에 실패했습니다.");
      if (id === target) localStorage.removeItem("apply-" + target);
    }
    await props.stop();
    location.assign("/library/");
  } catch (e) {
    $("status").textContent = e.message;
  }
};
$("full").onclick = () => props.setFullScreen(true);
$("release").onclick = () => document.exitPointerLock();
$("mute").onclick = () => {
  muted = !muted;
  props.setVolume(muted ? 0 : (prefs.volume ?? 100) / 100);
  $("mute").textContent = muted ? "소리 켜기" : "음소거";
};
$("apply").hidden = !editor;
$("apply").onclick = async () => {
  try {
    if (!ci) throw Error("먼저 에디터를 실행하세요.");
    const flags = await readFlags();
    if (!Object.keys(flags).length) throw Error("적용할 FLAG 파일이 없습니다.");
    localStorage.setItem("apply-" + target, JSON.stringify(flags));
    $("status").textContent = "다음 브라우저 하급생 실행에 적용됩니다.";
  } catch (e) {
    $("status").textContent = e.message;
  }
};
addEventListener(
  "keydown",
  (e) => {
    if (e.code === prefs.exitkey) {
      e.preventDefault();
      $("exit").click();
    }
  },
  true,
);
