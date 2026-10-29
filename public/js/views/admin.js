import { h, money, fmtDate, chip, toast, modal, liveCountdown, padNum, skeleton } from "../dom.js";
import { api } from "../api.js";
import { state } from "../state.js";
import { STATUS, raffleCard } from "./home.js";
import { shareDialog, shareRoomDialog, raffleLink, roomLink, copyText, prettyCode } from "../share.js";

const guard = (ctx, path) => {
  if (state.user) return true;
  state.next = path; ctx.go("/login"); return false;
};

export async function adminListView(_, ctx) {
  if (!guard(ctx, "/admin")) return h("div");
  const room = await api.get("/me/room");
  const name = h("input", { id: "room-name", value: room.has_custom_name ? room.room_name : "", placeholder: room.room_name, maxlength: 60, "aria-label": "Nombre de la sala" });
  const roomCard = h("div", { class: "card stack", id: "room-card" },
    h("div", { class: "row" }, h("h2", null, "Mi sala"), h("span", { class: "chip neutral num", id: "room-code" }, prettyCode(room.room_code))),
    h("p", { class: "muted" }, "Tu portafolio de rifas. Solo entra quien tenga el enlace o el código de tu sala; tú decides qué rifas aparecen en ella."),
    h("div", { class: "row" }, name, h("button", { class: "btn ghost small", type: "button", id: "save-room-name", onclick: async () => {
      const v = name.value.trim(); if (!v) return toast("Escribe un nombre para tu sala", "bad");
      try { await api.post("/me/room", { room_name: v }); room.room_name = v; toast("Nombre guardado"); } catch (x) { toast(x.message, "bad"); }
    } }, "Guardar")),
    h("div", { class: "row" }, h("span", { class: "num link-text" }, roomLink(room.room_code)), h("button", { class: "btn ghost small", type: "button", onclick: () => copyText(roomLink(room.room_code)) }, "Copiar")),
    h("button", { class: "btn block", type: "button", id: "share-room-open", onclick: () => shareRoomDialog(room) }, "Compartir toda mi sala"));

  const rows = room.raffles.map((r) => {
    const inRoom = r.visibility === "PORTFOLIO";
    const toggle = h("button", { class: "btn ghost small", type: "button", "data-vis": r.id, onclick: async (e) => {
      e.target.disabled = true;
      try { await api.post(`/raffles/${r.id}/visibility`, { visibility: inRoom ? "LINK" : "PORTFOLIO" }); window.dispatchEvent(new HashChangeEvent("hashchange")); }
      catch (x) { toast(x.message, "bad"); e.target.disabled = false; }
    } }, inRoom ? "Quitar de mi sala" : "Poner en mi sala");
    return h("div", { class: "stack", "data-raffle": r.id }, raffleCard(r, `#/admin/r/${r.id}`),
      h("div", { class: "row wrap vis-row" }, chip(inRoom ? "En mi sala" : "Solo con enlace o código", inRoom ? "ok" : "neutral"), toggle));
  });
  return h("div", null,
    h("div", { class: "row" }, h("h1", null, "Mis rifas"), h("a", { class: "btn small", href: "#/admin/new", id: "new-raffle" }, "Nueva rifa")),
    roomCard,
    rows.length ? rows : h("div", { class: "empty", id: "no-raffles" }, "Todavía no has creado rifas. Crea la primera y compártela."));
}

const toIso = (v) => new Date(v).toISOString();

