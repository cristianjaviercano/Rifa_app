import { h } from "./dom.js";
import { auth } from "./api.js";
import { loadConfig, loadUser, logout, state } from "./state.js";
import { homeView } from "./views/home.js";
import { loginView } from "./views/login.js";
import { raffleView } from "./views/raffle.js";
import { payView } from "./views/pay.js";
import { mineView } from "./views/mine.js";
import { adminListView, adminNewView, adminRaffleView } from "./views/admin.js";

const ROUTES = [
  [/^\/$/, homeView],
  [/^\/login$/, loginView],
  [/^\/r\/([\w-]+)$/, raffleView],
  [/^\/pay\/([\w-]+)$/, payView],
  [/^\/mine$/, mineView],
  [/^\/admin$/, adminListView],
  [/^\/admin\/new$/, adminNewView],
  [/^\/admin\/r\/([\w-]+)$/, adminRaffleView],
];
const root = document.getElementById("app");
let cleanups = [];
let renderToken = 0;

const ctx = {
  onCleanup: (fn) => cleanups.push(fn),
  go: (path) => { location.hash = "#" + path; },
};

function renderChrome(path) {
  document.getElementById("who").textContent = state.user ? state.user.name : "";
  const tab = (href, ico, label, match) => h("a", { href: "#" + href, "aria-current": match ? "page" : null },
    h("span", { class: "ico", "aria-hidden": "true" }, ico), label);
  document.getElementById("tabs").replaceChildren(
    tab("/", "🎟", "Rifas", path === "/" || path.startsWith("/r/") || path.startsWith("/pay/")),
    tab("/mine", "🧾", "Mis compras", path === "/mine"),
    tab("/admin", "⚙", "Administrar", path.startsWith("/admin")),
    state.user
      ? h("a", { href: "#/login", onclick: (e) => { e.preventDefault(); logout(); renderChrome("/"); ctx.go("/"); } },
          h("span", { class: "ico", "aria-hidden": "true" }, "⎋"), "Salir")
      : tab("/login", "👤", "Entrar", path === "/login"));
}

async function route() {
  const path = location.hash.slice(1) || "/";
  cleanups.forEach((f) => { try { f(); } catch { /* ignore */ } });
  cleanups = [];
  const token = ++renderToken;
  renderChrome(path);
  for (const [re, view] of ROUTES) {
    const m = path.match(re);
    if (!m) continue;
    try {
      const el = await view(m.slice(1), ctx);
      if (token !== renderToken) return;  // el usuario navegó mientras cargaba
      root.replaceChildren(el);
    } catch (e) {
      if (token !== renderToken) return;
      root.replaceChildren(h("div", { class: "empty" }, e.message || "Error inesperado",
        h("p", null, h("button", { class: "btn ghost", onclick: route }, "Reintentar"))));
    }
    root.focus({ preventScroll: true });
    window.scrollTo(0, 0);
    return;
  }
  root.replaceChildren(h("div", { class: "empty" }, "Página no encontrada"));
}

window.addEventListener("hashchange", route);
window.addEventListener("auth:expired", () => { state.user = null; state.next = location.hash.slice(1); ctx.go("/login"); });

(async () => {
  await loadConfig();
  const banner = document.getElementById("beta");
  if (state.config.beta) banner.hidden = false;
  if (auth.token) await loadUser();
  await route();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
})();
