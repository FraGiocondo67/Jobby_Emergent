import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import { Image } from "expo-image";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Stars } from "@/src/components/UI";
import RealMap from "@/src/components/RealMap";
import { useDeviceLocation } from "@/src/hooks/use-device-location";

const TREVISO = { lat: 45.6669, lng: 12.2433 };

export default function BusinessesScreen() {
  const { category, label, emoji } = useLocalSearchParams<{ category: string; label: string; emoji: string }>();
  const { user } = useAuth();
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const { coords } = useDeviceLocation({ lat: user?.lat || TREVISO.lat, lng: user?.lng || TREVISO.lng });
  const lat = coords.lat;
  const lng = coords.lng;

  useEffect(() => {
    (async () => {
      try { setItems(await api.businesses(category as string, lat, lng)); } catch {}
      finally { setLoading(false); }
    })();
  }, [category, lat, lng]);

  const openBiz = (b: any) => {
    router.push(`/business-request/${b.user_id}?category=${category}&name=${encodeURIComponent(b.name)}&label=${encodeURIComponent((label as string) || "")}`);
  };

  const modeText = (m: string) => t(`mode_${m || "both"}` as any);

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="businesses-back" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.primary} />
          <Text style={styles.backText}>Back</Text>
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }} showsVerticalScrollIndicator={false}>
        <Text style={styles.bigEmoji}>{(emoji as string) || "🏪"}</Text>
        <Text style={styles.title}>{(label as string) || t("proximity")}</Text>
        <Text style={styles.subtitle}>{t("chooseBusiness")}</Text>

        {items.length > 0 ? (
          <View style={{ marginTop: spacing.lg }}>
            <RealMap
              center={{ lat, lng }}
              markers={items.map((b) => ({ lat: b.lat, lng: b.lng, emoji: "🏪", color: colors.purple, label: `${b.name} · ⭐${b.rating.toFixed(1)}` }))}
              height={200}
            />
          </View>
        ) : null}

        {items.length === 0 && !loading ? (
          <View style={styles.empty} testID="businesses-empty">
            <Text style={{ fontSize: 44 }}>🏪</Text>
            <Text style={styles.emptyTitle}>{t("noBusinessesNearby")}</Text>
            <Text style={styles.emptySub}>{t("noBusinessesHint")}</Text>
          </View>
        ) : (
          <View style={{ marginTop: spacing.xl, gap: spacing.md }}>
            {items.map((b) => (
              <Pressable key={b.user_id} testID={`business-${b.user_id}`} style={[styles.row, { borderColor: colors.purpleBorder }, shadow.card]} onPress={() => openBiz(b)}>
                {b.picture ? (
                  <Image source={{ uri: b.picture }} style={styles.avatar} contentFit="cover" />
                ) : (
                  <View style={[styles.avatar, styles.avatarFallback]}><Text style={styles.avatarInitial}>{b.name[0]}</Text></View>
                )}
                <View style={{ flex: 1 }}>
                  <View style={styles.nameRow}>
                    <Text style={styles.rowTitle}>{b.name}</Text>
                    {b.verified ? <Ionicons name="shield-checkmark" size={15} color={colors.brand} /> : null}
                  </View>
                  <View style={styles.metaRow}>
                    <Stars rating={b.rating} size={12} />
                    <Text style={styles.rowSub}>{b.rating.toFixed(1)} · {b.distance_km} km</Text>
                  </View>
                  <View style={styles.tagRow}>
                    <Text style={styles.trust}>🛡️ {t("trustScore")} {Math.round(b.trust_score || 0)}</Text>
                    <Text style={styles.modeTag}>{modeText(b.service_mode)}</Text>
                  </View>
                  {b.approval_status !== "approved" ? (
                    <View style={styles.pending}>
                      <Ionicons name="time-outline" size={12} color={colors.warning} />
                      <Text style={styles.pendingText}>{t("pendingApproval")}</Text>
                    </View>
                  ) : null}
                </View>
                <Ionicons name="arrow-forward" size={22} color={colors.purple} />
              </Pressable>
            ))}
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  backBtn: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start" },
  backText: { color: colors.primary, fontSize: fsize.xl, fontFamily: font.medium },
  bigEmoji: { fontSize: 46, textAlign: "center", marginTop: spacing.md },
  title: { fontSize: fsize["3xl"], fontFamily: font.bold, color: colors.onSurface, textAlign: "center", marginTop: spacing.md },
  subtitle: { fontSize: fsize.xl, fontFamily: font.regular, color: colors.muted, textAlign: "center", marginTop: spacing.sm },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md },
  avatar: { width: 52, height: 52, borderRadius: 26 },
  avatarFallback: { backgroundColor: colors.purple, alignItems: "center", justifyContent: "center" },
  avatarInitial: { color: "#fff", fontSize: 20, fontFamily: font.medium },
  nameRow: { flexDirection: "row", alignItems: "center", gap: 5 },
  rowTitle: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.onSurface },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 2 },
  rowSub: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted },
  tagRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, marginTop: 3, flexWrap: "wrap" },
  trust: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.brand },
  modeTag: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.purple },
  pending: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 4, alignSelf: "flex-start", backgroundColor: "#FEF3E2", paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.pill },
  pendingText: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.warning },
  empty: { alignItems: "center", gap: spacing.sm, paddingVertical: spacing["2xl"] },
  emptyTitle: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.onSurface, marginTop: spacing.sm },
  emptySub: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, textAlign: "center", paddingHorizontal: spacing.lg },
});
