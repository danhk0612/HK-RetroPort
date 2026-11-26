const canvas = document.querySelector('#screen');
const player = document.querySelector('#player');
const status = document.querySelector('#status');
const start = document.querySelector('#start');
const sound = document.querySelector('#sound');
const fullscreen = document.querySelector('#fullscreen');
const stop = document.querySelector('#stop');
const drives = document.querySelector('#drives');
const id = new URLSearchParams(location.search).get('game');
const media = '/library/media/' + encodeURIComponent(id ?? '');
const corePath = '/library/cores/';
let flushSaves = async () => {};
let muted = false;

function audioContext() {
  return (window.Module?.SDL2 ?? window.SDL2)?.audioContext;
}

fullscreen.onclick = async () => {
  if (document.fullscreenElement) await document.exitFullscreen();
  else {
    player.style.setProperty('--screen-aspect', canvas.width / canvas.height);
    await player.requestFullscreen();
  }
  canvas.focus();
};
document.addEventListener('fullscreenchange', () => {
  fullscreen.textContent = document.fullscreenElement ? '전체 화면 해제' : '전체 화면';
});
sound.onclick = async () => {
  const context = audioContext();
  if (!context) return;
  if (muted) await context.resume();
  else await context.suspend();
  muted = !muted;
  sound.setAttribute('aria-pressed', String(muted));
  canvas.focus();
};
canvas.addEventListener('pointerdown', () => {
  canvas.focus();
  if (!muted) audioContext()?.resume();
});

stop.onclick = async () => {
  stop.disabled = true;
  try {
    await flushSaves();
    location.assign('/library/');
  } catch {
    status.textContent = '브라우저 저장에 실패했습니다. 잠시 뒤 종료를 다시 눌러 주세요.';
    stop.disabled = false;
  }
};

async function fetchFile(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error('파일을 불러오지 못했습니다.');
  return response;
}

