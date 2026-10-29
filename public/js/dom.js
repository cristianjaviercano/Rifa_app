// Construcción de DOM segura: todo texto entra por nodos de texto, nunca por innerHTML.
export function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

export const money = (n, cur = "COP") =>
  new Intl.NumberFormat("es-CO", { style: "currency", currency: cur, maximumFractionDigits: 0 }).format(Number(n));
export const fmtDate = (iso) => new Date(iso).toLocaleString("es-CO", { dateStyle: "medium", timeStyle: "short" });
export const padNum = (n, total) => String(n).padStart(String(Math.max(total - 1, 1)).length, "0");

export function remaining(iso) {
  const ms = new Date(iso) - Date.now();
  if (ms <= 0) return "00:00:00";
  const s = Math.floor(ms / 1000);
  const p = (x) => String(x).padStart(2, "0");
  const d = Math.floor(s / 86400);
  const hms = `${p(Math.floor((s % 86400) / 3600))}:${p(Math.floor((s % 3600) / 60))}:${p(s % 60)}`;
  return d ? `${d}d ${hms}` : hms;
}

/** Texto que se actualiza cada segundo hasta que el contenedor sale del DOM. */
export function liveCountdown(iso, prefix = "") {
  const el = h("span", { class: "num" }, prefix + remaining(iso));
  const t = setInterval(() => {
    if (!el.isConnected) return clearInterval(t);
    el.textContent = prefix + remaining(iso);
  }, 1000);
  return el;
}

export function toast(msg, kind = "") {
  const box = document.getElementById("toasts");
  const t = h("div", { class: "toast " + kind }, msg);
  box.append(t);
  setTimeout(() => t.remove(), 4200);
}

/** Diálogo modal accesible (<dialog>). Devuelve una promesa con el valor de cierre. */
export function modal(content, { actions } = {}) {
  return new Promise((resolve) => {
    const dlg = h("dialog", { "aria-modal": "true" });
    const close = (v) => { dlg.close(); dlg.remove(); resolve(v); };
    dlg.append(h("div", { class: "in stack" }, content, h("div", { class: "row" }, (actions || []).map((a) =>
      h("button", { class: "btn " + (a.cls || ""), type: "button", onclick: () => close(a.value) }, a.label)))));
    dlg.addEventListener("cancel", () => close(undefined));
    document.body.append(dlg);
    dlg.showModal();
  });
}

export const chip = (text, kind) => h("span", { class: "chip " + kind }, text);
export const skeleton = (n = 3) => Array.from({ length: n }, () => h("div", { class: "skeleton" }));
