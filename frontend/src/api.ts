import { storage } from "@/src/utils/storage";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL;
const TOKEN_KEY = "jobby_session_token";

export async function getToken() {
  return await storage.getItem(TOKEN_KEY);
}
export async function setToken(t: string) {
  await storage.setItem(TOKEN_KEY, t);
}
export async function clearToken() {
  await storage.removeItem(TOKEN_KEY);
}

async function request(path: string, options: RequestInit = {}) {
  const token = await getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${BASE}/api${path}`, { ...options, headers });
  if (res.status === 401) {
    await clearToken();
    throw new Error("unauthorized");
  }
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt || `Request failed: ${res.status}`);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

export const api = {
  createSession: (session_token: string) =>
    request("/auth/session", { method: "POST", body: JSON.stringify({ session_token }) }),
  me: () => request("/auth/me"),
  logout: () => request("/auth/logout", { method: "POST" }),
  updateProfile: (data: any) => request("/profile", { method: "PUT", body: JSON.stringify(data) }),
  providersNearby: (lat: number, lng: number, category?: string) =>
    request(`/providers/nearby?lat=${lat}&lng=${lng}${category ? `&category=${category}` : ""}`),
  createMission: (data: any) => request("/missions", { method: "POST", body: JSON.stringify(data) }),
  getMission: (id: string) => request(`/missions/${id}`),
  myMissions: () => request("/missions"),
  selectProvider: (id: string, provider_id: string) =>
    request(`/missions/${id}/select`, { method: "POST", body: JSON.stringify({ provider_id }) }),
  incomingMissions: () => request("/missions/incoming/list"),
  acceptMission: (id: string, price?: number) =>
    request(`/missions/${id}/accept`, { method: "POST", body: JSON.stringify({ price: price ?? null }) }),
  declineMission: (id: string) => request(`/missions/${id}/decline`, { method: "POST" }),
  bookings: () => request("/bookings"),
  getBooking: (id: string) => request(`/bookings/${id}`),
  completeBooking: (id: string) => request(`/bookings/${id}/complete`, { method: "POST" }),
  reviewBooking: (id: string, rating: number, comment: string) =>
    request(`/bookings/${id}/review`, { method: "POST", body: JSON.stringify({ rating, comment }) }),
  earnings: () => request("/earnings"),

  // categories & discovery
  categories: () => request("/categories"),
  getCategory: (id: string) => request(`/categories/${id}`),

  // wallet
  wallet: () => request("/wallet"),
  addFunds: (amount: number) => request("/wallet/add", { method: "POST", body: JSON.stringify({ amount }) }),

  // payments
  pay: (data: { service_id: string; label: string; amount: number; answers: any }) =>
    request("/payments", { method: "POST", body: JSON.stringify(data) }),

  // requests (Richieste)
  requests: () => request("/requests"),

  // chat
  conversations: () => request("/chat/conversations"),
  messages: (id: string) => request(`/chat/${id}`),
  sendMessage: (id: string, text: string) =>
    request(`/chat/${id}`, { method: "POST", body: JSON.stringify({ text }) }),
};
