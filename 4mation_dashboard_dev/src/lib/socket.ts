import { io, type Socket } from "socket.io-client";

const SOCKET_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
const GUEST_NAME_KEY = "4mation_guest_name";

let socket: Socket | null = null;

export function getGuestName(): string {
  return localStorage.getItem(GUEST_NAME_KEY)?.trim() || "Invité";
}

export function setGuestName(name: string): void {
  const trimmed = name.trim().slice(0, 24);
  localStorage.setItem(GUEST_NAME_KEY, trimmed || "Invité");
}

/** Ouvre ou recrée le client Socket.IO (pseudo invité envoyé au serveur). */
export function connectOnlineSocket(guestName?: string): Socket {
  disconnectSocket();
  const name = (guestName ?? getGuestName()).trim().slice(0, 24) || "Invité";
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