export async function adminNewView(_, ctx) {
  if (!guard(ctx, "/admin/new")) return h("div");
  const f = {};
  const field = (id, labelTxt, el, hint) => h("div", { class: "field" }, h("label", { for: id }, labelTxt), el, hint && h("div", { class: "hint" }, hint));
  const inp = (id, attrs) => (f[id] = h("input", { id, ...attrs }));
  const soon = (hours) => { const d = new Date(Date.now() + hours * 3600e3); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 16); };

  const prizeRows = h("div", { class: "stack" });
  const addPrize = (kind = "MAIN", desc = "", offset = 0) => {
    const k = h("select", { "aria-label": "Tipo de premio" }, [["MAIN", "Principal"], ["SECO", "Seco"], ["CONSECUTIVE", "Consecutivo"]].map(([v, l]) => h("option", { value: v, selected: v === kind }, l)));
    const d = h("input", { placeholder: "Descripción del premio", "aria-label": "Descripción", value: desc, maxlength: 200 });
    const o = h("input", { type: "number", "aria-label": "Desplazamiento respecto al número ganador", value: offset, step: 1 });
    const row = h("div", { class: "card stack", "data-prize": "1" }, k, d, h("div", { class: "field" }, h("label", null, "Desplazamiento (0 = número ganador, +1 / −1 = seco)"), o),
      h("button", { class: "btn ghost small", type: "button", onclick: () => row.remove() }, "Quitar"));
    row.read = () => ({ kind: k.value, description: d.value.trim(), offset: Number(o.value), rank: [...prizeRows.children].indexOf(row) + 1 });
    prizeRows.append(row);
  };
  addPrize("MAIN", "");

  const method = (f.method = h("select", { id: "method", onchange: () => (lotteryField.hidden = method.value !== "EXTERNAL_LOTTERY") },
    h("option", { value: "INTERNAL_CSPRNG" }, "Interno (generador aleatorio seguro)"), h("option", { value: "EXTERNAL_LOTTERY" }, "Externo (lotería oficial)")));
  const lotteryField = field("lottery", "Nombre de la lotería", inp("lottery", { placeholder: "Ej. Lotería de Bogotá" }));
  lotteryField.hidden = true;
  const err = h("div", { class: "err", role: "alert" });
  const accounts = ["Nequi", "Daviplata", "Bre-B", "PayPal"].map((n) => [n, h("input", { "aria-label": n, placeholder: n + " (número o enlace)", maxlength: 120 })]);

  async function save(publish) {
    err.textContent = "";
    const prizes = [...prizeRows.children].map((r) => r.read()).filter((p) => p.description);
    const body = {
      title: f.title.value.trim(), terms_md: f.terms.value.trim(), total_numbers: Number(f.total.value),
      numbers_per_ticket: Number(f.per.value), ticket_price: Number(f.price.value),
      sales_close_at: f.close.value && toIso(f.close.value), draw_at: f.draw.value && toIso(f.draw.value),
      draw_method: method.value, lottery_name: method.value === "EXTERNAL_LOTTERY" ? f.lottery.value.trim() : null,
      hold_minutes: Number(f.hold.value), prizes, referrer_raffle_id: state.referrer || null, visibility: f.visibility.value,
      payment_accounts: Object.fromEntries(accounts.filter(([, i]) => i.value.trim()).map(([n, i]) => [n, i.value.trim()])),
    };
    if (!body.title || !body.terms_md || !prizes.length) { err.textContent = "Completa título, términos y al menos un premio."; return; }
    if (!body.sales_close_at || !body.draw_at) { err.textContent = "Indica las fechas de cierre y de sorteo."; return; }
    if (body.total_numbers % body.numbers_per_ticket) { err.textContent = "El total de números debe ser divisible por los números por boleta."; return; }
    try {
      const r = await api.post("/raffles", body);
      if (publish) await api.post(`/raffles/${r.id}/publish`);
      state.referrer = null;
      toast(publish ? "Rifa publicada" : "Borrador guardado");
      ctx.go(`/admin/r/${r.id}`);
    } catch (x) { err.textContent = x.message === `Error ${x.status}` || x.code === "VALIDATION" ? "Revisa los datos del formulario." : x.message; }
  }

  return h("form", { class: "stack", novalidate: true, onsubmit: (e) => e.preventDefault() },
    h("h1", null, "Nueva rifa"),
    h("div", { class: "card" },
      field("title", "Título", inp("title", { maxlength: 120, placeholder: "Ej. Rifa Moto 2026" })),
      field("terms", "Términos y condiciones", (f.terms = h("textarea", { id: "terms" }))),
      field("total", "Cantidad total de números", inp("total", { type: "number", inputmode: "numeric", value: 100, min: 1 })),
      field("per", "Números por boleta", inp("per", { type: "number", inputmode: "numeric", value: 1, min: 1 })),
      field("price", "Valor de la boleta (COP)", inp("price", { type: "number", inputmode: "numeric", value: 10000, min: 1 }))),
    h("div", { class: "card" },
      field("close", "Cierre de ventas", inp("close", { type: "datetime-local", value: soon(24 * 6) })),
      field("draw", "Fecha del sorteo", inp("draw", { type: "datetime-local", value: soon(24 * 7) })),
      field("hold", "Minutos de reserva", inp("hold", { type: "number", inputmode: "numeric", value: 120, min: 1 }), "Tiempo para que verifiques el pago antes de liberar las boletas."),
      field("method", "Método de sorteo", method), lotteryField),
    h("div", { class: "card" }, field("visibility", "¿Quién puede ver esta rifa?", (f.visibility = h("select", { id: "visibility" },
      h("option", { value: "PORTFOLIO" }, "Aparece en mi sala (quien entre a mi sala la ve)"),
      h("option", { value: "LINK" }, "Solo con su enlace o código (rifa independiente)"))),
      "Siempre puedes cambiarlo después. Nadie ve tus rifas sin un enlace o código.")),
    h("div", { class: "card" }, h("h2", null, "Cuentas para recibir pagos"), accounts.map(([, i]) => h("div", { class: "field" }, i))),
    h("h2", null, "Premios"), prizeRows,
    h("button", { class: "btn ghost", type: "button", onclick: () => addPrize("SECO", "", 1) }, "Añadir premio"),
    err,
    h("div", { class: "row" },
      h("button", { class: "btn ghost", type: "button", id: "save-draft", onclick: () => save(false) }, "Guardar borrador"),
      h("button", { class: "btn", type: "button", id: "save-publish", onclick: () => save(true) }, "Crear y publicar")));
}

