import { io, type Socket } from "socket.io-client";
import { ensureGuestName, generateRandomGuestName, isGenericGuestName } from "./guestNames";

const SOCKET_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
const GUEST_NAME_KEY = "4mation_guest_name";

let socket: Socket | null = null;

export function getGuestName(): string {
  const stored = localStorage.getItem(GUEST_NAME_KEY)?.trim();
  if (stored && !isGenericGuestName(stored)) {
    return stored.slice(0, 24);
  }
  const generated = generateRandomGuestName();
  localStorage.setItem(GUEST_NAME_KEY, generated);
  return generated;
}

export function setGuestName(name: string): void {
  const trimmed = ensureGuestName(name).slice(0, 24);
  localStorage.setItem(GUEST_NAME_KEY, trimmed);
}

export function rollGuestName(): string {
  const next = generateRandomGuestName();
  localStorage.setItem(GUEST_NAME_KEY, next);
  return next;
}

/** Ouvre ou recrée le client Socket.IO (pseudo invité envoyé au serveur). */
export function connectOnlineSocket(guestName?: string): Socket {
  disconnectSocket();
  const name = ensureGuestName(guestName ?? getGuestName()).slice(0, 24);
  const prod = import.meta.env.PROD;
  socket = io(SOCKET_URL, {
    withCredentials: true,
    autoConnect: false,
    // Prod : polling seul vers le service realtime (évite upgrade WS cassé derrière Gunicorn)
    transports: prod ? ["polling"] : ["polling", "websocket"],
    upgrade: !prod,
    auth: { guest_name: name },
  });
  return socket;
}

export function getSocket(): Socket {
  if (!socket) {
    return connectOnlineSocket();
  }
  return socket;
}

export function disconnectSocket(): void {
  if (socket) {
    socket.removeAllListeners();
    socket.disconnect();
    socket = null;
  }
}
