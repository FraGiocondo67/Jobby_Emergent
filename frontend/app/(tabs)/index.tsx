import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput, RefreshControl, Switch, Modal,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { Image } from "expo-image";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Button } from "@/src/components/UI";
import RealMap from "@/src/components/RealMap";
import NotifBell from "@/src/components/NotifBell";
import { EarnerConfirm } from "@/src/components/DeliveryConfirm";

export default function HomeTab() {
  const { user } = useAuth();
  if (user?.role === "provider") return <ProviderHome />;
  if (user?.role === "business") return <BusinessHome />;
  return <CustomerHome />;
}

function CustomerHome() {
  const { user } = useAuth();
  const { lang, t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [tiles, setTiles] = useState<any[]>([]);
  const [online, setOnline] = useState(0);
  const [balance, setBalance] = useState(user?.wallet_balance || 0);
  const query = "";
  const [refreshing, setRefreshing] = useState(false);
  const [home, setHome] = useState<any>({ state: "new", relationships: [] });

  const load = useCallback(async () => {
    try {
      const [c, w, h] = await Promise.all([api.categories(), api.wallet(), api.homeState()]);
      const std = (c.standard || []).map((s: any) => ({ ...s, kind: "service" }));
      const built = [
        ...std,
        { cat_id: "prossimita", emoji: "🏪", label: { it: "Prossimità", en: "Proximity" }, kind: "proximity", accent: "purple", badge: (c.proximity || []).length },
        { cat_id: "pagamenti", emoji: "💳", label: { it: "Pagamenti", en: "Payments" }, kind: "payment", accent: "green", badge: (c.payment || []).length },
      ];
      setTiles(built);
      setOnline(c.providers_online);
      setBalance(w.balance);
      setHome(h);
    } catch {}
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const filtered = useMemo(
    () => tiles.filter((c) => c.label[lang].toLowerCase().includes(query.toLowerCase())),
    [tiles, query, lang]
  );

  const openCategory = (c: any) => {
    Haptics.selectionAsync().catch(() => {});
    if (c.cat_id === "pulizie") router.push("/pulizie/configura");
    else if (c.cat_id === "babysitting") router.push("/babysitting/configura");
    else if (c.cat_id === "driver") router.push("/driver/configura");
    else if (c.cat_id === "artigiani") router.push("/artigiani/configura");
    else if (c.kind === "proximity") router.push(`/list/prossimita`);
    else if (c.kind === "payment") router.push("/pay");
    else router.push(`/request/${c.cat_id}?type=service`);
  };

  const accentStyle = (c: any) => {
    if (c.accent === "purple") return { borderColor: colors.purpleBorder, backgroundColor: colors.purpleBg };
    if (c.accent === "green") return { borderColor: colors.greenBorder, backgroundColor: colors.greenBg };
    return {};
  };

  return (
    <View style={styles.container}>
      <ScrollView
        contentContainerStyle={{ paddingBottom: insets.bottom + 120 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
        showsVerticalScrollIndicator={false}
      >
        <View style={[styles.top, { paddingTop: insets.top + spacing.md }]}>
          <View style={{ flex: 1 }}>
            <Text style={styles.hi}>{t("hi")}, {(user?.name || "").split(" ")[0] || "👋"} 👋</Text>
            <Text style={styles.subhi}>Treviso · {online} {t("providersOnline")}</Text>
          </View>
          <Pressable testID="wallet-pill" style={styles.walletPill} onPress={() => router.push("/wallet")}>
            <Text style={styles.walletText}>{balance.toFixed(2)}</Text>
          </Pressable>
          <NotifBell />
          <Image source={require("@/assets/images/jobby-logo.png")} style={styles.logo} contentFit="cover" />
        </View>

        {user?.is_demo ? (
          <View style={styles.demoBanner} testID="demo-banner">
            <Ionicons name="eye-outline" size={16} color={colors.warning} />
            <Text style={styles.demoBannerText}>{t("demoBanner")}</Text>
          </View>
        ) : null}

        <View style={styles.body}>
          <View style={styles.heroCard}>
            <Text style={styles.heroPromise}>{t("homePromise")}</Text>
          </View>
          <Pressable testID="pulizie-entry" style={[styles.entryCard, shadow.card]} onPress={() => router.push("/pulizie/configura")}>
            <Text style={{ fontSize: 34 }}>🧽</Text>
            <View style={{ flex: 1 }}>
              <Text style={styles.entryTitle}>{t("homePulizieEntry")}</Text>
              <Text style={styles.entrySub}>{t("homePulizieSub")}</Text>
            </View>
            <Ionicons name="arrow-forward-circle" size={30} color={colors.brand} />
          </Pressable>
          <Text style={styles.sectionTitle}>{t("otherServices")}</Text>

          <Pressable testID="explore-map" style={[styles.mapCard, shadow.card]} onPress={() => router.push("/map")}>
            <View style={styles.mapIcon}><Ionicons name="map" size={26} color={colors.blue} /></View>
            <View style={{ flex: 1 }}>
              <Text style={styles.mapTitle}>{t("exploreMapTitle")}</Text>
              <Text style={styles.mapSub}>{t("exploreMapSub")}</Text>
            </View>
            <Ionicons name="arrow-forward-circle" size={30} color={colors.blue} />
          </Pressable>

          <View style={styles.grid}>
            {filtered.filter((c) => !(home.state !== "recurring" && c.cat_id === "pulizie")).map((c) => (
              <Pressable
                key={c.cat_id}
                testID={`category-${c.cat_id}`}
                style={[styles.tile, accentStyle(c), shadow.card]}
                onPress={() => openCategory(c)}
              >
                {c.badge ? (
                  <View style={[styles.badge, { backgroundColor: c.accent === "purple" ? colors.purple : colors.green }]}>
                    <Text style={styles.badgeText}>{c.badge}</Text>
                  </View>
                ) : null}
                <Text style={styles.tileEmoji}>{c.emoji}</Text>
                <Text style={[styles.tileLabel, c.accent === "purple" && { color: colors.purple }, c.accent === "green" && { color: colors.green }]}>
                  {c.label[lang]}
                </Text>
              </Pressable>
            ))}
          </View>

          {home.state !== "recurring" ? (
            <View style={styles.trustCard}>
              {[["shield-checkmark", t("trustVerified")], ["umbrella", t("trustInsured")], ["star", t("trustReviews")], ["ribbon", t("trustGuarantee")]].map(([ic, tx]) => (
                <View key={tx} style={styles.trustRow}><Ionicons name={ic as any} size={18} color={colors.brand} /><Text style={styles.trustTxt}>{tx}</Text></View>
              ))}
            </View>
          ) : null}
        </View>
      </ScrollView>

      <View style={[styles.floatWrap, { bottom: insets.bottom + 96, pointerEvents: "box-none" }]}>
        <Button
          testID="request-service-button"
          label={`+ ${t("requestService")}`}
          onPress={() => router.push("/list/all")}
          style={{ ...styles.floatBtn, ...shadow.float }}
        />
      </View>
    </View>
  );
}

function ProviderHome() {
  const { user, refresh } = useAuth();
  const { t, lang } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [incoming, setIncoming] = useState<any[]>([]);
  const [opps, setOpps] = useState<any[]>([]);
  const [cats, setCats] = useState<Record<string, any>>({});
  const [online, setOnline] = useState(!!user?.online);

  const SOURCES: Record<string, { fn: () => Promise<any>; route: (id: string) => string }> = {
    pulizie: { fn: api.pulizieIncoming, route: (id) => `/pulizie/${id}` },
    babysitting: { fn: api.bsIncoming, route: (id) => `/babysitting/${id}` },
    driver: { fn: api.drvIncoming, route: (id) => `/driver/${id}` },
    artigiani: { fn: api.artIncoming, route: (id) => `/artigiani/${id}` },
  };

  const load = useCallback(async () => {
    try { setIncoming(await api.incomingMissions()); } catch {}
    const services: string[] = user?.services || [];
    const keys = services.filter((s) => SOURCES[s]);
    try {
      const lists = await Promise.all(keys.map((s) =>
        SOURCES[s].fn().then((l: any[]) => (l || []).map((r) => ({ ...r, __cat: s }))).catch(() => [])));
      const flat = lists.flat().sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
      setOpps(flat);
    } catch {}
  }, [user?.services]);
  useFocusEffect(useCallback(() => { load(); const iv = setInterval(load, 5000); return () => clearInterval(iv); }, [load]));

  useEffect(() => {
    (async () => { try { const c = await api.categories(); const m: Record<string, any> = {}; [...(c.standard || []), ...(c.proximity || [])].forEach((x: any) => { m[x.cat_id] = x.label; }); setCats(m); } catch {} })();
  }, []);

  const oppId = (r: any) => r.richiesta_id || r.rid || r.id;
  const oppSubtitle = (r: any) => {
    if (r.__cat === "driver") { const cfg = r.config || {}; return `${cfg?.route?.from?.label || r.partenza?.label || ""} → ${cfg?.route?.to?.label || r.destinazione?.label || ""}`.trim() || (r.pickup_at || "").replace("T", " "); }
    return r.indirizzo || r.address || "";
  };
  const oppWhen = (r: any) => (r.data_ora || r.pickup_at || "").toString().replace("T", " ").slice(0, 16);

  const toggleOnline = async (v: boolean) => {
    setOnline(v);
    Haptics.selectionAsync().catch(() => {});
    // BLOCCO 9 (fix bug "seleziono online e la app torna alla home CLIENTE"):
    // api.updateProfile() (PUT /profile) risponde con {"message": "..."},
    // NON con un utente — setUser() con quella risposta cancellava
    // user.role dallo stato, HomeTab tornava a CustomerHome di default.
    // refresh() richiama GET /auth/me e ottiene lo shape corretto.
    await api.updateProfile({ online: v });
    await refresh();
  };
  const act = async (id: string, accept: boolean) => {
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    if (accept) await api.acceptMission(id); else await api.declineMission(id);
    load();
  };

  const pins = incoming.map((m) => ({ lat: m.lat, lng: m.lng, emoji: "📍", label: `${m.category} · ${m.address}` }));

  return (
    <View style={styles.container}>
      <View style={[styles.pHeader, { paddingTop: insets.top + spacing.md }]}>
        <View>
          <Text style={styles.brandSmall}>JOBBY</Text>
          <Text style={styles.hi}>{t("missions")}</Text>
        </View>
        <View style={styles.onlineToggle}>
          <NotifBell />
          <Text style={[styles.onlineText, { color: online ? colors.success : colors.muted }]}>{online ? t("online") : t("offline")}</Text>
          <Switch testID="online-toggle" value={online} onValueChange={toggleOnline} trackColor={{ true: colors.brand, false: colors.borderStrong }} thumbColor="#fff" />
        </View>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 100 }} showsVerticalScrollIndicator={false}>
        <RealMap center={{ lat: user?.lat || 45.6669, lng: user?.lng || 12.2433 }} markers={pins} radiusKm={user?.radius_km || 10} height={200} />

        {/* Opportunità richieste per categoria (spec4) */}
        {opps.length > 0 ? (
          <>
            <Text style={styles.sectionTitle}>🔔 {t("newOpportunities")}</Text>
            {[...opps].sort((a, b) => String(b.updated_at || b.created_at || "").localeCompare(String(a.updated_at || a.created_at || ""))).slice(0, 6).map((r) => (
              <Pressable key={`${r.__cat}-${oppId(r)}`} testID={`opp-${oppId(r)}`} style={[styles.missionCard, shadow.card]} onPress={() => router.push(SOURCES[r.__cat].route(oppId(r)) as any)}>
                <View style={styles.missionRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.missionTitle}>{cats[r.__cat]?.[lang] || r.__cat}</Text>
                    <Text style={styles.missionSub} numberOfLines={1}>{oppSubtitle(r)}</Text>
                    {oppWhen(r) ? <Text style={styles.missionSub}>🗓️ {oppWhen(r)}</Text> : null}
                    {r.stato === "confermata" ? <Text style={styles.acceptedTag}>✅ {t("oppConfirmed")}</Text>
                      : r.stato === "in_corso" ? <Text style={styles.acceptedTag}>🚗 {t("oppInProgress")}</Text>
                      : r.my_proposal ? <Text style={styles.acceptedTag}>⏳ {t("proposalSent")}</Text> : null}
                  </View>
                  <View style={{ alignItems: "flex-end", gap: 4 }}>
                    {r.suggested_price != null ? <Text style={styles.missionPrice}>€{Number(r.suggested_price).toFixed(0)}</Text> : null}
                    <Ionicons name="chevron-forward" size={20} color={colors.muted} />
                  </View>
                </View>
              </Pressable>
            ))}
            {opps.length > 6 ? (
              <Pressable testID="opp-see-all" style={styles.seeAllBtn} onPress={() => router.push("/(tabs)/richieste")}>
                <Text style={styles.seeAllText}>{t("seeAllActivity")} ({opps.length})</Text>
                <Ionicons name="arrow-forward" size={16} color={colors.brand} />
              </Pressable>
            ) : null}
          </>
        ) : null}

        <Text style={styles.sectionTitle}>{t("incomingMissions")}</Text>
        {incoming.length === 0 && opps.length === 0 ? (
          <View style={styles.empty}><Text style={{ fontSize: 40 }}>☕</Text><Text style={styles.emptyText}>{t("noMissions")}</Text></View>
        ) : (
          incoming.map((m) => (
            <View key={m.mission_id} style={[styles.missionCard, shadow.card]} testID={`incoming-${m.mission_id}`}>
              <View style={styles.missionRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.missionTitle}>{m.category} · {m.duration_hours}{t("hours")}</Text>
                  <Text style={styles.missionSub}>{m.address}</Text>
                  <Text style={styles.missionSub}>{m.date} · {m.time}</Text>
                  {m.budget ? <Text style={styles.budgetTag}>💰 {t("budgetLabel")}: €{Number(m.budget).toFixed(0)}</Text> : null}
                </View>
                <Text style={styles.missionPrice}>€{((user?.hourly_rate || 13) * m.duration_hours).toFixed(0)}</Text>
              </View>
              {m.already_accepted ? (
                <Text style={styles.acceptedTag}>⏳ {t("accepted2")}</Text>
              ) : (
                <View style={styles.actionRow}>
                  <Button testID={`decline-${m.mission_id}`} label={t("decline")} variant="secondary" onPress={() => act(m.mission_id, false)} style={{ flex: 1, height: 46 }} />
                  <Button testID={`accept-${m.mission_id}`} label={t("accept")} onPress={() => act(m.mission_id, true)} style={{ flex: 1, height: 46 }} />
                </View>
              )}
            </View>
          ))
        )}
      </ScrollView>
    </View>
  );
}

function BusinessHome() {
  const { user, refresh } = useAuth();
  const { lang, t } = useLang();
  const insets = useSafeAreaInsets();
  const [requests, setRequests] = useState<any[]>([]);
  const [online, setOnline] = useState(!!user?.online);
  const [active, setActive] = useState<any>(null); // request being responded to
  const [eta, setEta] = useState("");
  const [mode, setMode] = useState("pickup");
  const [deliveryCost, setDeliveryCost] = useState("0");
  const [price, setPrice] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setRequests(await api.incomingBusinessRequests()); } catch {}
  }, []);
  useFocusEffect(useCallback(() => { load(); const iv = setInterval(load, 5000); return () => clearInterval(iv); }, [load]));

  const toggleOnline = async (v: boolean) => {
    setOnline(v);
    Haptics.selectionAsync().catch(() => {});
    // Vedi commento nello stesso fix in ProviderHome.toggleOnline sopra.
    await api.updateProfile({ online: v });
    await refresh();
  };

  const openRespond = (r: any) => {
    setActive(r); setEta(""); setMode("pickup"); setDeliveryCost("0"); setPrice(""); setNote("");
  };

  const decline = async (r: any) => {
    Haptics.selectionAsync().catch(() => {});
    if (r.order) await api.respondOrder(r.request_id, { accept: false });
    else await api.respondBusinessRequest(r.request_id, { accept: false });
    load();
  };

  const completeOrd = async (r: any) => {
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    try { await api.completeOrder(r.request_id); } catch {}
    load();
  };

  const confirm = async () => {
    setBusy(true);
    try {
      if (active.order) {
        await api.respondOrder(active.request_id, { accept: true, eta, mode, note });
      } else {
        await api.respondBusinessRequest(active.request_id, {
          accept: true, eta, mode,
          delivery_cost: Number(deliveryCost) || 0,
          price: Number(price) || 0,
          note,
        });
      }
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      setActive(null);
      load();
    } catch {} finally { setBusy(false); }
  };

  const statusColor: Record<string, string> = { pending: colors.warning, confirmed: colors.success, completed: colors.brand, declined: colors.error, cancelled: colors.muted };

  return (
    <View style={styles.container}>
      <View style={[styles.pHeader, { paddingTop: insets.top + spacing.md }]}>
        <View>
          <Text style={styles.brandSmall}>JOBBY</Text>
          <Text style={styles.hi}>{user?.business_name || t("roleBusiness")}</Text>
        </View>
        <View style={styles.onlineToggle}>
          <NotifBell />
          <Text style={[styles.onlineText, { color: online ? colors.success : colors.muted }]}>{online ? t("online") : t("offline")}</Text>
          <Switch testID="online-toggle" value={online} onValueChange={toggleOnline} trackColor={{ true: colors.brand, false: colors.borderStrong }} thumbColor="#fff" />
        </View>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 100 }} showsVerticalScrollIndicator={false}>
        <Text style={styles.sectionTitle}>{t("incomingRequests")}</Text>
        {requests.length === 0 ? (
          <View style={styles.empty}><Text style={{ fontSize: 40 }}>🏪</Text><Text style={styles.emptyText}>{t("noIncomingRequests")}</Text></View>
        ) : (
          requests.map((r) => (
            <View key={r.request_id} style={[styles.missionCard, shadow.card]} testID={`breq-${r.request_id}`}>
              <View style={styles.missionRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.missionTitle}>{r.category_label?.[lang] || r.category}</Text>
                  <Text style={styles.missionSub}>{r.client_name}</Text>
                  {r.order && r.items?.length ? (
                    <View style={{ marginTop: 4, marginBottom: 2 }}>
                      {r.items.map((it: any, i: number) => (
                        <Text key={i} style={styles.orderLine}>{it.qty}× {it.descrizione} · €{Number(it.line_total).toFixed(2)}</Text>
                      ))}
                    </View>
                  ) : (
                    <Text style={styles.missionSub}>{r.note}</Text>
                  )}
                  {r.address ? <Text style={styles.missionSub}>📍 {r.address}</Text> : null}
                  {r.order ? (
                    <Text style={styles.budgetTag}>🔒 €{Number(r.total).toFixed(2)} {t("heldInEscrow")}</Text>
                  ) : r.budget ? (
                    <Text style={styles.budgetTag}>💰 {t("budgetLabel")}: €{Number(r.budget).toFixed(0)}</Text>
                  ) : null}
                </View>
                <View style={[styles.pill, { backgroundColor: (statusColor[r.status] || colors.muted) + "22" }]}>
                  <Text style={[styles.pillText, { color: statusColor[r.status] || colors.muted }]}>{t(`status_${r.status}` as any) || r.status}</Text>
                </View>
              </View>
              {r.status === "pending" ? (
                <View style={styles.actionRow}>
                  <Button testID={`breq-decline-${r.request_id}`} label={t("decline")} variant="secondary" onPress={() => decline(r)} style={{ flex: 1, height: 46 }} />
                  <Button testID={`breq-accept-${r.request_id}`} label={t("acceptConfirm")} onPress={() => openRespond(r)} style={{ flex: 1, height: 46 }} />
                </View>
              ) : r.status === "confirmed" && r.order && r.conferma_pending ? (
                <EarnerConfirm refId={r.request_id} onConfirmed={load} />
              ) : r.status === "confirmed" && r.order ? (
                <Button testID={`order-complete-${r.request_id}`} label={t("markDelivered")} onPress={() => completeOrd(r)} style={{ marginTop: spacing.md, height: 46 }} />
              ) : r.status === "confirmed" && r.response ? (
                <Text style={styles.confirmedInfo}>
                  {r.response.mode === "delivery" ? t("mode_delivery") : t("mode_pickup")} · {r.response.eta || "—"} · €{(r.response.price || 0).toFixed(2)} + €{(r.response.delivery_cost || 0).toFixed(2)}
                </Text>
              ) : null}
            </View>
          ))
        )}
      </ScrollView>

      {/* Respond modal */}
      <Modal visible={!!active} transparent animationType="slide" onRequestClose={() => setActive(null)}>
        <View style={styles.modalOverlay}>
          <View style={[styles.modalCard, { paddingBottom: insets.bottom + spacing.lg }]}>
            <View style={styles.modalHandle} />
            <Text style={styles.modalTitle}>{t("confirmRequest")}</Text>

            <Text style={styles.modalLabel}>{t("deliveryMode")}</Text>
            <View style={styles.modeRow}>
              {(["pickup", "delivery"] as const).map((m) => (
                <Pressable key={m} testID={`resp-mode-${m}`} style={[styles.modeChip, mode === m && styles.modeChipOn]} onPress={() => setMode(m)}>
                  <Text style={{ fontSize: 20 }}>{m === "pickup" ? "🏪" : "🚚"}</Text>
                  <Text style={[styles.modeText, mode === m && { color: "#fff" }]}>{m === "pickup" ? t("mode_pickup") : t("mode_delivery")}</Text>
                </Pressable>
              ))}
            </View>

            <Text style={styles.modalLabel}>{t("estimatedTime")}</Text>
            <TextInput testID="resp-eta" style={styles.modalInput} value={eta} onChangeText={setEta} placeholder={t("etaPlaceholder")} placeholderTextColor={colors.muted} />

            <View style={styles.row2}>
              <View style={{ flex: 1 }}>
                {active?.order ? null : (
                  <>
                    <Text style={styles.modalLabel}>{t("priceLabel")}</Text>
                    <TextInput testID="resp-price" style={styles.modalInput} value={price} onChangeText={setPrice} keyboardType="numeric" placeholder="0.00" placeholderTextColor={colors.muted} />
                  </>
                )}
              </View>
              {mode === "delivery" && !active?.order ? (
                <View style={{ flex: 1 }}>
                  <Text style={styles.modalLabel}>{t("deliveryCost")}</Text>
                  <TextInput testID="resp-delivery-cost" style={styles.modalInput} value={deliveryCost} onChangeText={setDeliveryCost} keyboardType="numeric" placeholder="0.00" placeholderTextColor={colors.muted} />
                </View>
              ) : null}
            </View>

            <Text style={styles.modalLabel}>{t("noteOptional")}</Text>
            <TextInput testID="resp-note" style={styles.modalInput} value={note} onChangeText={setNote} placeholder="" placeholderTextColor={colors.muted} />

            <View style={styles.actionRow}>
              <Button testID="resp-cancel" label={t("cancel")} variant="secondary" onPress={() => setActive(null)} style={{ flex: 1 }} />
              <Button testID="resp-confirm" label={t("confirm")} loading={busy} onPress={confirm} style={{ flex: 1 }} />
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  top: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, gap: spacing.sm },
  hi: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface },
  subhi: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 2 },
  walletPill: { backgroundColor: colors.greenBg, paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill },
  walletText: { color: colors.green, fontFamily: font.bold, fontSize: fsize.base },
  demoBanner: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: "#FEF3E2", marginHorizontal: spacing.lg, marginBottom: spacing.sm, paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.md },
  demoBannerText: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.warning },
  logo: { width: 44, height: 44, borderRadius: 12 },
  logoJ: { fontSize: 24, fontFamily: font.bold, color: colors.blue },
  body: { paddingHorizontal: spacing.lg },
  search: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 50 },
  searchInput: { flex: 1, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  mapCard: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.blueBg, borderRadius: radius.md, padding: spacing.md, marginTop: spacing.md, marginBottom: spacing.sm },
  mapIcon: { width: 46, height: 46, borderRadius: 23, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  mapTitle: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.blue },
  mapSub: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.blue, opacity: 0.8, marginTop: 1 },
  sectionTitle: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface, marginTop: spacing.xl, marginBottom: spacing.md },
  seeAllBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: spacing.md },
  seeAllText: { fontSize: fsize.base, fontFamily: font.bold, color: colors.brand },
  heroCard: { backgroundColor: colors.brand, borderRadius: radius.lg, padding: spacing.xl, marginTop: spacing.md },
  heroPromise: { fontSize: fsize["2xl"], fontFamily: font.bold, color: "#fff", lineHeight: 30 },
  entryCard: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1.5, borderColor: colors.brand, padding: spacing.lg, marginTop: spacing.md },
  entryTitle: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.onSurface },
  entrySub: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 2 },
  relCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, marginTop: spacing.md },
  relTop: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  relAvatar: { width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  relAvatarTxt: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.brand },
  relName: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.onSurface },
  relNext: { fontSize: fsize.base, fontFamily: font.medium, color: colors.brand, marginTop: 2 },
  relMeta: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 2 },
  relActions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md },
  relBtn: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 4, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.borderStrong, borderRadius: radius.md, paddingVertical: 10 },
  relBtnTxt: { fontSize: fsize.base, fontFamily: font.medium, color: colors.brand },
  problemBanner: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.surfaceTertiary, borderRadius: radius.sm, padding: spacing.sm, marginBottom: spacing.md },
  problemTxt: { flex: 1, fontSize: fsize.sm, fontFamily: font.medium, color: colors.onSurface },
  problemResolve: { fontSize: fsize.sm, fontFamily: font.bold, color: colors.warning },
  trustCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginTop: spacing.xl, gap: spacing.sm },
  trustRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  trustTxt: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  tile: {
    width: "31%", aspectRatio: 0.95, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center", gap: spacing.sm, paddingVertical: spacing.md,
  },
  tileEmoji: { fontSize: 34 },
  tileLabel: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface, textAlign: "center" },
  badge: { position: "absolute", top: 8, right: 8, minWidth: 22, height: 22, borderRadius: 11, alignItems: "center", justifyContent: "center", paddingHorizontal: 5 },
  badgeText: { color: "#fff", fontSize: fsize.sm, fontFamily: font.bold },
  floatWrap: { position: "absolute", left: 0, right: 0, alignItems: "center" },
  floatBtn: { paddingHorizontal: spacing.xl, minWidth: 220 },
  // provider
  pHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.divider },
  brandSmall: { fontSize: fsize.sm, fontFamily: font.bold, color: colors.primary, letterSpacing: 1 },
  onlineToggle: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  onlineText: { fontSize: fsize.base, fontFamily: font.medium },
  empty: { alignItems: "center", padding: spacing["2xl"], gap: spacing.md },
  emptyText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, textAlign: "center" },
  missionCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.lg, marginBottom: spacing.md },
  missionRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  missionTitle: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface, textTransform: "capitalize" },
  missionSub: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 1 },
  budgetTag: { fontSize: fsize.sm, fontFamily: font.bold, color: colors.green, marginTop: 4 },
  orderLine: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.onSurfaceTertiary },
  missionPrice: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.brand },
  actionRow: { flexDirection: "row", gap: spacing.md, marginTop: spacing.md },
  acceptedTag: { marginTop: spacing.md, fontSize: fsize.sm, fontFamily: font.medium, color: colors.warning },
  pill: { alignSelf: "flex-start", paddingHorizontal: spacing.sm, paddingVertical: 3, borderRadius: radius.pill },
  pillText: { fontSize: fsize.sm, fontFamily: font.medium, textTransform: "capitalize" },
  confirmedInfo: { marginTop: spacing.md, fontSize: fsize.base, fontFamily: font.medium, color: colors.success },
  modalOverlay: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  modalCard: { backgroundColor: colors.surface, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: spacing.lg },
  modalHandle: { width: 44, height: 5, borderRadius: 3, backgroundColor: colors.borderStrong, alignSelf: "center", marginBottom: spacing.md },
  modalTitle: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.onSurface, marginBottom: spacing.sm },
  modalLabel: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary, marginTop: spacing.md, marginBottom: spacing.sm },
  modalInput: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  modeRow: { flexDirection: "row", gap: spacing.sm },
  modeChip: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, paddingVertical: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  modeChipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  modeText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary },
  row2: { flexDirection: "row", gap: spacing.md },
});