export async function adminRaffleView([rid], ctx) {
  if (!guard(ctx, `/admin/r/${rid}`)) return h("div");
  const body = h("div", { class: "stack" });

  async function paint() {
    const r = await api.get(`/raffles/${rid}`);
    if (!r.is_owner) { body.replaceChildren(h("div", { class: "empty" }, "No administras esta rifa.")); return; }
    const [lbl, kind] = STATUS[r.status] || [r.status, "neutral"];
    const txs = r.status === "DRAFT" ? [] : await api.get(`/raffles/${rid}/transactions`);
    const pending = txs.filter((t) => t.status === "PENDING");
    const parts = [h("div", { class: "row" }, h("h1", null, r.title), chip(lbl, kind)),
      h("div", { class: "card" }, h("dl", { class: "kv" },
        h("dt", null, "Vendidas"), h("dd", { class: "num" }, `${r.tickets_sold}/${r.tickets_total}`),
        h("dt", null, "En revisión"), h("dd", { class: "num" }, String(r.tickets_held)),
        h("dt", null, "Cierre de ventas"), h("dd", null, fmtDate(r.sales_close_at)),
        h("dt", null, "Sorteo"), h("dd", null, fmtDate(r.draw_at))),
        h("p", null, h("a", { href: `#/r/${rid}` }, "Ver como comprador →")))];

    if (r.status !== "DRAFT") parts.push(h("div", { class: "card stack", id: "share-card" },
      h("h2", null, "Comparte tu rifa"),
      h("p", { class: "muted" }, "Publícala en WhatsApp, LinkedIn, Instagram y más. El enlace lleva a la portada con la selección de números."),
      h("div", { class: "row" }, h("span", { class: "num link-text" }, raffleLink(rid)), h("button", { class: "btn ghost small", type: "button", onclick: () => copyText(raffleLink(rid)) }, "Copiar")),
      h("div", { class: "row" }, h("span", null, "Código: ", h("b", { class: "num", id: "raffle-code" }, prettyCode(r.share_code))), chip(r.visibility === "PORTFOLIO" ? "En mi sala" : "Solo con enlace o código", r.visibility === "PORTFOLIO" ? "ok" : "neutral")),
      h("button", { class: "btn ghost block", type: "button", id: "toggle-vis", onclick: async (e) => {
        e.target.disabled = true;
        try { await api.post(`/raffles/${rid}/visibility`, { visibility: r.visibility === "PORTFOLIO" ? "LINK" : "PORTFOLIO" }); toast("Visibilidad actualizada"); paint(); }
        catch (x) { toast(x.message, "bad"); e.target.disabled = false; }
      } }, r.visibility === "PORTFOLIO" ? "Sacar de mi sala (solo con enlace)" : "Poner en mi sala"),
      h("button", { class: "btn block", type: "button", id: "share-open", onclick: () => shareDialog(r, rid) }, "Elegir dónde compartir")));

    if (r.status === "DRAFT") parts.push(h("button", { class: "btn block", id: "publish", onclick: async () => {
      try { await api.post(`/raffles/${rid}/publish`); toast("Rifa publicada"); paint(); } catch (x) { toast(x.message, "bad"); } } }, "Publicar rifa"));

    if (r.status === "OPEN") parts.push(h("button", { class: "btn ghost block", id: "close", onclick: async () => {
      try { await api.post(`/raffles/${rid}/close`); toast("Ventas cerradas"); paint(); } catch (x) { toast(x.message, "bad"); } } }, "Cerrar ventas y generar arqueo"));

    if (pending.length) parts.push(h("h2", null, `Pagos por verificar (${pending.length})`), ...pending.map((t) => txCard(t, r, paint)));
    else if (r.status === "OPEN" || r.status === "CLOSED") parts.push(h("div", { class: "card muted", id: "no-pending" }, "No hay pagos pendientes."));

    if (r.status === "CLOSED" || r.status === "DRAWN") {
      try {
        const a = await api.get(`/raffles/${rid}/accounting`);
        parts.push(h("div", { class: "card", id: "accounting" }, h("h2", null, "Arqueo contable"), h("dl", { class: "kv" },
          h("dt", null, "Boletas pagadas"), h("dd", { class: "num" }, String(a.sold_count)),
          h("dt", null, "Dinero validado"), h("dd", { class: "num" }, money(a.validated_amount, r.currency)),
          h("dt", null, "Pendiente"), h("dd", { class: "num" }, money(a.pending_amount, r.currency)),
          h("dt", null, "Huella"), h("dd", { class: "num" }, a.hash.slice(0, 12) + "…"))));
      } catch { /* aún sin arqueo */ }
    }
    if (r.status === "CLOSED") parts.push(drawPanel(r, rid, pending.length, paint));
    if (r.status === "DRAWN") parts.push(h("p", null, h("a", { class: "btn block", href: `#/r/${rid}` }, "Ver resultado público")));
    body.replaceChildren(...parts);
  }

  body.append(...skeleton(2));
  await paint();
  const poll = setInterval(() => { if (!document.querySelector("dialog")) paint().catch(() => {}); }, 8000);
  ctx.onCleanup(() => clearInterval(poll));
  return body;
}

