import { h, money, liveCountdown, chip, skeleton } from "../dom.js";
import { api } from "../api.js";
import { state } from "../state.js";

export const STATUS = { OPEN: ["Abierta", "ok"], CLOSED: ["Ventas cerradas", "warn"], DRAWN: ["Sorteada", "info"], DRAFT: ["Borrador", "neutral"], CANCELLED: ["Cancelada", "bad"] };

export function raffleCard(r, href) {
  const [label, kind] = STATUS[r.status] || [r.status, "neutral"];
  const pct = r.tickets_total ? Math.round((r.tickets_sold / r.tickets_total) * 100) : 0;
  const bar = h("i"); bar.style.width = pct + "%";
  return h("a", { class: "card", href }, 
    h("div", { class: "row" }, h("h2", null, r.title), chip(label, kind)),
    h("div", { class: "row" }, h("span", { class: "price" }, money(r.ticket_price, r.currency)),
      h("span", { class: "muted" }, r.numbers_per_ticket > 1 ? `${r.numbers_per_ticket} números por boleta` : "por número")),
    h("div", { class: "bar", role: "progressbar", "aria-valuenow": pct, "aria-valuemin": 0, "aria-valuemax": 100, "aria-label": "Vendido" }, bar),
    h("div", { class: "row muted" }, h("span", null, `${pct}% vendido`),
      r.status === "OPEN" ? liveCountdown(r.sales_close_at, "Cierra en ") : h("span", null, "")));
}

const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

/** Acepta un enlace pegado (…/r/ID, …/s/CÓDIGO, …/#/r/ID) o un código (R-XXXXXXX / S-XXXXXXX) y devuelve la ruta. */
export async function routeForInput(raw) {
  const t = raw.trim();
  const link = t.match(/\/(r|s)\/([A-Za-z0-9-]{6,})/);
  if (link) {
    if (link[1].toLowerCase() === "r" && UUID.test(link[2])) return `/r/${link[2].match(UUID)[0]}`;
    if (link[1].toLowerCase() === "s") return `/s/${link[2].replace(/-/g, "").toUpperCase()}`;
  }
  const r = await api.get(`/resolve/${encodeURIComponent(t)}`);
  return r.type === "room" ? `/s/${r.code}` : `/r/${r.id}`;
}

export async function homeView(_, ctx) {
  let mine = [], rooms = [];
  if (state.user) [mine, rooms] = await Promise.all([api.get("/me/raffles"), api.get("/me/rooms")]);

  const input = h("input", { id: "code-input", autocomplete: "off", autocapitalize: "characters", placeholder: "Enlace o código (R-… / S-…)", "aria-label": "Enlace o código" });
  const err = h("div", { class: "err", role: "alert" });
  const go = h("button", { class: "btn block", type: "submit", id: "join-btn" }, "Entrar");
  const join = h("form", { class: "card stack", novalidate: true, onsubmit: async (e) => {
    e.preventDefault(); err.textContent = "";
    if (!input.value.trim()) { err.textContent = "Escribe el código o pega el enlace que te compartieron."; return; }
    go.disabled = true;
    try { ctx.go(await routeForInput(input.value)); } catch (x) { err.textContent = x.message; go.disabled = false; }
  } },
    h("h2", null, "Entrar a una rifa o sala"),
    h("p", { class: "muted" }, "Las rifas son privadas: se ven solo con el enlace o el código que te comparte su organizador."),
    input, err, go);

  const create = h("div", { class: "card stack" },
    h("h2", null, "Crear mi propia rifa"),
    h("p", { class: "muted" }, "Define los números, el precio y el sorteo. Cada organizador tiene su sala: tú decides si compartes una rifa o todo tu portafolio."),
    h("button", { class: "btn ghost block", type: "button", id: "create-raffle", onclick: () => {
      state.referrer = null;
      if (!state.user) { state.next = "/admin/new"; return ctx.go("/login"); }
      ctx.go("/admin/new");
    } }, "Crear mi rifa"));

  const out = [h("h1", null, "Bienvenido"), join, create];
  if (rooms.length) out.push(h("h2", null, "Salas que has visitado"), ...rooms.map((r) =>
    h("a", { class: "card", href: `#/s/${r.room_code}` }, h("div", { class: "row" }, h("h2", null, r.room_name),
      h("span", { class: "chip ok" }, `${r.open_raffles} activa${r.open_raffles === 1 ? "" : "s"}`)), h("div", { class: "muted" }, "de " + r.owner_name))));
  if (mine.length) out.push(h("a", { class: "card", href: "#/admin", id: "my-room-link" }, h("div", { class: "row" }, h("h2", null, "Mi sala"),
    h("span", { class: "chip info" }, `${mine.length} rifa${mine.length === 1 ? "" : "s"}`)), h("div", { class: "muted" }, "Administra tus rifas y comparte tu sala")));
  return h("div", { class: "stack" }, out);
}
