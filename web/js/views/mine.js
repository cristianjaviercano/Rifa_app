import { h, money, fmtDate, chip, liveCountdown, padNum, skeleton } from "../dom.js";
import { api } from "../api.js";
import { state } from "../state.js";

const ST = { PENDING: ["En verificación", "warn"], APPROVED: ["Pagado", "ok"], REJECTED: ["Rechazado", "bad"], EXPIRED: ["Vencido", "neutral"] };

export function timeline(status) {
  const step = (txt, cls) => h("li", { class: cls }, txt);
  return h("ol", { class: "timeline", "aria-label": "Progreso" },
    step("Enviado", "done"),
    step(status === "PENDING" ? "En verificación" : "Verificado", status === "PENDING" ? "done" : "done"),
    status === "APPROVED" ? step("Pagado", "done") : status === "REJECTED" || status === "EXPIRED" ? step(ST[status][0], "stop") : step("Pagado", ""));
}

export async function mineView(_, ctx) {
  if (!state.user) { state.next = "/mine"; ctx.go("/login"); return h("div"); }
  const box = h("div");
  const paint = async () => {
    const rows = await api.get("/me/transactions");
    box.replaceChildren(...(rows.length ? rows.map((t) => {
      const [label, kind] = ST[t.status];
      return h("a", { class: "card stack", href: `#/r/${t.raffle_id}`, "data-status": t.status },
        h("div", { class: "row" }, h("h2", null, t.raffle_title), chip(label, kind)),
        h("div", { class: "num" }, (t.tickets || []).map((x) => x.numbers.map((n) => padNum(n, t.total_numbers)).join("·")).join("  ")),
        h("div", { class: "row muted" }, h("span", null, `${t.platform}${t.external_ref ? " · " + t.external_ref : ""}`), h("b", { class: "num" }, money(t.amount_declared))),
        timeline(t.status),
        t.status === "PENDING" && h("div", { class: "muted" }, "Se libera en ", liveCountdown(t.expires_at)),
        t.status === "REJECTED" && t.reject_reason && h("div", { class: "err" }, "Motivo: " + t.reject_reason),
        h("div", { class: "muted" }, fmtDate(t.created_at)));
    }) : [h("div", { class: "empty" }, "Aún no tienes compras.", h("p", null, h("a", { class: "btn", href: "#/" }, "Ver rifas")))]));
  };
  await paint();
  const poll = setInterval(() => paint().catch(() => {}), 10000);
  ctx.onCleanup(() => clearInterval(poll));
  return h("div", null, h("h1", null, "Mis compras"), box);
}