function txCard(t, r, repaint) {
  const expected = Number(t.ticket_price) * (t.tickets || []).length;
  const mismatch = Number(t.amount_declared) !== expected;
  const wa = "https://wa.me/" + t.buyer_phone.replace(/\D/g, "");
  return h("div", { class: "card stack", "data-tx": t.id },
    h("div", { class: "row" }, h("b", null, t.buyer_name), h("a", { href: wa, target: "_blank", rel: "noopener noreferrer" }, t.buyer_phone)),
    h("div", { class: "num" }, (t.tickets || []).map((x) => x.numbers.map((n) => padNum(n, r.total_numbers)).join("·")).join("  ")),
    h("dl", { class: "kv" },
      h("dt", null, "Plataforma"), h("dd", null, t.platform),
      h("dt", null, "N.º transacción"), h("dd", { class: "num" }, t.external_ref || "—"),
      h("dt", null, "Declarado"), h("dd", { class: "num" }, money(t.amount_declared, r.currency)),
      h("dt", null, "Esperado"), h("dd", { class: "num" }, money(expected, r.currency)),
      h("dt", null, "Vence en"), h("dd", null, liveCountdown(t.expires_at))),
    mismatch && h("div", { class: "chip bad" }, "El monto no coincide"),
    h("div", { class: "row wrap" },
      t.proof_id ? h("button", { class: "btn ghost small", type: "button", onclick: () => showProof(t.proof_id) }, "Ver comprobante") : h("span", { class: "muted" }, "Sin comprobante"),
      h("div", { class: "row" },
        h("button", { class: "btn danger small", type: "button", "data-act": "reject", onclick: () => reject(t, repaint) }, "Rechazar"),
        h("button", { class: "btn small", type: "button", "data-act": "approve", onclick: async (e) => {
          e.target.disabled = true;
          try { await api.post(`/transactions/${t.id}/approve`); toast("Pago aprobado"); } catch (x) { toast(x.message, "bad"); }
          repaint();
        } }, "Aprobar"))));
}

