import { h, money, liveCountdown, chip, skeleton } from "../dom.js";
import { api } from "../api.js";

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

export async function homeView() {
  const box = h("div", null, h("h1", null, "Rifas disponibles"), ...skeleton());
  const rows = await api.get("/raffles");
  return h("div", null, h("h1", null, "Rifas disponibles"),
    rows.length ? rows.map((r) => raffleCard(r, `#/r/${r.id}`))
                : h("div", { class: "empty" }, "Aún no hay rifas publicadas.", h("p", null, h("a", { class: "btn", href: "#/admin/new" }, "Crear una rifa"))));
}
