export async function clean() {
  const res = await fetch("/library/purged");
  if (!res.ok) return;
  const removed = await res.json();
  if (!removed.length) return;
  const namespace = (await (await fetch("/library/storage.json")).json());
  for (const { id } of removed) {
    if (localStorage.getItem("purged-" + id)) continue;
    const root = await navigator.storage.getDirectory();
    try {
      await root.removeEntry((namespace + "-") + id, { recursive: true });
    } catch (e) {
      if (e.name !== "NotFoundError") throw e;
    }
    for (const info of await indexedDB.databases()) {
      if (![(namespace + "-browser"), "/quasi88"].includes(info.name)) continue;
      await new Promise((resolve, reject) => {
        const req = indexedDB.open(info.name);
        req.onerror = () => reject(req.error);
        req.onsuccess = () => {
          const db = req.result;
          const store = info.name === (namespace + "-browser") ? "disks" : "FILE_DATA";
          if (!db.objectStoreNames.contains(store)) {
            db.close();
            resolve();
            return;
          }
          const tx = db.transaction(store, "readwrite"),
            cursor = tx.objectStore(store).openCursor();
          cursor.onsuccess = () => {
            const c = cursor.result;
            if (!c) return;
            const key = String(c.key);
            if (
              key.startsWith(id + "/") ||
              key.startsWith("/quasi88/DISK/" + id.slice(0, 16) + "-")
            )
              c.delete();
            c.continue();
          };
          tx.oncomplete = () => {
            db.close();
            resolve();
          };
          tx.onabort = () => reject(tx.error);
        };
      });
    }
    localStorage.removeItem("flags-" + id);
    localStorage.removeItem("apply-" + id);
    localStorage.setItem("purged-" + id, "1");
  }
}