async function showProof(pid) {
  try {
    const blob = await api.blob(`/proofs/${pid}`);
    const url = URL.createObjectURL(blob);
    const content = blob.type === "application/pdf"
      ? h("p", null, h("a", { class: "btn block", href: url, target: "_blank", rel: "noopener" }, "Abrir PDF"))
      : h("img", { src: url, alt: "Comprobante de pago" });
    await modal(content, { actions: [{ label: "Cerrar", value: true, cls: "ghost" }] });
    URL.revokeObjectURL(url);
  } catch (x) { toast(x.message, "bad"); }
}

async function reject(t, repaint) {
  const reason = h("textarea", { id: "reason", "aria-label": "Motivo del rechazo", placeholder: "Ej. El monto no coincide" });
  const ok = await modal([h("h2", null, "Rechazar pago"), h("p", { class: "muted" }, "Las boletas volverán a estar disponibles."), reason],
    { actions: [{ label: "Cancelar", value: false, cls: "ghost" }, { label: "Rechazar", value: true, cls: "danger" }] });
  if (!ok) return;
  if (reason.value.trim().length < 3) return toast("Indica un motivo", "bad");
  try { await api.post(`/transactions/${t.id}/reject`, { reason: reason.value.trim() }); toast("Pago rechazado"); } catch (x) { toast(x.message, "bad"); }
  repaint();
}

function drawPanel(r, rid, pendingCount, repaint) {
  const external = r.draw_method === "EXTERNAL_LOTTERY";
  const num = h("input", { id: "win", type: "number", inputmode: "numeric", min: 0, placeholder: `0 – ${r.total_numbers - 1}`, "aria-label": "Número ganador oficial" });
  const src = h("input", { id: "src", type: "url", placeholder: "https://… (fuente pública)", "aria-label": "Enlace de comprobación" });
  return h("div", { class: "card stack", id: "draw-panel" }, h("h2", null, "Sorteo"),
    pendingCount > 0 && h("div", { class: "chip warn" }, `Resuelve ${pendingCount} pago(s) pendiente(s) antes de sortear`),
    external ? [h("p", { class: "muted" }, `Ingresa el resultado oficial de ${r.lottery_name}.`), h("div", { class: "field" }, num), h("div", { class: "field" }, src)]
             : h("p", { class: "muted" }, "Se elegirá al azar entre las boletas pagadas con un generador criptográficamente seguro."),
    h("button", { class: "btn block", id: "run-draw", disabled: pendingCount > 0, onclick: async () => {
      const go = await modal([h("h2", null, "¿Ejecutar el sorteo?"), h("p", null, "Esta acción no se puede deshacer.")],
        { actions: [{ label: "Cancelar", value: false, cls: "ghost" }, { label: "Sortear", value: true }] });
      if (!go) return;
      try {
        await api.post(`/raffles/${rid}/draw`, external ? { winning_number: Number(num.value), source_url: src.value.trim() } : {});
        toast("Sorteo realizado"); repaint();
      } catch (x) { toast(x.message, "bad"); }
    } }, "Ejecutar sorteo"));
}