async function openSaves() {
  const database = (await (await fetch("/library/storage.json")).json()) + "-browser";
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(database, 1);
    request.onupgradeneeded = () => request.result.createObjectStore('disks');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function readSave(db, name) {
  return new Promise((resolve, reject) => {
    const request = db.transaction('disks').objectStore('disks').get(id + '/' + name);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function trackSaves(fs, db, paths) {
  const modified = new Map(paths.map(path => [path, fs.stat(path).mtime.getTime()]));
  let pending;
  function saveChanges() {
    if (pending) return pending;
    const changes = paths.map(path => [path, fs.stat(path).mtime.getTime()])
      .filter(([path, time]) => modified.get(path) !== time);
    if (!changes.length) return Promise.resolve();

    pending = new Promise((resolve, reject) => {
      const transaction = db.transaction('disks', 'readwrite');
      const store = transaction.objectStore('disks');
      for (const [path] of changes) {
        store.put(fs.readFile(path), id + '/' + path.split('/').pop());
      }
      transaction.oncomplete = () => {
        for (const [path, time] of changes) modified.set(path, time);
        resolve();
      };
      transaction.onabort = () => reject(transaction.error);
    }).finally(() => { pending = undefined; });
    return pending;
  }

  function autosave() {
    saveChanges().catch(() => {
      status.textContent = '브라우저에 게임 진행 상황을 저장하지 못했습니다.';
    });
  }
  setInterval(autosave, 2000);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) autosave();
  });
  return async () => {
    await pending;
    await saveChanges();
  };
}

function setFloppyControls(floppies) {
  if (floppies.length < 2) return;
  for (let drive = 0; drive < 2; drive++) {
    const label = document.createElement('label');
    const list = document.createElement('select');
    list.add(new Option('비어 있음', ''));
    floppies.forEach(({name}, index) => list.add(new Option(`디스크 ${index + 1}`, '/disk/' + name)));
    list.selectedIndex = drive + 1;
    list.onchange = () => {
      const ccall = window.Module.ccall ?? window.ccall;
      ccall('webnp2_set_fdd', null, ['number', 'string'], [drive, list.value]);
      canvas.focus();
    };
    label.append(`FDD ${drive + 1}`, list);
    drives.append(label);
  }
}

function runPC98(roms, floppies, hardDisks, db, settings) {
  const config = ['[NekoProject21kai]', `ExMemory=${settings.pc98_memory ?? 1}`,
    'SNDboard=4', 'USEFMGEN=true', `clk_mult=${settings.pc98_clock ?? 8}`];
  const font = roms.find(file => file.name.startsWith('font.'));
  if (font) config.push('fontfile=/' + font.name);
  hardDisks.forEach(({name}, index) => config.push(`HDD${index + 1}FILE=/disk/${name}`));
  return {
    arguments: floppies.slice(0, 2).map(({name}) => '/disk/' + name),
    preRun: [() => {
      const fs = window.Module.FS ?? window.FS;
      fs.mkdir('/disk');
      for (const {name, data} of roms) fs.writeFile('/' + name, data);
      for (const {name, data} of [...floppies, ...hardDisks]) fs.writeFile('/disk/' + name, data);
      fs.writeFile('/np21kai.cfg', config.join('\n') + '\n');
    }],
    onRuntimeInitialized: () => {
      const fs = window.Module.FS ?? window.FS;
      if (db) flushSaves = trackSaves(fs, db, [...floppies, ...hardDisks].map(({name}) => '/disk/' + name));
      setFloppyControls(floppies);
      showRunning();
    },
  };
}

function runPC88(roms, floppies, settings) {
  return {
    noInitialRun: true,
    onRuntimeInitialized: () => {
      const module = window.Module;
      const fs = module.FS;
      flushSaves = () => new Promise((resolve, reject) => {
        fs.syncfs(false, error => error ? reject(error) : resolve());
      });
      for (const {name, data} of roms) fs.writeFile('/quasi88/ROM/' + name, data);
      const diskPaths = floppies.map(({name, data}) => {
        const path = `/quasi88/DISK/${id.slice(0, 16)}-${name}`;
        if (!fs.analyzePath(path).exists) fs.writeFile(path, data);
        return path;
      });
      const menu = document.createElement('button');
      menu.textContent = '디스크 및 설정';
      menu.onclick = () => module.ccall('quasi88_post_menu_event', null, [], []);
      drives.append(menu);
      const clock = settings.pc88_clock ? ['-clock', String(settings.pc88_clock)] : [];
      const args = ['-romdir', '/quasi88/ROM', '-diskdir', '/quasi88/DISK',
        '-samplefreq', '48000', ...clock, ...diskPaths.slice(0, 2)];
      showRunning();
      module.callMain(args);
    },
  };
}

function showRunning() {
  drives.hidden = !drives.childElementCount;
  sound.hidden = false;
  fullscreen.hidden = false;
  status.textContent = '게임 화면을 클릭하면 키보드 입력과 소리가 활성화됩니다.';
  canvas.focus();
}

async function prepare() {
  const manifest = await (await fetchFile(media)).json();
  document.querySelector('#title').textContent = manifest.title;
  canvas.style.imageRendering=manifest.settings.render==='smooth'?'auto':'pixelated';
  document.addEventListener('keydown',event=>{if(event.code===manifest.settings.exitkey){event.preventDefault();stop.click()}},true);
  if(manifest.settings.volume!==undefined){
    const connect=AudioNode.prototype.connect;
    const gains=new WeakMap();
    AudioNode.prototype.connect=function(destination,...args){
      if(destination instanceof AudioDestinationNode){
        let gain=gains.get(destination);
        if(!gain){
          gain=this.context.createGain();
          gain.gain.value=manifest.settings.volume/100;
          connect.call(gain,destination);
          gains.set(destination,gain);
        }
        return connect.call(this,gain,...args);
      }
      return connect.call(this,destination,...args);
    };
  }
  const db = manifest.pc88 ? null : await openSaves();
  const files = await Promise.all(manifest.files.map(async name => {
    const disk = /^(fd|hd)\d+\./.test(name);
    const saved = disk && db ? await readSave(db, name) : null;
    const data = saved ?? new Uint8Array(await (await fetchFile(media + '/' + name)).arrayBuffer());
    return {name, data};
  }));
  const floppies = files.filter(file => /^fd\d+\./.test(file.name));
  const hardDisks = files.filter(file => /^hd\d+\./.test(file.name));
  const roms = files.filter(file => !floppies.includes(file) && !hardDisks.includes(file));

  start.disabled = false;
  status.textContent = '시작 버튼을 누르면 이 브라우저에서 게임을 실행합니다.';
  start.onclick = () => {
    start.hidden = true;
    status.textContent = '에뮬레이터를 시작하는 중입니다.';
    const options = manifest.pc88 ? runPC88(roms, floppies, manifest.settings)
      : runPC98(roms, floppies, hardDisks, db, manifest.settings);
    window.Module = {
      canvas,
      locateFile: name => corePath + name,
      onAbort: () => { status.textContent = '에뮬레이터를 시작하지 못했습니다. 서버 실행으로 시도해 주세요.'; },
      ...options,
    };
    const script = document.createElement('script');
    script.src = corePath + (manifest.pc88 ? 'quasi88.js' : 'emnp21kai_sdl2.js');
    script.onerror = window.Module.onAbort;
    document.body.append(script);
  };
}

prepare().catch(error => { status.textContent = error.message; });
