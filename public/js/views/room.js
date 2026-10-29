import { h, chip } from "../dom.js";
import { api } from "../api.js";
import { raffleCard } from "./home.js";
import { ownRaffleCta, prettyCode, shareRoomDialog } from "../share.js";

export async function roomView([code], ctx) {
  const room = await api.get(`/rooms/${code}`);
  return h("div", null,
    h("div", { class: "row" }, h("h1", null, room.room_name), chip(prettyCode(room.room_code), "neutral")),
    h("p", { class: "muted" }, "Organiza " + room.owner_name),
    h("div", { class: "row wrap" },
      room.is_owner ? h("a", { href: "#/admin" }, "Administrar mi sala →") : h("span"),
      h("button", { class: "btn ghost small", type: "button", id: "share-room", onclick: () => shareRoomDialog(room) }, "Compartir sala")),
    room.raffles.length
      ? room.raffles.map((r) => raffleCard(r, `#/r/${r.id}`))
      : h("div", { class: "empty", id: "room-empty" }, "Esta sala todavía no tiene rifas activas."),
    ownRaffleCta(ctx, null));
}
