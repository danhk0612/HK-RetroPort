import { clean } from "/library/cleanup.js";
const $ = (id) => document.getElementById(id);
const api = async (path, data) => {
  const resp = await fetch(
    "/library/" + path,
    data === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        },
  );
  const result = await resp.json();
  if (!resp.ok) throw Error(result.error);
  return result;
};
function run(fn) {
  return async (e) => {
    e?.preventDefault();
    try {
      await fn(e);
    } catch (err) {
      $("status").textContent = err.message;
    }
  };
}
let games = [],
  token,
  preview = [],
  generation = 0;
const current = () => games.find((g) => g.id === $("pick").value);
async function showCore() {
  const core = await api("manage/cores");
  $("core-info").textContent = "PC-98 브라우저 실행기 · " + (core.installed ? "설치됨" : "추가 가능");
  $("core-source").href = core.source;
  $("core-source").textContent = "원본 파일 · " + core.version.slice(0, 12);
  $("core-files").textContent = "필수 파일 · " + core.files.join(", ");
}
$("core-install").onclick = run(async () => {
  const files = [...$("core-input").files];
  if (!files.length) throw Error("설치할 파일을 선택하세요.");
  const zip = files.length === 1 && files[0].name.toLowerCase().endsWith(".zip");
  const form = new FormData();
  files.forEach(file => form.append("file", file));
  const result = await fetch("/library/manage/cores/pc98", {
    method: "POST", headers: zip ? {"Content-Type": "application/zip"} : {},
    body: zip ? files[0] : form,
  });
  if (!result.ok) throw Error((await result.json()).error);
  await showCore();
  $("status").textContent = "PC-98 코어를 설치했습니다.";
});
run(showCore)();
const fields = {
  title: "한글 제목",
  english: "영문 제목",
  work: "동일 작품 그룹",
  genre: "한글 장르",
  note: "영문 장르",
  publisher: "제작사",
  language: "언어",
  year: "발매 시기",
  region: "발매 지역",
  verification: "검증 결과",
  description: "설명",
  commands: "DOS 시작 명령 (한 줄에 하나)",
  disks: "디스크 순서 (파일 경로, 한 줄에 하나)",
  font: "글꼴 파일",
  cd: "CD 이미지",
  icon: "아이콘 파일",
  screenshots: "스크린샷 파일 (한 줄에 하나)",
  manual: "매뉴얼 파일",
};
function input(parent, name, label, options) {
  const wrap = document.createElement("label");
  wrap.textContent = label;
  const el = document.createElement(
    options
      ? "select"
      : ["commands", "disks", "screenshots", "description"].includes(name)
        ? "textarea"
        : "input",
  );
  el.name = name;
  if (options) for (const [k, v] of options) el.add(new Option(v, k));
  wrap.append(el);
  parent.append(wrap);
  return el;
}
for (const [k, v] of Object.entries(fields)) {
  const el = input($("fields"), k, v);
  if (["icon", "font", "manual", "cd"].includes(k))
    el.setAttribute("list", "paths");
}
const configs = {
  execution: [
    "실행 위치",
    [
      ["browser", "브라우저"],
      ["server", "Docker 서버"],
    ],
  ],
  pc98_server: [
    "PC-98 서버 실행기 (단일 HDI)선택",
    [
      ["dosbox", "DOSBox-X"],
      ["anex", "Anex86"],
    ],
  ],
  dos_cycles: ["DOS CPU 사이클"],
  dos_memory: ["DOS 메모리 (MB)"],
  pc98_clock: ["PC-98 CPU 배율"],
  pc98_memory: ["PC-98 메모리 (MB)"],
  pc88_clock: ["PC-88 MHz"],
  volume: ["브라우저 소리 (0~100)"],
  render: [
    "브라우저 화면",
    [
      ["pixelated", "픽셀"],
      ["smooth", "부드럽게"],
    ],
  ],
  exitkey: [
    "브라우저 저장 후 종료 키",
    [
      ["None", "없음"],
      ["F9", "F9"],
      ["F10", "F10"],
    ],
  ],
};
for (const [k, [label, options]] of Object.entries(configs)) {
  const el = input(
    $("prefs").querySelector("fieldset"),
    k,
    label,
    options && [["", "상속"], ...options],
  );
  if (!options) el.type = "number";
}
function scope() {
  return $("scope").value === "game" ? current().id : $("scope").value;
}
async function prefs() {
  const id = scope(),
    res = await api("settings/" + id);
  if (id !== scope()) return;
  for (const k of Object.keys(configs)) {
    const field = $("prefs").elements[k];
    field.value = res.values[k] ?? "";
    field.placeholder = res.defaults[k] ?? "기본값";
    if (field.options)
      field.options[0].textContent = "상속 · " + (res.defaults[k] ?? "기본값");
  }
}
async function select() {
  const seq = ++generation,
    g = current();
  if (!g) return;
  for (const k in fields) $("edit").elements[k].value = g[k] ?? "";
  $("apply").hidden = !g.title.includes("세이브 에디터");
  const names = await api("files/" + g.id);
  if (seq !== generation) return;
  $("paths").replaceChildren(...names.map((n) => new Option(n, n)));
  await prefs();
}
function filter(id) {
  const term = $("search").value.toLowerCase();
  const list = games.filter((g) =>
    (g.title + " " + g.platform).toLowerCase().includes(term),
  );
  $("pick").replaceChildren(
    ...list.map(
      (g) => new Option(g.title + " · " + g.platform.toUpperCase(), g.id),
    ),
  );
  if (list.length) {
    $("pick").value = list.some((g) => g.id === id) ? id : list[0].id;
    return select();
  }
}
async function load(id) {
  games = await api("games");
  await filter(id);
}
$("pick").onchange = run(select);
$("search").oninput = run(() => filter());
$("scope").onchange = run(prefs);
$("edit").onsubmit = run(async () => {
  const g = current(),
    data = Object.fromEntries(new FormData($("edit")));
  // An untouched legacy disk/font setting keeps its imported emulator profile.
  for (const k of ["disks", "font"]) if (!(k in g) && !data[k]) delete data[k];
  await api("edit/" + g.id, data);
  await load(g.id);
  $("status").textContent = "게임 정보를 저장했습니다.";
});
$("test").onclick = () => location.assign("/library/?play=" + current().id);
$("trash").onclick = run(async () => {
  await api("trash/" + current().id, {});
  await load();
  $("status").textContent = "휴지통으로 이동했습니다.";
});
$("apply").onclick = run(async () => {
  await api("apply/" + current().id, {});
  $("status").textContent = "서버 하급생 세이브에 적용했습니다.";
});
$("prefs").onsubmit = run(async () => {
  const values = {};
  for (const [k, v] of new FormData($("prefs")))
    if (v !== "") values[k] = configs[k][1] ? v : Number(v);
  await api("settings/" + scope(), values);
  await prefs();
  $("status").textContent = "실행 설정을 저장했습니다.";
});
$("reset").onclick = run(async () => {
  await api("settings/" + scope(), {});
  await prefs();
});
$("folder").onchange = () => ($("archive").value = "");
$("archive").onchange = () => ($("folder").value = "");
$("preview").onclick = run(async () => {
  const archive = $("archive").files[0],
    items = archive ? [archive] : Array.from($("folder").files);
  if (!items.length) throw Error("폴더 또는 압축 파일을 선택하세요.");
  $("preview").disabled = true;
  try {
    if (token) await api("cancel/" + token, {});
    token = (await api("stage", {})).token;
    for (const [i, f] of items.entries()) {
      $("status").textContent = "파일 전송 " + (i + 1) + " / " + items.length;
      const resp = await fetch(
        "/library/upload/" +
          token +
          (archive ? "" : "?file=" + encodeURIComponent(f.webkitRelativePath)),
        { method: "POST", body: f },
      );
      if (!resp.ok) throw Error("전송 실패 · " + f.name);
    }
    preview = await api("preview/" + token, {});
    $("imports").replaceChildren();
    for (const [i, item] of preview.entries()) {
      const box = document.createElement("fieldset");
      $("imports").append(box);
      input(box, "title" + i, "제목").value = item.title;
      input(box, "platform" + i, "기종", [
        ["dos", "DOS"],
        ["pc98", "PC-98"],
        ["pc88", "PC-88"],
      ]).value = item.platform;
      const cmd = input(box, "cmd" + i, "시작 명령");
      cmd.value = item.commands;
      const dl = document.createElement("datalist");
      dl.id = "cmdlist" + i;
      cmd.setAttribute("list", dl.id);
      dl.append(...item.choices.map((n) => new Option(n, n)));
      box.append(dl);
    }
    const b = document.createElement("button");
    b.textContent = "목록에 등록";
    $("imports").append(b);
    $("status").textContent = preview.length + "개 후보를 확인하세요.";
  } finally {
    $("preview").disabled = false;
  }
});
$("imports").onsubmit = run(async () => {
  const form = $("imports");
  const items = preview.map((g, i) => ({
    folder: g.folder,
    title: form.elements["title" + i].value,
    platform: form.elements["platform" + i].value,
    commands: form.elements["cmd" + i].value,
  }));
  const results = await api("import/" + token, { items });
  token = null;
  form.replaceChildren();
  await load(results[0]?.id);
  $("status").textContent =
    results.filter((r) => r.state === "added").length +
    "개 등록 · 기존/휴지통 " +
    results.filter((r) => r.state !== "added").length +
    "개";
});
$("attach").onclick = run(async () => {
  const g = current(),
    file = $("attachment").files[0];
  if (!file) throw Error("파일을 선택하세요.");
  const res = await fetch(
    "/library/attachment/" +
      g.id +
      "?field=" +
      $("attachmentType").value +
      "&name=" +
      encodeURIComponent(file.name),
    { method: "POST", body: file },
  );
  if (!res.ok) throw Error((await res.json()).error);
  await load(g.id);
  $("status").textContent = "자료를 첨부했습니다.";
});
async function trash() {
  const rows = await api("trash");
  const list = $("bin").querySelector("ul");
  list.replaceChildren();
  if (!rows.length) list.textContent = "휴지통이 비어 있습니다.";
  for (const r of rows) {
    const li = document.createElement("li");
    li.textContent = r.title;
    for (const [op, label] of [
      ["restore", "복원"],
      ["purge", "완전 삭제"],
    ]) {
      const b = document.createElement("button");
      b.textContent = label;
      b.onclick = run(async () => {
        if (
          op === "purge" &&
          !confirm(r.title + "의 웹 사본과 저장 데이터를 완전히 삭제할까요?")
        )
          return;
        await api(op + "/" + r.id, { confirm: r.id });
        await clean();
        await trash();
      });
      li.append(b);
    }
    list.append(li);
  }
}
run(async () => {
  await clean();
  if (location.pathname.includes("/trash/")) {
    $("active").hidden = true;
    $("bin").hidden = false;
    await trash();
  } else await load();
})();
