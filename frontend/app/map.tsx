import React, { useEffect, useMemo, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import { Image } from "expo-image";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Stars } from "@/src/components/UI";
import RealMap from "@/src/components/RealMap";
import { useDeviceLocation } from "@/src/hooks/use-device-location";

const TREVISO = { lat: 45.6669, lng: 12.2433 };

function PendingBadge() {
  const { t } = useLang();
  return (
    <View style={styles.pending}>
      <Ionicons name="time-outline" size={12} color={colors.warning} />
      <Text style={styles.pendingText}>{t("pendingApproval")}</Text>
    </View>
  );
}

function TrustChip({ score }: { score: number }) {
  const { t } = useLang();
  return <Text style={styles.trust}>🛡️ {t("trustScore")} {Math.round(score)}</Text>;
}

function ActivePill({ online }: { online: boolean }) {
  const { t } = useLang();
  return (
    <View style={[styles.statusPill, { backgroundColor: online ? "#E4F4E8" : "#F0F0F0" }]}>
      <View style={[styles.statusDot, { backgroundColor: online ? colors.success : colors.muted }]} />
      <Text style={[styles.statusText, { color: online ? colors.success : colors.muted }]}>{online ? t("active") : t("inactive")}</Text>
    </View>
  );
}

export default function MapScreen() {
  const { user } = useAuth();
  const { t, lang } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [all, setAll] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showProviders, setShowProviders] = useState(true);
  const [showBusinesses, setShowBusinesses] = useState(true);
  const [radiusKm, setRadiusKm] = useState<number>(user?.radius_km || 10);
  const [category, setCategory] = useState<string | null>(null);
  const [cats, setCats] = useState<any[]>([]);

  const RADII = [2, 5, 10, 20, 50];

  const fallbackCenter = { lat: user?.lat || TREVISO.lat, lng: user?.lng || TREVISO.lng };
  const { coords: center } = useDeviceLocation(fallbackCenter);

  useEffect(() => {
    (async () => {
      try { const c = await api.categories(); setCats([...(c.standard || []), ...(c.proximity || [])]); } catch {}
    })();
  }, []);

  useEffect(() => {
    setLoading(true);
    (async () => {
      try { setAll(await api.providersNearby(center.lat, center.lng, category || undefined, radiusKm)); } catch {}
      finally { setLoading(false); }
    })();
  }, [center.lat, center.lng, category, radiusKm]);

  const providers = useMemo(() => all.filter((p) => p.role === "provider"), [all]);
  const businesses = useMemo(() => all.filter((p) => p.role === "business"), [all]);

  const markers = useMemo(() => {
    const m: any[] = [];
    if (showProviders) providers.forEach((p) => m.push({ lat: p.lat, lng: p.lng, emoji: "🧑‍🔧", color: colors.blue, label: `${p.name} · ⭐${p.rating.toFixed(1)}` }));
    if (showBusinesses) businesses.forEach((b) => m.push({ lat: b.lat, lng: b.lng, emoji: "🏪", color: colors.purple, label: `${b.business_name || b.name} · ⭐${b.rating.toFixed(1)}` }));
    return m;
  }, [providers, businesses, showProviders, showBusinesses]);

  return (
    <View style={styles.container}>
      <View style={{ height: "40%" }}>
        <RealMap center={center} markers={markers} radiusKm={radiusKm} height="100%" />
        <Pressable testID="map-back" style={[styles.backBtn, { top: insets.top + spacing.sm }]} onPress={() => router.back()} hitSlop={12}>
          <Ionicons name="arrow-back" size={22} color={colors.onSurface} />
        </Pressable>
        {/* filter tabs */}
        <View style={[styles.tabs, { top: insets.top + spacing.sm }]}>
          <Pressable testID="tab-providers" style={[styles.tab, showProviders && styles.tabProvidersOn]} onPress={() => setShowProviders((v) => !v)}>
            <Text style={[styles.tabText, showProviders && { color: "#fff" }]}>🧑‍🔧 {t("providers")}</Text>
          </Pressable>
          <Pressable testID="tab-businesses" style={[styles.tab, showBusinesses && styles.tabBusinessesOn]} onPress={() => setShowBusinesses((v) => !v)}>
            <Text style={[styles.tabText, showBusinesses && { color: "#fff" }]}>🏪 {t("businesses")}</Text>
          </Pressable>
        </View>
        {/* legend */}
        <View style={styles.legend}>
          <View style={styles.legendRow}><View style={[styles.dot, { backgroundColor: colors.brand }]} /><Text style={styles.legendText}>{t("yourLocation")}</Text></View>
          <View style={styles.legendRow}><View style={[styles.dot, { backgroundColor: colors.blue }]} /><Text style={styles.legendText}>{t("providerOnline")}</Text></View>
          <View style={styles.legendRow}><View style={[styles.dot, { backgroundColor: colors.purple }]} /><Text style={styles.legendText}>{t("nearbyBusiness")}</Text></View>
        </View>
      </View>

      <View style={styles.sheet}>
        <View style={styles.handle} />
        {/* Radius selector */}
        <View style={styles.radiusRow}>
          <Text style={styles.radiusLabel}>📍 {t("searchRadius")}: <Text style={{ fontFamily: font.bold, color: colors.brand }}>{radiusKm} km</Text></Text>
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, paddingBottom: spacing.sm }}>
          {RADII.map((r) => (
            <Pressable key={r} testID={`radius-${r}`} onPress={() => setRadiusKm(r)} style={[styles.rChip, radiusKm === r && styles.rChipOn]}>
              <Text style={[styles.rChipText, radiusKm === r && { color: "#fff" }]}>{r} km</Text>
            </Pressable>
          ))}
        </ScrollView>
        {/* Category filter */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, paddingBottom: spacing.md }}>
          <Pressable testID="cat-all" onPress={() => setCategory(null)} style={[styles.catChip, !category && styles.catChipOn]}>
            <Text style={[styles.catChipText, !category && { color: "#fff" }]}>🔎 {t("allCategories")}</Text>
          </Pressable>
          {cats.map((c) => (
            <Pressable key={c.cat_id} testID={`cat-${c.cat_id}`} onPress={() => setCategory(c.cat_id)} style={[styles.catChip, category === c.cat_id && styles.catChipOn]}>
              <Text style={[styles.catChipText, category === c.cat_id && { color: "#fff" }]}>{c.emoji} {c.label[lang]}</Text>
            </Pressable>
          ))}
        </ScrollView>
        <ScrollView contentContainerStyle={{ paddingBottom: insets.bottom + 20 }} showsVerticalScrollIndicator={false}>
          {!loading && providers.length === 0 && businesses.length === 0 ? (
            <View style={styles.empty} testID="map-empty">
              <Text style={{ fontSize: 44 }}>🗺️</Text>
              <Text style={styles.emptyTitle}>{t("noProvidersNearby")}</Text>
              <Text style={styles.emptySub}>{t("noProvidersHint")}</Text>
            </View>
          ) : null}

          {showProviders && providers.length > 0 ? (
            <>
              <Text style={styles.section}>👤 {t("providersOnlineTitle")} ({providers.length})</Text>
              {providers.map((p) => (
                <Pressable key={p.user_id} style={[styles.card, shadow.card]} testID={`map-provider-${p.user_id}`} onPress={() => router.push(`/provider/${p.user_id}`)}>
                  {p.picture ? <Image source={{ uri: p.picture }} style={styles.avatar} contentFit="cover" /> : <View style={[styles.avatar, styles.avFallback, { backgroundColor: colors.blue }]}><Text style={styles.avInit}>{p.name[0]}</Text></View>}
                  <View style={{ flex: 1 }}>
                    <Text style={styles.name}>{p.name}</Text>
                    <Text style={styles.sub}>{(p.services || []).join(" · ")}</Text>
                    <View style={styles.metaRow}><Stars rating={p.rating} size={12} /><Text style={styles.meta}>{p.rating.toFixed(1)}</Text><TrustChip score={p.trust_score} /><ActivePill online={p.online} /></View>
                    {p.approval_status !== "approved" ? <PendingBadge /> : null}
                  </View>
                  <View style={{ alignItems: "flex-end", gap: 4 }}>
                    <Text style={styles.rate}>€{p.hourly_rate.toFixed(0)}{t("perHour")}</Text>
                    <Ionicons name="chevron-forward" size={20} color={colors.muted} />
                  </View>
                </Pressable>
              ))}
            </>
          ) : null}

          {showBusinesses && businesses.length > 0 ? (
            <>
              <Text style={styles.section}>🏪 {t("nearbyBusinessesTitle")} ({businesses.length})</Text>
              {businesses.map((b) => (
                <Pressable key={b.user_id} style={[styles.card, shadow.card]} testID={`map-business-${b.user_id}`} onPress={() => router.push(`/provider/${b.user_id}`)}>
                  {b.picture ? <Image source={{ uri: b.picture }} style={styles.avatar} contentFit="cover" /> : <View style={[styles.avatar, styles.avFallback, { backgroundColor: colors.purple }]}><Text style={styles.avInit}>{(b.business_name || b.name)[0]}</Text></View>}
                  <View style={{ flex: 1 }}>
                    <Text style={styles.name}>{b.business_name || b.name}</Text>
                    <Text style={styles.sub}>{(b.services || []).join(" · ")} · {b.distance_km} km</Text>
                    <View style={styles.metaRow}><Stars rating={b.rating} size={12} /><Text style={styles.meta}>{b.rating.toFixed(1)}</Text><TrustChip score={b.trust_score} /><ActivePill online={b.online} /></View>
                    {b.approval_status !== "approved" ? <PendingBadge /> : null}
                  </View>
                  <Ionicons name="chevron-forward" size={20} color={colors.muted} />
                </Pressable>
              ))}
            </>
          ) : null}
        </ScrollView>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  backBtn: { position: "absolute", left: spacing.lg, width: 40, height: 40, borderRadius: 20, backgroundColor: "#fff", alignItems: "center", justifyContent: "center", ...shadow.card },
  tabs: { position: "absolute", right: spacing.lg, flexDirection: "row", gap: spacing.sm },
  tab: { paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill, backgroundColor: "#fff", ...shadow.card },
  tabProvidersOn: { backgroundColor: colors.blue },
  tabBusinessesOn: { backgroundColor: colors.purple },
  tabText: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.onSurface },
  legend: { position: "absolute", left: spacing.lg, bottom: spacing.lg, backgroundColor: "rgba(255,255,255,0.94)", borderRadius: radius.md, padding: spacing.sm, gap: 4, ...shadow.card },
  legendRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  dot: { width: 10, height: 10, borderRadius: 5 },
  legendText: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.onSurface },
  sheet: { flex: 1, backgroundColor: colors.surfaceSecondary, borderTopLeftRadius: 28, borderTopRightRadius: 28, marginTop: -28, padding: spacing.lg },
  handle: { width: 44, height: 5, borderRadius: 3, backgroundColor: colors.borderStrong, alignSelf: "center", marginBottom: spacing.md },
  radiusRow: { marginBottom: spacing.sm },
  radiusLabel: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  rChip: { paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  rChipOn: { backgroundColor: colors.brand, borderColor: colors.brand },
  rChipText: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.onSurfaceTertiary },
  catChip: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  catChipOn: { backgroundColor: colors.purple, borderColor: colors.purple },
  catChipText: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.onSurfaceTertiary },
  statusPill: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.pill },
  statusDot: { width: 7, height: 7, borderRadius: 4 },
  statusText: { fontSize: fsize.sm, fontFamily: font.medium },
  section: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface, marginTop: spacing.md, marginBottom: spacing.sm },
  card: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md, marginBottom: spacing.sm },
  avatar: { width: 48, height: 48, borderRadius: 24 },
  avFallback: { alignItems: "center", justifyContent: "center" },
  avInit: { color: "#fff", fontSize: 18, fontFamily: font.medium },
  name: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  sub: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 1, textTransform: "capitalize" },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 3, flexWrap: "wrap" },
  meta: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted },
  trust: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.brand },
  rate: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.brand },
  pending: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 4, alignSelf: "flex-start", backgroundColor: "#FEF3E2", paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.pill },
  pendingText: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.warning },
  empty: { alignItems: "center", gap: spacing.sm, paddingVertical: spacing["2xl"] },
  emptyTitle: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.onSurface, marginTop: spacing.sm },
  emptySub: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, textAlign: "center", paddingHorizontal: spacing.lg },
});
