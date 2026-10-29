import { h, modal, toast, money } from "./dom.js";

/** Enlace público de la rifa: /r/{id} devuelve las etiquetas Open Graph y redirige a la aplicación. */
export const raffleLink = (rid) => `${location.origin}/r/${rid}`;

export async function copyText(text) {
  try { await navigator.clipboard.writeText(text); toast("Enlace copiado"); return true; }
  catch { toast("No se pudo copiar. Selecciónalo y cópialo a mano.", "bad"); return false; }
}

/** Diálogo con los destinos de compartir. Instagram no admite enlaces de compartir desde la web:
 *  se usa el menú nativo del teléfono o se copia el enlace para biografía/historias. */
export function shareDialog(raffle, rid) {
  const url = raffleLink(rid);
  const text = `Participa en "${raffle.title}": boleta a ${money(raffle.ticket_price, raffle.currency)}. Elige tu número aquí:`;
  const enc = encodeURIComponent;
  const targets = [
    ["WhatsApp", `https://wa.me/?text=${enc(text + " " + url)}`],
    ["Facebook", `https://www.facebook.com/sharer/sharer.php?u=${enc(url)}`],
    ["LinkedIn", `https://www.linkedin.com/sharing/share-offsite/?url=${enc(url)}`],
    ["X", `https://twitter.com/intent/tweet?text=${enc(text)}&url=${enc(url)}`],
    ["Telegram", `https://t.me/share/url?url=${enc(url)}&text=${enc(text)}`],
    ["Correo", `mailto:?subject=${enc(raffle.title)}&body=${enc(text + "\n" + url)}`],
  ];
  const field = h("input", { id: "share-url", readonly: true, value: url, "aria-label": "Enlace de la rifa" });
  field.addEventListener("focus", () => field.select());
  return modal([
    h("h2", null, "Comparte tu rifa"),
    h("p", { class: "muted" }, "Quien abra el enlace verá la portada de la rifa y podrá elegir su número."),
    h("div", { class: "row" }, field, h("button", { class: "btn small", type: "button", id: "copy-link", onclick: () => copyText(url) }, "Copiar")),
    h("div", { class: "share-grid" }, targets.map(([name, href]) => h("a", { class: "btn ghost small", href, target: "_blank", rel: "noopener noreferrer" }, name))),
    navigator.share && h("button", { class: "btn block", type: "button", id: "native-share", onclick: () => navigator.share({ title: raffle.title, text, url }).catch(() => {}) }, "Compartir desde el teléfono"),
    h("p", { class: "hint" }, "Instagram: usa «Compartir desde el teléfono» o copia el enlace y pégalo en tu biografía o historia."),
  ], { actions: [{ label: "Cerrar", value: true, cls: "ghost" }] });
}
