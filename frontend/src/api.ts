import { storage } from "@/src/utils/storage";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL;
const TOKEN_KEY = "jobby_session_token";

export async function getToken() {
  return await storage.getItem(TOKEN_KEY, null);
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
    if (res.status === 403 && txt.includes("demo_readonly")) {
      try {
        const { Alert } = require("react-native");
        Alert.alert("Demo", "Questa è una demo di sola lettura. Registrati per usare tutte le funzioni.");
      } catch {}
      throw new Error("demo_readonly");
    }
    throw new Error(txt || `Request failed: ${res.status}`);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

async function adminRequest(path: string, adminToken: string, options: RequestInit = {}) {
  const token = await getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Admin-Token": adminToken,
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${BASE}/api${path}`, { ...options, headers });
  if (!res.ok) throw new Error(`admin_request_failed_${res.status}`);
  return res.json();
}

export const api = {
  createSession: (session_token: string) =>
    request("/auth/session", { method: "POST", body: JSON.stringify({ session_token }) }),
  register: (data: { email: string; password: string; name?: string }) =>
    request("/auth/register", { method: "POST", body: JSON.stringify(data) }),
  loginEmail: (data: { email: string; password: string }) =>
    request("/auth/login", { method: "POST", body: JSON.stringify(data) }),
  loginApple: (data: { identity_token: string; name?: string | null; email?: string | null }) =>
    request("/auth/apple", { method: "POST", body: JSON.stringify(data) }),
  loginDemo: () => request("/auth/demo", { method: "POST" }),
  me: () => request("/auth/me"),
  logout: () => request("/auth/logout", { method: "POST" }),
  updateProfile: (data: any) => request("/profile", { method: "PUT", body: JSON.stringify(data) }),
  // onboarding
  completeOnboarding: (data: any) => request("/onboarding/complete", { method: "POST", body: JSON.stringify(data) }),
  onboardingStatus: () => request("/onboarding/status"),
  addBusinessPhoto: (image: string) => request("/onboarding/business/photo", { method: "POST", body: JSON.stringify({ image }) }),
  deleteBusinessPhoto: (index: number) => request(`/onboarding/business/photo/${index}`, { method: "DELETE" }),
  setBusinessDocument: (image: string) => request("/onboarding/business/document", { method: "POST", body: JSON.stringify({ image }) }),
  providersNearby: (lat: number, lng: number, category?: string) =>
    request(`/providers/nearby?lat=${lat}&lng=${lng}${category ? `&category=${category}` : ""}`),
  createMission: (data: any) => request("/missions", { method: "POST", body: JSON.stringify(data) }),
  getMission: (id: string) => request(`/missions/${id}`),
  myMissions: () => request("/missions"),
  selectProvider: (id: string, provider_id: string) =>
    request(`/missions/${id}/select`, { method: "POST", body: JSON.stringify({ provider_id }) }),
  incomingMissions: () => request("/missions/incoming/list"),
  cancelMission: (id: string) => request(`/missions/${id}/cancel`, { method: "POST" }),
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
  withdraw: (data: { method: string; amount: number; target_id?: string }) =>
    request("/wallet/withdraw", { method: "POST", body: JSON.stringify(data) }),
  payouts: () => request("/wallet/payouts"),
  payEscrow: (bookingId: string) => request(`/bookings/${bookingId}/pay-escrow`, { method: "POST" }),
  cancelBooking: (bookingId: string) => request(`/bookings/${bookingId}/cancel`, { method: "POST" }),
  // disputes
  disputeReasonCodes: () => request("/disputes/reason-codes"),
  createDispute: (data: { booking_id: string; reason_code: string; description: string }) =>
    request("/disputes", { method: "POST", body: JSON.stringify(data) }),
  disputes: () => request("/disputes"),
  getDispute: (id: string) => request(`/disputes/${id}`),
  disputeMessage: (id: string, text: string) => request(`/disputes/${id}/message`, { method: "POST", body: JSON.stringify({ text }) }),
  disputeRespond: (id: string, data: { accept: boolean; refund_pct?: number; message?: string }) =>
    request(`/disputes/${id}/respond`, { method: "POST", body: JSON.stringify(data) }),
  disputeEscalate: (id: string) => request(`/disputes/${id}/escalate`, { method: "POST" }),
  // notifications
  notifications: () => request("/notifications"),
  notifUnread: () => request("/notifications/unread-count"),
  markNotifRead: (id: string) => request(`/notifications/${id}/read`, { method: "POST" }),
  markAllNotifRead: () => request("/notifications/read-all", { method: "POST" }),
  // stripe connect (real provider payouts)
  connectStatus: () => request("/connect/status"),
  connectOnboarding: (originUrl: string) =>
    request("/connect/onboarding-link", { method: "POST", body: JSON.stringify({ origin_url: originUrl }) }),
  withdrawStripe: (amount: number) =>
    request("/wallet/withdraw/stripe", { method: "POST", body: JSON.stringify({ amount }) }),
  // pulizie configurator (Spec 1)
  pulizieConfig: () => request("/pulizie/config"),
  pulizieEstimate: (data: any) => request("/pulizie/estimate", { method: "POST", body: JSON.stringify(data) }),
  createRichiesta: (data: any) => request("/pulizie/richieste", { method: "POST", body: JSON.stringify(data) }),
  myRichieste: () => request("/pulizie/richieste"),
  getRichiesta: (id: string) => request(`/pulizie/richieste/${id}`),
  cancelRichiesta: (id: string) => request(`/pulizie/richieste/${id}/cancel`, { method: "POST" }),
  confirmRichiesta: (id: string, provider_id: string) =>
    request(`/pulizie/richieste/${id}/confirm`, { method: "POST", body: JSON.stringify({ provider_id }) }),
  startRichiesta: (id: string) => request(`/pulizie/richieste/${id}/start`, { method: "POST" }),
  completeRichiesta: (id: string) => request(`/pulizie/richieste/${id}/complete`, { method: "POST" }),
  reviewRichiesta: (id: string, rating: number, comment: string) =>
    request(`/pulizie/richieste/${id}/review`, { method: "POST", body: JSON.stringify({ rating, comment }) }),
  pulizieIncoming: () => request("/pulizie/incoming"),
  proposeRichiesta: (id: string, data: { accept: boolean; variation_reason?: string | null; variation_price?: number | null; message?: string }) =>
    request(`/pulizie/richieste/${id}/propose`, { method: "POST", body: JSON.stringify(data) }),
  getListino: () => request("/pulizie/listino"),
  setListino: (binario: string, listino: any) =>
    request("/pulizie/listino", { method: "PUT", body: JSON.stringify({ binario, listino }) }),
  lfBorsellino: () => request("/pulizie/lf/borsellino"),
  lfTopup: (amount: number) => request("/pulizie/lf/topup", { method: "POST", body: JSON.stringify({ amount }) }),
  // admin pulizie
  adminRichieste: (token: string) => adminRequest("/admin/pulizie/richieste", token),
  adminInvite: (rid: string, provider_ids: string[], token: string) =>
    adminRequest(`/admin/pulizie/richieste/${rid}/invite`, token, { method: "POST", body: JSON.stringify({ provider_ids }) }),
  // provider onboarding (Spec 2)
  sendOtp: (email: string) => request("/email/send-otp", { method: "POST", body: JSON.stringify({ email }) }),
  verifyOtp: (email: string, code: string) => request("/email/verify-otp", { method: "POST", body: JSON.stringify({ email, code }) }),
  onbConfig: () => request("/onboarding/config"),
  setProviderProfile: (data: any) => request("/onboarding/provider/profile", { method: "POST", body: JSON.stringify(data) }),
  uploadProviderDoc: (kind: string, image: string) => request("/onboarding/provider/document", { method: "POST", body: JSON.stringify({ kind, image }) }),
  signDelega: (signature_name: string) => request("/onboarding/lf/delega", { method: "POST", body: JSON.stringify({ signature_name }) }),
  setInps: (registered: boolean) => request("/onboarding/lf/inps", { method: "POST", body: JSON.stringify({ registered }) }),
  setAvailability: (availability: any) => request("/onboarding/availability", { method: "PUT", body: JSON.stringify({ availability }) }),
  submitProvider: () => request("/onboarding/provider/submit", { method: "POST" }),
  providerStatus: () => request("/onboarding/provider/status"),
  selfSuspend: (suspend: boolean) => request("/provider/suspend", { method: "POST", body: JSON.stringify({ suspend }) }),
  adminPendingProviders: (token: string) => adminRequest("/admin/onboarding/pending", token),
  adminProviderDecision: (userId: string, action: string, token: string) =>
    adminRequest(`/admin/onboarding/${userId}/decision`, token, { method: "POST", body: JSON.stringify({ action }) }),
  topupCheckout: (packageId: string, originUrl: string) =>
    request("/wallet/topup/checkout", { method: "POST", body: JSON.stringify({ package_id: packageId, origin_url: originUrl }) }),
  topupStatus: (sessionId: string) => request(`/wallet/topup/status/${sessionId}`),
  payBooking: (bookingId: string, originUrl: string) =>
    request(`/bookings/${bookingId}/pay`, { method: "POST", body: JSON.stringify({ origin_url: originUrl }) }),
  createPaypalOrder: (bookingId: string, originUrl: string) =>
    request(`/bookings/${bookingId}/paypal/create`, { method: "POST", body: JSON.stringify({ origin_url: originUrl }) }),
  capturePaypal: (orderId: string) => request(`/paypal/capture/${orderId}`, { method: "POST" }),
  payoutProvider: (bookingId: string) => request(`/bookings/${bookingId}/payout`, { method: "POST" }),
  setPaypalEmail: (email: string) => request("/wallet/paypal-email", { method: "PUT", body: JSON.stringify({ email }) }),
  paymentStatus: (sessionId: string) => request(`/payments/status/${sessionId}`),
  setPaymentMethod: (data: any) => request("/wallet/payment-method", { method: "PUT", body: JSON.stringify(data) }),
  setBankAccount: (data: any) => request("/wallet/bank-account", { method: "PUT", body: JSON.stringify(data) }),
  setCryptoWallet: (data: { token: string; name: string; address: string; network: string }) =>
    request("/wallet/crypto-wallet", { method: "PUT", body: JSON.stringify(data) }),
  deleteCryptoWallet: (walletId: string) =>
    request(`/wallet/crypto-wallet/${walletId}`, { method: "DELETE" }),

  // verification (simulated KYC)
  startVerification: () => request("/verification/start", { method: "POST" }),
  completeVerification: () => request("/verification/complete", { method: "POST" }),

  // trust
  trust: () => request("/trust"),

  // admin (X-Admin-Token)
  adminCategories: (token: string) => adminRequest("/admin/categories", token),
  adminToggleCategory: (catId: string, token: string) =>
    adminRequest(`/admin/categories/${catId}/toggle`, token, { method: "POST" }),
  adminSetCategory: (catId: string, active: boolean, token: string) =>
    adminRequest(`/admin/categories/${catId}/set`, token, {
      method: "POST",
      body: JSON.stringify({ active }),
    }),
  adminSetCommission: (catId: string, commissionPct: number, token: string) =>
    adminRequest(`/admin/categories/${catId}/commission`, token, {
      method: "POST",
      body: JSON.stringify({ commission_pct: commissionPct }),
    }),
  adminRecalcTrust: (token: string) =>
    adminRequest("/admin/trust/recalc", token, { method: "POST" }),

  // bookings extra
  startBooking: (id: string) => request(`/bookings/${id}/start`, { method: "POST" }),

  // payments
  pay: (data: { service_id: string; label: string; amount: number; answers: any }) =>
    request("/payments", { method: "POST", body: JSON.stringify(data) }),
  // payment services (top-up / bills / abroad / local SEPA) — simulated charge
  paymentOptions: (country = "IT") => request(`/payments/options?country=${country}`),
  beneficiaries: (type?: string) => request(`/beneficiaries${type ? `?type=${type}` : ""}`),
  createBeneficiary: (data: any) => request("/beneficiaries", { method: "POST", body: JSON.stringify(data) }),
  deleteBeneficiary: (id: string) => request(`/beneficiaries/${id}`, { method: "DELETE" }),
  servicePayment: (data: any) => request("/payments/service", { method: "POST", body: JSON.stringify(data) }),
  paymentHistory: (kind = "all") => request(`/payments/history?kind=${kind}`),

  // requests (Richieste)
  requests: () => request("/requests"),

  // chat
  conversations: () => request("/chat/conversations"),
  messages: (id: string) => request(`/chat/${id}`),
  sendMessage: (id: string, text: string) =>
    request(`/chat/${id}`, { method: "POST", body: JSON.stringify({ text }) }),

  // proximity businesses (directed requests)
  businesses: (category: string, lat: number, lng: number) =>
    request(`/businesses?category=${category}&lat=${lat}&lng=${lng}`),
  getBusinessDetail: (businessId: string) => request(`/businesses/detail/${businessId}`),
  createBusinessRequest: (data: { business_id: string; category: string; note: string; address: string; lat: number; lng: number; budget?: number | null }) =>
    request("/business-requests", { method: "POST", body: JSON.stringify(data) }),
  businessRequests: () => request("/business-requests"),
  incomingBusinessRequests: () => request("/business-requests/incoming"),
  getBusinessRequest: (id: string) => request(`/business-requests/${id}`),
  respondBusinessRequest: (id: string, data: { accept: boolean; eta?: string; mode?: string; delivery_cost?: number; price?: number; note?: string }) =>
    request(`/business-requests/${id}/respond`, { method: "POST", body: JSON.stringify(data) }),
  cancelBusinessRequest: (id: string) => request(`/business-requests/${id}/cancel`, { method: "POST" }),

  // babysitting (Spec 6)
  bsConfig: () => request("/babysitting/config"),
  bsEstimate: (data: any) => request("/babysitting/estimate", { method: "POST", body: JSON.stringify(data) }),
  bsChildren: () => request("/babysitting/children"),
  bsCreateChild: (data: any) => request("/babysitting/children", { method: "POST", body: JSON.stringify(data) }),
  bsUpdateChild: (cid: string, data: any) => request(`/babysitting/children/${cid}`, { method: "PUT", body: JSON.stringify(data) }),
  bsDeleteChild: (cid: string) => request(`/babysitting/children/${cid}`, { method: "DELETE" }),
  bsCreateRichiesta: (data: any) => request("/babysitting/richieste", { method: "POST", body: JSON.stringify(data) }),
  bsMyRichieste: () => request("/babysitting/richieste"),
  bsGetRichiesta: (id: string) => request(`/babysitting/richieste/${id}`),
  bsCancelRichiesta: (id: string) => request(`/babysitting/richieste/${id}/cancel`, { method: "POST" }),
  bsIncoming: () => request("/babysitting/incoming"),
  bsPropose: (id: string, data: { accept: boolean; message?: string }) =>
    request(`/babysitting/richieste/${id}/propose`, { method: "POST", body: JSON.stringify(data) }),
  bsConfirm: (id: string, provider_id: string) =>
    request(`/babysitting/richieste/${id}/confirm`, { method: "POST", body: JSON.stringify({ provider_id }) }),
  bsSetIncontro: (id: string, mode: string, slot: string) =>
    request(`/babysitting/richieste/${id}/incontro`, { method: "POST", body: JSON.stringify({ mode, slot }) }),
  bsCancelRefund: (id: string) => request(`/babysitting/richieste/${id}/incontro/cancel-refund`, { method: "POST" }),
  bsInizio: (id: string) => request(`/babysitting/richieste/${id}/inizio`, { method: "POST" }),
  bsInizioConfirm: (id: string, code: string) => request(`/babysitting/richieste/${id}/inizio/confirm`, { method: "POST", body: JSON.stringify({ code }) }),
  bsFine: (id: string) => request(`/babysitting/richieste/${id}/fine`, { method: "POST" }),
  bsFineConfirm: (id: string, code: string) => request(`/babysitting/richieste/${id}/fine/confirm`, { method: "POST", body: JSON.stringify({ code }) }),
  bsReview: (id: string, rating: number, comment: string) =>
    request(`/babysitting/richieste/${id}/review`, { method: "POST", body: JSON.stringify({ rating, comment }) }),
  bsEmergency: (id: string) => request(`/babysitting/richieste/${id}/emergency`, { method: "POST" }),
  bsAddChild: (id: string, card_id: string) => request(`/babysitting/richieste/${id}/add-child`, { method: "POST", body: JSON.stringify({ card_id }) }),
  bsAddChildDecision: (id: string, accept: boolean) => request(`/babysitting/richieste/${id}/add-child/decision`, { method: "POST", body: JSON.stringify({ accept }) }),
  bsGetProfile: () => request("/babysitting/profile"),
  bsSetProfile: (data: any) => request("/babysitting/profile", { method: "PUT", body: JSON.stringify(data) }),
  bsUploadCasellario: (image: string) => request("/babysitting/casellario", { method: "POST", body: JSON.stringify({ image }) }),
  bsGetListino: () => request("/babysitting/listino"),
  bsSetListino: (binario: string, listino: any) => request("/babysitting/listino", { method: "PUT", body: JSON.stringify({ binario, listino }) }),
  // admin babysitting
  adminBsRichieste: (token: string) => adminRequest("/admin/babysitting/richieste", token),
  adminBsInvite: (rid: string, provider_ids: string[], token: string) =>
    adminRequest(`/admin/babysitting/richieste/${rid}/invite`, token, { method: "POST", body: JSON.stringify({ provider_ids }) }),
  adminBsCasellario: (userId: string, verified: boolean, token: string) =>
    adminRequest(`/admin/babysitting/${userId}/casellario`, token, { method: "POST", body: JSON.stringify({ verified }) }),

  // driver / NCC + TAXI (Spec 8)
  drvConfig: () => request("/driver/config"),
  drvGeocode: (query: string) => request("/driver/geocode", { method: "POST", body: JSON.stringify({ query }) }),
  drvEstimate: (data: any) => request("/driver/estimate", { method: "POST", body: JSON.stringify(data) }),
  drvCreateRichiesta: (data: any) => request("/driver/richieste", { method: "POST", body: JSON.stringify(data) }),
  drvMyRichieste: () => request("/driver/richieste"),
  drvGetRichiesta: (id: string) => request(`/driver/richieste/${id}`),
  drvCancelRichiesta: (id: string) => request(`/driver/richieste/${id}/cancel`, { method: "POST" }),
  drvIncoming: () => request("/driver/incoming"),
  drvPropose: (id: string, data: any) => request(`/driver/richieste/${id}/propose`, { method: "POST", body: JSON.stringify(data) }),
  drvConfirm: (id: string, provider_id: string) => request(`/driver/richieste/${id}/confirm`, { method: "POST", body: JSON.stringify({ provider_id }) }),
  drvDepart: (id: string) => request(`/driver/richieste/${id}/depart`, { method: "POST" }),
  drvExtra: (id: string, data: any) => request(`/driver/richieste/${id}/extra`, { method: "POST", body: JSON.stringify(data) }),
  drvExtraApprove: (id: string, extra_id: string, approve: boolean) => request(`/driver/richieste/${id}/extra/approve`, { method: "POST", body: JSON.stringify({ extra_id, approve }) }),
  drvNoshow: (id: string) => request(`/driver/richieste/${id}/noshow`, { method: "POST" }),
  drvComplete: (id: string, meter_amount?: number) => request(`/driver/richieste/${id}/complete`, { method: "POST", body: JSON.stringify({ meter_amount }) }),
  drvPay: (id: string) => request(`/driver/richieste/${id}/pay`, { method: "POST" }),
  drvReview: (id: string, rating: number, comment: string) => request(`/driver/richieste/${id}/review`, { method: "POST", body: JSON.stringify({ rating, comment }) }),
  drvGetListino: () => request("/driver/listino"),
  drvSetListino: (data: any) => request("/driver/listino", { method: "PUT", body: JSON.stringify(data) }),
  drvAddVehicle: (data: any) => request("/driver/vehicles", { method: "POST", body: JSON.stringify(data) }),
  drvDelVehicle: (vid: string) => request(`/driver/vehicles/${vid}`, { method: "DELETE" }),
  drvUploadAuth: (data: any) => request("/driver/authorization", { method: "POST", body: JSON.stringify(data) }),
  adminDrvRichieste: (token: string) => adminRequest("/admin/driver/richieste", token),
  adminDrvInvite: (rid: string, provider_ids: string[], token: string) =>
    adminRequest(`/admin/driver/richieste/${rid}/invite`, token, { method: "POST", body: JSON.stringify({ provider_ids }) }),
  adminDrvAuth: (userId: string, verified: boolean, token: string) =>
    adminRequest(`/admin/driver/${userId}/authorization`, token, { method: "POST", body: JSON.stringify({ verified }) }),
};
