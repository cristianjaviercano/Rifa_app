import { h, modal, toast, money } from "./dom.js";
import { state } from "./state.js";

const prettyCode = (c) => (c ? `${c[0]}-${c.slice(1)}` : "");

/** Enlaces públicos: /r/{id} y /s/{código} devuelven las etiquetas Open Graph y redirigen a la aplicación. */
export const raffleLink = (rid) => `${location.origin}/r/${rid}`;
export const roomLink = (code) => `${location.origin}/s/${code}`;

export async function copyText(text, msg = "Enlace copiado") {
  try { await navigator.clipboard.writeText(text); toast(msg); return true; }
  catch { toast("No se pudo copiar. Selecciónalo y cópialo a mano.", "bad"); return false; }
}

function targetsFor(title, text, url) {
  const enc = encodeURIComponent;
  return [
    ["WhatsApp", `https://wa.me/?text=${enc(text + " " + url)}`],
    ["Facebook", `https://www.facebook.com/sharer/sharer.php?u=${enc(url)}`],
    ["LinkedIn", `https://www.linkedin.com/sharing/share-offsite/?url=${enc(url)}`],
    ["X", `https://twitter.com/intent/tweet?text=${enc(text)}&url=${enc(url)}`],
    ["Telegram", `https://t.me/share/url?url=${enc(url)}&text=${enc(text)}`],
    ["Correo", `mailto:?subject=${enc(title)}&body=${enc(text + "\n" + url)}`],
  ];
}

function dialogBody({ heading, blurb, title, text, url, code, extra }) {
  const field = h("input", { id: "share-url", readonly: true, value: url, "aria-label": "Enlace" });
  field.addEventListener("focus", () => field.select());
  return [
    h("h2", null, heading),
    h("p", { class: "muted" }, blurb),
    h("div", { class: "row" }, field, h("button", { class: "btn small", type: "button", id: "copy-link", onclick: () => copyText(url) }, "Copiar")),
    code && h("div", { class: "row code-row" }, h("span", null, "O comparte el código: ", h("b", { class: "code num", id: "share-code" }, prettyCode(code))),
      h("button", { class: "btn ghost small", type: "button", onclick: () => copyText(code, "Código copiado") }, "Copiar código")),
    h("div", { class: "share-grid" }, targetsFor(title, text, url).map(([name, href]) => h("a", { class: "btn ghost small", href, target: "_blank", rel: "noopener noreferrer" }, name))),
    navigator.share && h("button", { class: "btn block", type: "button", id: "native-share", onclick: () => navigator.share({ title, text, url }).catch(() => {}) }, "Compartir desde el teléfono"),
    h("p", { class: "hint" }, "Instagram: usa «Compartir desde el teléfono» o copia el enlace y pégalo en tu biografía o historia."),
    extra,
  ];
}

/** Compartir UNA rifa (independiente). Si la rifa está en la sala, ofrece también compartir toda la sala. */
export async function shareDialog(raffle, rid) {
  const text = `Participa en "${raffle.title}": boleta a ${money(raffle.ticket_price, raffle.currency)}. Elige tu número aquí:`;
  const inRoom = raffle.visibility === "PORTFOLIO" && raffle.room_code;
  const again = await modal(dialogBody({
    heading: "Comparte esta rifa", blurb: "Quien abra el enlace verá solo esta rifa" + (inRoom ? " y el acceso a tu sala." : ", sin ver el resto de tu portafolio."),
    title: raffle.title, text, url: raffleLink(rid), code: raffle.share_code,
    extra: inRoom && h("button", { class: "btn ghost block", type: "button", id: "share-room-switch", onclick: (e) => e.target.closest("dialog").dispatchEvent(new CustomEvent("switch")) }, "Compartir toda mi sala"),
  }), { actions: [{ label: "Cerrar", value: true, cls: "ghost" }], switchTo: inRoom });
  if (again === "switch") return shareRoomDialog({ room_code: raffle.room_code, room_name: raffle.room_name });
}

/** Compartir TODA la sala (portafolio). */
export function shareRoomDialog(room) {
  return modal(dialogBody({
    heading: "Comparte tu sala", blurb: "Quien entre verá todas las rifas que tengas en tu sala. Las que marcaste como «solo enlace» no aparecen.",
    title: room.room_name, text: `Entra a "${room.room_name}" y elige tu número en mis rifas:`, url: roomLink(room.room_code), code: room.room_code,
  }), { actions: [{ label: "Cerrar", value: true, cls: "ghost" }] });
}

/** Pie de la portada: invita a quien llegó por un enlace a crear su propia rifa. */
export function ownRaffleCta(ctx, fromRaffleId) {
  return h("section", { class: "own-raffle", id: "own-raffle", "aria-label": "Crea tu propia rifa" },
    h("h2", null, "¿Quieres hacer tu propia rifa?"),
    h("p", { class: "muted" }, "Crea y comparte la tuya en minutos: tú defines los números, el precio y el sorteo, y decides si la compartes sola o dentro de tu sala."),
    h("button", { class: "btn ghost block", type: "button", id: "own-raffle-cta", onclick: () => {
      state.referrer = fromRaffleId || null;  // la nueva rifa queda ligada a esta, para medir el alcance de los enlaces
      if (!state.user) { state.next = "/admin/new"; return ctx.go("/login"); }
      ctx.go("/admin/new");
    } }, "Crea tu propia rifa"));
}

export { prettyCode };
