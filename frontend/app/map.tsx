import React, { useEffect, useState } from "react";
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

const TREVISO = { lat: 45.6669, lng: 12.2433 };

export default function MapScreen() {
  const { user } = useAuth();
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [providers, setProviders] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const center = { lat: user?.lat || TREVISO.lat, lng: user?.lng || TREVISO.lng };

  useEffect(() => {
    (async () => {
      try {
        setProviders(await api.providersNearby(center.lat, center.lng));
      } catch {}
      finally { setLoading(false); }
    })();
  }, [center.lat, center.lng]);

  const markers = providers.map((p) => ({
    lat: p.lat,
    lng: p.lng,
    emoji: p.role === "business" ? "🏪" : "🧑‍🔧",
    label: `${p.business_name || p.name} · ${p.distance_km} km`,
  }));

  return (
    <View style={styles.container}>
      <View style={{ height: "48%" }}>
        <RealMap center={center} markers={markers} height="100%" />
        <Pressable testID="map-back" style={[styles.backBtn, { top: insets.top + spacing.sm }]} onPress={() => router.back()} hitSlop={12}>
          <Ionicons name="arrow-back" size={22} color={colors.onSurface} />
        </Pressable>
      </View>
      <View style={styles.sheet}>
        <View style={styles.handle} />
        <Text style={styles.title}>{t("allProvidersNear")} · Treviso</Text>
        <ScrollView contentContainerStyle={{ paddingBottom: insets.bottom + 20 }} showsVerticalScrollIndicator={false}>
          {providers.length === 0 && !loading ? (
            <View style={styles.empty} testID="map-empty">
              <Text style={{ fontSize: 44 }}>🗺️</Text>
              <Text style={styles.emptyTitle}>{t("noProvidersNearby")}</Text>
              <Text style={styles.emptySub}>{t("noProvidersHint")}</Text>
            </View>
          ) : (
            providers.map((p) => (
              <View key={p.user_id} style={[styles.card, shadow.card]} testID={`map-provider-${p.user_id}`}>
                {p.picture ? (
                  <Image source={{ uri: p.picture }} style={styles.avatar} contentFit="cover" />
                ) : (
                  <View style={[styles.avatar, styles.avatarFallback]}><Text style={styles.avatarInitial}>{(p.business_name || p.name)[0]}</Text></View>
                )}
                <View style={{ flex: 1 }}>
                  <Text style={styles.name}>{p.business_name || p.name}</Text>
                  <View style={styles.metaRow}>
                    <Stars rating={p.rating} size={12} />
                    <Text style={styles.meta}>{p.rating.toFixed(1)} · {p.distance_km} km</Text>
                  </View>
                  {p.role === "business" ? (
                    <Text style={styles.modeTag}>{t(`mode_${p.service_mode || "both"}` as any)}</Text>
                  ) : null}
                </View>
                <Text style={styles.rate}>€{p.hourly_rate.toFixed(0)}{t("perHour")}</Text>
              </View>
            ))
          )}
        </ScrollView>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  backBtn: { position: "absolute", left: spacing.lg, width: 40, height: 40, borderRadius: 20, backgroundColor: "#fff", alignItems: "center", justifyContent: "center", ...shadow.card },
  sheet: { flex: 1, backgroundColor: colors.surfaceSecondary, borderTopLeftRadius: 28, borderTopRightRadius: 28, marginTop: -28, padding: spacing.lg },
  handle: { width: 44, height: 5, borderRadius: 3, backgroundColor: colors.borderStrong, alignSelf: "center", marginBottom: spacing.md },
  title: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.onSurface, marginBottom: spacing.md },
  card: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md, marginBottom: spacing.sm },
  avatar: { width: 48, height: 48, borderRadius: 24 },
  avatarFallback: { backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" },
  avatarInitial: { color: "#fff", fontSize: 18, fontFamily: font.medium },
  name: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 2 },
  meta: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted },
  modeTag: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.purple, marginTop: 2 },
  rate: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.brand },
  empty: { alignItems: "center", gap: spacing.sm, paddingVertical: spacing["2xl"] },
  emptyTitle: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.onSurface, marginTop: spacing.sm },
  emptySub: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, textAlign: "center", paddingHorizontal: spacing.lg },
});
