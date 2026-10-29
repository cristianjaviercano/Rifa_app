import { h, money, fmtDate, liveCountdown, chip, toast, padNum, skeleton } from "../dom.js";
import { api } from "../api.js";
import { state, selectionFor } from "../state.js";
import { STATUS } from "./home.js";
import { shareDialog, ownRaffleCta } from "../share.js";

const label = (t, total) => {
  const n = t.numbers.map((x) => padNum(x, total));
  return n.length <= 2 ? n.join("·") : `${n[0]}…${n[n.length - 1]}`;
};

export async function raffleView([rid], ctx) {
  const r = await api.get(`/raffles/${rid}`);
  const sel = selectionFor(rid);
  const [statusLabel, statusKind] = STATUS[r.status] || [r.status, "neutral"];
  const selling = r.status === "OPEN" && new Date(r.sales_close_at) > new Date();
  let tickets = [], onlyFree = false, shown = 200;  // se pintan por tandas: una rifa de miles de boletas no satura el DOM

  const pct = r.tickets_total ? Math.round((r.tickets_sold / r.tickets_total) * 100) : 0;
  const barFill = h("i"); barFill.style.width = pct + "%";
  const grid = h("div", { class: "grid" + (r.numbers_per_ticket > 1 ? " wide" : ""), role: "group", "aria-label": "Boletas" });
  const cta = h("div", { class: "sticky-cta", hidden: true });
  const search = h("input", { type: "search", inputmode: "numeric", placeholder: "Buscar número…", "aria-label": "Buscar número" });
  const filter = h("input", { type: "checkbox", id: "free", onchange: (e) => { onlyFree = e.target.checked; paint(); } });

  function cellClass(t) {
    if (sel.has(t.serial)) return "cell sel";
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

  const more = h("button", { class: "btn ghost block", type: "button", id: "show-more", hidden: true, onclick: () => { shown += 200; paint(); } });

  function paint() {
    const list = tickets.filter((t) => !onlyFree || t.status === "DISPONIBLE" || sel.has(t.serial));
    grid.replaceChildren(...list.slice(0, shown).map((t) => {
      const free = t.status === "DISPONIBLE";
      return h("button", {
        class: cellClass(t), type: "button", id: "t-" + t.serial, disabled: !(free && selling),
        "aria-pressed": sel.has(t.serial) ? "true" : "false",
        "aria-label": `Boleta ${t.numbers.join(", ")}: ${free ? "disponible" : t.mine ? "tuya" : t.status.toLowerCase()}`,
        onclick: () => {
          sel.has(t.serial) ? sel.delete(t.serial) : sel.set(t.serial, { serial: t.serial, numbers: t.numbers });
          paint();
        },
      }, label(t, r.total_numbers));
    }));
    more.hidden = list.length <= shown;
    more.textContent = `Mostrar más (${list.length - shown} restantes)`;
    paintCta();
  }

  const BY = { D: "DISPONIBLE", C: "CONGELADO", P: "PAGADO", G: "GANADOR" };
  async function refresh() {
    const b = await api.get(`/raffles/${rid}/board`);  // ~1 byte por boleta; el navegador revalida con ETag
    const mine = new Set(b.mine);
    tickets = [...b.states].map((c, i) => ({ serial: i + 1, status: BY[c], mine: mine.has(i + 1),
      numbers: Array.from({ length: b.npt }, (_, k) => i * b.npt + k) }));
    for (const serial of [...sel.keys()]) {
      if (tickets[serial - 1]?.status !== "DISPONIBLE") { sel.delete(serial); toast("Una boleta que elegiste ya no está disponible", "bad"); }
    }
    paint();
  }

  const randN = h("input", { id: "rand-n", type: "number", min: 1, max: 20, value: 5, "aria-label": "Cantidad al azar", inputmode: "numeric" });
  const randBtn = h("button", { class: "btn ghost small", type: "button", id: "rand-pick", onclick: () => {
    const n = Math.max(1, Math.min(20, Number(randN.value) || 1));
    const free = tickets.filter((t) => t.status === "DISPONIBLE" && !sel.has(t.serial));
    for (let k = 0; k < n && free.length; k++) {
      const [t] = free.splice(Math.floor(Math.random() * free.length), 1);
      sel.set(t.serial, { serial: t.serial, numbers: t.numbers });
    }
    paint();
  } }, "Elegir al azar");

  search.addEventListener("input", () => {
    const q = Number(search.value);
    if (search.value === "" || Number.isNaN(q)) return;
    const t = tickets.find((x) => x.numbers.includes(q));
    if (t && t.serial > shown) { shown = Math.ceil(t.serial / 200) * 200; paint(); }
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
    r.images && r.images.length ? h("div", { class: "gallery", "aria-label": "Imágenes de la rifa" }, r.images.map((id, i) =>
      h("img", { src: `/api/v1/raffle-images/${id}`, alt: i ? `Imagen ${i + 1} de ${r.title}` : `Portada de ${r.title}`, loading: i ? "lazy" : "eager" }))) : null,
    h("div", { class: "row" }, h("h1", null, r.title), chip(statusLabel, statusKind)),
    r.description && h("p", { id: "raffle-description" }, r.description),
    r.contact && h("p", { class: "muted", id: "raffle-contact" }, "Contacto del organizador: ", r.contact),
    h("div", { class: "row wrap" },
      r.is_owner ? h("a", { href: `#/admin/r/${rid}` }, "Administrar esta rifa →")
        : r.room_code ? h("a", { href: `#/s/${r.room_code}`, id: "see-room" }, `Ver más rifas de ${r.owner_name} →`) : h("span"),
      h("button", { class: "btn ghost small", type: "button", id: "share-btn", onclick: () => shareDialog(r, rid) }, "Compartir")),
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
    selling && h("div", { class: "row", id: "random-box" }, h("span", { class: "muted" }, "¿Sin preferencia?"), h("span", { class: "row" }, randN, randBtn)),
    h("div", { class: "legend", "aria-hidden": "true" },
      h("span", null, h("i", { class: "cell" }), "Libre"), h("span", null, h("i", { class: "cell sel" }), "Elegida"),
      h("span", null, h("i", { class: "cell held" }), "En revisión"), h("span", null, h("i", { class: "cell paid" }), "Pagada"),
      h("span", null, h("i", { class: "cell mine" }), "Tuya")),
    ...skeleton(0), grid, more,
    ownRaffleCta(ctx, rid),
    cta);

  await refresh();
  // Actualización casi en vivo, pausada con la pestaña en segundo plano (ahorra invocaciones).
  const poll = setInterval(() => { if (!document.hidden) refresh().catch(() => {}); }, 5000);
  const onVisible = () => { if (!document.hidden) refresh().catch(() => {}); };
  document.addEventListener("visibilitychange", onVisible);
  ctx.onCleanup(() => { clearInterval(poll); document.removeEventListener("visibilitychange", onVisible); });
  return view;
}
