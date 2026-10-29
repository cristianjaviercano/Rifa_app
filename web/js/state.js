import { api, auth } from "./api.js";

export const state = { user: null, next: null, selection: new Map() };

export async function loadUser() {
  if (!auth.token) { state.user = null; return null; }
  try { state.user = await api.get("/me"); } catch { state.user = null; }
  return state.user;
}
export function logout() { auth.clear(); state.user = null; state.selection.clear(); }

/** Selección de boletas por rifa: Map<ticketId, {serial, numbers}> */
export function selectionFor(rid) {
  if (!state.selection.has(rid)) state.selection.set(rid, new Map());
  return state.selection.get(rid);
}
