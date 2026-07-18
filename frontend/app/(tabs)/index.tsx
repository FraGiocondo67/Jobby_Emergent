import React, { useCallback, useMemo, useState } from "react";
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
  const [query, setQuery] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [c, w] = await Promise.all([api.categories(), api.wallet()]);
      const std = (c.standard || []).map((s: any) => ({ ...s, kind: "service" }));
      const built = [
        ...std,
        { cat_id: "prossimita", emoji: "🏪", label: { it: "Prossimità", en: "Proximity" }, kind: "proximity", accent: "purple", badge: (c.proximity || []).length },
        { cat_id: "pagamenti", emoji: "💳", label: { it: "Pagamenti", en: "Payments" }, kind: "payment", accent: "green", badge: (c.payment || []).length },
      ];
      setTiles(built);
      setOnline(c.providers_online);
      setBalance(w.balance);
    } catch {}
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const filtered = useMemo(
    () => tiles.filter((c) => c.label[lang].toLowerCase().includes(query.toLowerCase())),
    [tiles, query, lang]
  );

  const openCategory = (c: any) => {
    Haptics.selectionAsync().catch(() => {});
    if (c.kind === "proximity") router.push(`/list/prossimita`);
    else if (c.kind === "payment") router.push(`/list/pagamenti`);
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
          <Image source={require("@/assets/images/jobby-logo.png")} style={styles.logo} contentFit="cover" />
        </View>

        <View style={styles.body}>
          <View style={styles.search}>
            <Ionicons name="search" size={18} color={colors.muted} />
            <TextInput
              testID="search-input"
              style={styles.searchInput}
              placeholder={t("searchCategory")}
              placeholderTextColor={colors.muted}
              value={query}
              onChangeText={setQuery}
            />
          </View>

          <Pressable testID="explore-map-card" style={styles.mapCard} onPress={() => router.push("/map")}>
            <Text style={{ fontSize: 26 }}>🗺️</Text>
            <View style={{ flex: 1 }}>
              <Text style={styles.mapTitle}>{t("exploreMap")}</Text>
              <Text style={styles.mapSub}>{t("allProvidersNear")} · Treviso</Text>
            </View>
            <Ionicons name="arrow-forward" size={20} color={colors.blue} />
          </Pressable>

          <Text style={styles.sectionTitle}>{t("whatDoYouNeed")}</Text>
          <View style={styles.grid}>
            {filtered.map((c) => (
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
        </View>
      </ScrollView>

      <View style={[styles.floatWrap, { bottom: insets.bottom + 96 }]} pointerEvents="box-none">
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
  const { user, setUser } = useAuth();
  const { t } = useLang();
  const insets = useSafeAreaInsets();
  const [incoming, setIncoming] = useState<any[]>([]);
  const [online, setOnline] = useState(!!user?.online);

  const load = useCallback(async () => {
    try { setIncoming(await api.incomingMissions()); } catch {}
  }, []);
  useFocusEffect(useCallback(() => { load(); const iv = setInterval(load, 4000); return () => clearInterval(iv); }, [load]));

  const toggleOnline = async (v: boolean) => {
    setOnline(v);
    Haptics.selectionAsync().catch(() => {});
    setUser(await api.updateProfile({ online: v }));
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
          <Text style={[styles.onlineText, { color: online ? colors.success : colors.muted }]}>{online ? t("online") : t("offline")}</Text>
          <Switch testID="online-toggle" value={online} onValueChange={toggleOnline} trackColor={{ true: colors.brand, false: colors.borderStrong }} thumbColor="#fff" />
        </View>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 100 }} showsVerticalScrollIndicator={false}>
        <RealMap center={{ lat: user?.lat || 45.6669, lng: user?.lng || 12.2433 }} markers={pins} radiusKm={user?.radius_km || 10} height={200} />
        <Text style={styles.sectionTitle}>{t("incomingMissions")}</Text>
        {incoming.length === 0 ? (
          <View style={styles.empty}><Text style={{ fontSize: 40 }}>☕</Text><Text style={styles.emptyText}>{t("noMissions")}</Text></View>
        ) : (
          incoming.map((m) => (
            <View key={m.mission_id} style={[styles.missionCard, shadow.card]} testID={`incoming-${m.mission_id}`}>
              <View style={styles.missionRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.missionTitle}>{m.category} · {m.duration_hours}{t("hours")}</Text>
                  <Text style={styles.missionSub}>{m.address}</Text>
                  <Text style={styles.missionSub}>{m.date} · {m.time}</Text>
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
  const { user, setUser } = useAuth();
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
    setUser(await api.updateProfile({ online: v }));
  };

  const openRespond = (r: any) => {
    setActive(r); setEta(""); setMode("pickup"); setDeliveryCost("0"); setPrice(""); setNote("");
  };

  const decline = async (r: any) => {
    Haptics.selectionAsync().catch(() => {});
    await api.respondBusinessRequest(r.request_id, { accept: false });
    load();
  };

  const confirm = async () => {
    setBusy(true);
    try {
      await api.respondBusinessRequest(active.request_id, {
        accept: true, eta, mode,
        delivery_cost: Number(deliveryCost) || 0,
        price: Number(price) || 0,
        note,
      });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      setActive(null);
      load();
    } catch {} finally { setBusy(false); }
  };

  const statusColor: Record<string, string> = { pending: colors.warning, confirmed: colors.success, declined: colors.error };

  return (
    <View style={styles.container}>
      <View style={[styles.pHeader, { paddingTop: insets.top + spacing.md }]}>
        <View>
          <Text style={styles.brandSmall}>JOBBY</Text>
          <Text style={styles.hi}>{user?.business_name || t("roleBusiness")}</Text>
        </View>
        <View style={styles.onlineToggle}>
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
                  <Text style={styles.missionSub}>{r.note}</Text>
                  {r.address ? <Text style={styles.missionSub}>📍 {r.address}</Text> : null}
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
                <Text style={styles.modalLabel}>{t("priceLabel")}</Text>
                <TextInput testID="resp-price" style={styles.modalInput} value={price} onChangeText={setPrice} keyboardType="numeric" placeholder="0.00" placeholderTextColor={colors.muted} />
              </View>
              {mode === "delivery" ? (
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
  logo: { width: 44, height: 44, borderRadius: 12 },
  logoJ: { fontSize: 24, fontFamily: font.bold, color: colors.blue },
  body: { paddingHorizontal: spacing.lg },
  search: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 50 },
  searchInput: { flex: 1, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  mapCard: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.blueBg, borderRadius: radius.md, padding: spacing.md, marginTop: spacing.md },
  mapTitle: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.blue },
  mapSub: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.blue, opacity: 0.8, marginTop: 1 },
  sectionTitle: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface, marginTop: spacing.xl, marginBottom: spacing.md },
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
