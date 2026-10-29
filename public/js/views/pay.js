import { h, money, toast, liveCountdown, padNum } from "../dom.js";
import { api, ApiError } from "../api.js";
import { state, selectionFor } from "../state.js";
import { prepareImage as prepare } from "../image.js";

const PLATFORMS = [["NEQUI", "Nequi"], ["DAVIPLATA", "Daviplata"], ["BREVE", "Bre-B"], ["PAYPAL", "PayPal"], ["OTRO", "Otro"]];
const MAX = 4 * 1024 * 1024;  // límite de la plataforma: 4,5 MB por petición

export async function payView([rid], ctx) {
  if (!state.user) { state.next = `/pay/${rid}`; ctx.go("/login"); return h("div"); }
  const sel = selectionFor(rid);
  if (!sel.size) { ctx.go(`/r/${rid}`); return h("div"); }
  const r = await api.get(`/raffles/${rid}`);
  const picks = [...sel.entries()];
  const total = Number(r.ticket_price) * picks.length;
  const idem = crypto.randomUUID();  // misma clave en reintentos: no se duplica la reserva
  let file = null, previewUrl = null;

  const platform = h("select", { id: "platform" }, PLATFORMS.map(([v, l]) => h("option", { value: v }, l)));
  const ref = h("input", { id: "ref", autocomplete: "off", maxlength: 64, placeholder: "Ej. M1234567" });
  const preview = h("div");
  const err = h("div", { class: "err", role: "alert" });
  const fileIn = h("input", { id: "proof", type: "file", accept: "image/*,application/pdf", onchange: (e) => {
    const f = e.target.files[0];
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    file = f || null; previewUrl = null; preview.replaceChildren();
    if (!f) return;
    if (f.size > MAX * 4) { err.textContent = "El archivo es demasiado grande."; file = null; return; }
    err.textContent = "";
    if (f.type.startsWith("image/")) { previewUrl = URL.createObjectURL(f); preview.replaceChildren(h("img", { class: "preview", src: previewUrl, alt: "Vista previa del comprobante" })); }
    else preview.replaceChildren(h("p", { class: "muted" }, "📄 " + f.name));
  } });
  ctx.onCleanup(() => previewUrl && URL.revokeObjectURL(previewUrl));

  const submit = h("button", { class: "btn block", type: "submit", id: "submit-pay" }, `Enviar para verificación · ${money(total, r.currency)}`);
  const accounts = Object.entries(r.payment_accounts || {});

  const form = h("form", { class: "card", novalidate: true, onsubmit: async (e) => {
    e.preventDefault(); err.textContent = "";
    if (!ref.value.trim() && !file) { err.textContent = "Indica el número de transacción o adjunta el comprobante."; return; }
    submit.disabled = true; submit.textContent = "Enviando…";
    try {
      let proof_id = null;
      if (file) {
        const blob = await prepare(file);
        if (blob.size > MAX) throw new ApiError(413, "FILE_TOO_LARGE");
        proof_id = (await api.putBlob("/uploads/proof", blob)).proof_id;
      }
      const res = await api.post(`/raffles/${rid}/reservations`, {
        serials: picks.map(([serial]) => serial), platform: platform.value,
        external_ref: ref.value.trim() || null, proof_id, amount_declared: total,
      }, { "Idempotency-Key": idem });
      sel.clear();
      done(res);
    } catch (x) {
      if (x.code === "TICKET_UNAVAILABLE") {
        (x.extra.conflicts || []).forEach((serial) => sel.delete(serial));
        toast(x.message, "bad"); return ctx.go(`/r/${rid}`);
      }
      err.textContent = x.message; submit.disabled = false; submit.textContent = `Enviar para verificación · ${money(total, r.currency)}`;
    }
  } },
    h("div", { class: "field" }, h("label", { for: "platform" }, "¿Con qué plataforma pagaste?"), platform),
    h("div", { class: "field" }, h("label", { for: "ref" }, "Número de transacción"), ref),
    h("div", { class: "field" }, h("label", { for: "proof" }, "Comprobante (foto, captura o PDF)"), fileIn, preview,
      h("div", { class: "hint" }, "Puedes indicar el número, adjuntar el comprobante o ambos.")),
    err, submit);

  const wrap = h("div", { class: "stack" });
  const done = (res) => {
    wrap.replaceChildren(h("h1", null, "Pago reportado"), h("div", { class: "card stack", id: "confirmation" },
      h("p", null, "Tus boletas quedaron ", h("b", null, "reservadas"), " mientras el administrador verifica el pago."),
      h("p", null, "Vence en: ", liveCountdown(res.expires_at)),
      h("p", { class: "muted" }, "Recibirás un mensaje cuando el pago sea confirmado."),
      h("a", { class: "btn block", href: "#/mine" }, "Ver mis compras")));
  };

  wrap.append(
    h("h1", null, "Confirmar pago"),
    h("div", { class: "card" }, h("h2", null, r.title),
      h("dl", { class: "kv" },
        h("dt", null, "Boletas"), h("dd", { class: "num" }, picks.map(([, t]) => t.numbers.map((n) => padNum(n, r.total_numbers)).join("·")).join("  ")),
        h("dt", null, "Total a pagar"), h("dd", { class: "num" }, money(total, r.currency)),
        h("dt", null, "Reserva por"), h("dd", null, `${r.hold_minutes} min tras enviar`))),
    accounts.length ? h("div", { class: "card" }, h("h2", null, "Paga a"), accounts.map(([k, v]) =>
      h("div", { class: "copy" }, h("span", null, h("b", null, k), " ", h("span", { class: "num" }, v)),
        h("button", { class: "btn ghost small", type: "button", onclick: async () => {
          try { await navigator.clipboard.writeText(v); toast("Copiado"); } catch { toast("No se pudo copiar", "bad"); }
        } }, "Copiar")))) : null,
    form);
  return wrap;
}
