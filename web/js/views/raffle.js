import { h, money, fmtDate, liveCountdown, chip, toast, padNum, skeleton } from "../dom.js";
import { api } from "../api.js";
import { state, selectionFor } from "../state.js";
import { STATUS } from "./home.js";

const label = (t, total) => {
  const n = t.numbers.map((x) => padNum(x, total));
  return n.length <= 2 ? n.join("·") : `${n[0]}…${n[n.length - 1]}`;
};

export async function raffleView([rid], ctx) {
  const r = await api.get(`/raffles/${rid}`);
  const sel = selectionFor(rid);
  const [statusLabel, statusKind] = STATUS[r.status] || [r.status, "neutral"];
  const selling = r.status === "OPEN" && new Date(r.sales_close_at) > new Date();
  let tickets = [], onlyFree = false;

  const pct = r.tickets_total ? Math.round((r.tickets_sold / r.tickets_total) * 100) : 0;
  const barFill = h("i"); barFill.style.width = pct + "%";
  const grid = h("div", { class: "grid" + (r.numbers_per_ticket > 1 ? " wide" : ""), role: "group", "aria-label": "Boletas" });
  const cta = h("div", { class: "sticky-cta", hidden: true });
  const search = h("input", { type: "search", inputmode: "numeric", placeholder: "Buscar número…", "aria-label": "Buscar número" });
  const filter = h("input", { type: "checkbox", id: "free", onchange: (e) => { onlyFree = e.target.checked; paint(); } });

  function cellClass(t) {
    if (sel.has(t.id)) return "cell sel";
    if (t.status === "GANADOR") return "cell win";
    if (t.mine) return "cell mine";
    if (t.status === "CONGELADO") return "cell held";
    if (t.status === "PAGADO") return "cell paid";
    return "cell";
  }

  function paintCta() {
    const n = sel.size;
    cta.hidden = n === 0 || !selling;
    if (cta.hidden) return;
    const total = Number(r.ticket_price) * n;
    cta.replaceChildren(h("div", { class: "in" },
      h("div", { class: "grow" }, h("b", null, `${n} boleta${n > 1 ? "s" : ""}`), h("div", { class: "muted num" }, money(total, r.currency))),
      h("button", { class: "btn", id: "go-pay", onclick: () => {
        if (!state.user) { state.next = `/pay/${rid}`; return ctx.go("/login"); }
        ctx.go(`/pay/${rid}`);
      } }, "Continuar al pago")));
  }

  function paint() {
    grid.replaceChildren(...tickets.filter((t) => !onlyFree || t.status === "DISPONIBLE" || sel.has(t.id)).map((t) => {
      const free = t.status === "DISPONIBLE";
      return h("button", {
        class: cellClass(t), type: "button", id: "t-" + t.serial, disabled: !(free && selling),
        "aria-pressed": sel.has(t.id) ? "true" : "false",
        "aria-label": `Boleta ${t.numbers.join(", ")}: ${free ? "disponible" : t.mine ? "tuya" : t.status.toLowerCase()}`,
        onclick: () => {
          sel.has(t.id) ? sel.delete(t.id) : sel.set(t.id, { serial: t.serial, numbers: t.numbers });
          paint();
        },
      }, label(t, r.total_numbers));
    }));
    paintCta();
  }

  async function refresh() {
    tickets = await api.get(`/raffles/${rid}/tickets`);
    const byId = new Map(tickets.map((t) => [t.id, t]));
    for (const id of [...sel.keys()]) {
      if (byId.get(id)?.status !== "DISPONIBLE") { sel.delete(id); toast("Una boleta que elegiste ya no está disponible", "bad"); }
    }
    paint();
  }

  search.addEventListener("input", () => {
    const q = Number(search.value);
    if (search.value === "" || Number.isNaN(q)) return;
    const t = tickets.find((x) => x.numbers.includes(q));
    const el = t && document.getElementById("t-" + t.serial);
    if (el) { el.scrollIntoView({ block: "center", behavior: "smooth" }); el.classList.add("flash"); setTimeout(() => el.classList.remove("flash"), 2600); }
  });

  const extras = [];
  if (r.status === "DRAWN" && r.draw) {
    extras.push(h("div", { class: "card", id: "result" },
      h("h2", null, "Resultado del sorteo"),
      h("p", { class: "price num" }, "Número ganador: " + padNum(r.draw.winning_number, r.total_numbers)),
      h("p", { class: "muted" }, r.draw.method === "EXTERNAL_LOTTERY"
        ? ["Según ", r.lottery_name || "lotería oficial", ". ", r.draw.source_url && h("a", { href: r.draw.source_url, target: "_blank", rel: "noopener noreferrer" }, "Verificar fuente")]
        : "Generado con un generador aleatorio criptográficamente seguro."),
      h("ul", null, r.winners.map((w) => h("li", null, `${w.description}: `, h("b", { class: "num" }, w.numbers.map((n) => padNum(n, r.total_numbers)).join("·")))))));
  }

  const view = h("div", null,
    h("div", { class: "row" }, h("h1", null, r.title), chip(statusLabel, statusKind)),
    r.is_owner && h("p", null, h("a", { href: `#/admin/r/${rid}` }, "Administrar esta rifa →")),
    h("div", { class: "card stack" },
      h("div", { class: "row" }, h("span", { class: "price" }, money(r.ticket_price, r.currency)),
        h("span", { class: "muted" }, r.numbers_per_ticket > 1 ? `${r.numbers_per_ticket} números por boleta` : "por número")),
      h("div", { class: "bar", role: "progressbar", "aria-valuenow": pct, "aria-valuemin": 0, "aria-valuemax": 100, "aria-label": "Vendido" }, barFill),
      h("div", { class: "row muted" }, h("span", null, `${r.tickets_sold}/${r.tickets_total} vendidas`),
        selling ? liveCountdown(r.sales_close_at, "Cierra en ") : h("span", null, "Ventas cerradas")),
      h("div", { class: "muted" }, "Sorteo: ", fmtDate(r.draw_at), " · ", r.draw_method === "EXTERNAL_LOTTERY" ? `Lotería: ${r.lottery_name}` : "Generador aleatorio seguro")),
    ...extras,
    h("details", { class: "card" }, h("summary", null, "Premios"), h("ul", null, r.prizes.map((p) => h("li", null, p.description)))),
    h("details", { class: "card" }, h("summary", null, "Términos y condiciones"), h("p", { class: "pre" }, r.terms_md)),
    h("h2", null, selling ? "Elige tus boletas" : "Boletas"),
    h("div", { class: "row" }, search, h("label", { for: "free", class: "row", style: null }, filter, "Solo libres")),
    h("div", { class: "legend", "aria-hidden": "true" },
      h("span", null, h("i", { class: "cell" }), "Libre"), h("span", null, h("i", { class: "cell sel" }), "Elegida"),
      h("span", null, h("i", { class: "cell held" }), "En revisión"), h("span", null, h("i", { class: "cell paid" }), "Pagada"),
      h("span", null, h("i", { class: "cell mine" }), "Tuya")),
    ...skeleton(0), grid, cta);

  await refresh();
  const poll = setInterval(() => refresh().catch(() => {}), 5000);  // actualización casi en vivo
  ctx.onCleanup(() => clearInterval(poll));
  return view;
}
