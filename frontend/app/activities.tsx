import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import Slider from "@react-native-community/slider";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Button } from "@/src/components/UI";

const MODES = [
  { id: "outdoor", emoji: "🏠", labelKey: "mode_outdoor" },
  { id: "in_shop", emoji: "🏪", labelKey: "mode_in_shop" },
  { id: "both", emoji: "🔁", labelKey: "mode_both" },
] as const;

export default function Activities() {
  const { user, setUser } = useAuth();
  const { lang, t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [all, setAll] = useState<any[]>([]);
  const [selected, setSelected] = useState<string[]>(user?.services || []);
  const [radiusKm, setRadiusKm] = useState<number>(Math.round(user?.radius_km || 10));
  const [mode, setMode] = useState<string>(user?.service_mode || "both");
  const [loading, setLoading] = useState(false);

  const business = user?.role === "business";

  useEffect(() => {
    (async () => {
      try {
        const c = await api.categories();
        setAll(business ? c.proximity : c.standard);
      } catch {}
    })();
  }, [business]);

  const toggle = (id: string) => {
    Haptics.selectionAsync().catch(() => {});
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const save = async () => {
    setLoading(true);
    const payload: any = { services: selected, radius_km: radiusKm };
    if (business) payload.service_mode = mode;
    try {
      const updated = await api.updateProfile(payload);
      setUser(updated);
      router.back();
    } catch {
      // Surface nothing intrusive; stay on screen so the user can retry.
    } finally {
      setLoading(false);
    }
  };

  // Businesses that operate in-shop only don't need a travel radius.
  const showRadius = !business || mode !== "in_shop";

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="activities-back" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.primary} />
          <Text style={styles.backText}>Back</Text>
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 120 }} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>{t("myActivities")}</Text>
        <Text style={styles.desc}>{t("selectActivities")}</Text>
        <View style={styles.grid}>
          {all.map((c) => {
            const on = selected.includes(c.cat_id);
            return (
              <Pressable key={c.cat_id} testID={`activity-${c.cat_id}`} style={[styles.chip, on && styles.chipOn]} onPress={() => toggle(c.cat_id)}>
                <Text style={{ fontSize: 22 }}>{c.emoji}</Text>
                <Text style={[styles.chipText, on && { color: "#fff" }]}>{c.label[lang]}</Text>
                {on ? <Ionicons name="checkmark-circle" size={16} color="#fff" /> : null}
              </Pressable>
            );
          })}
        </View>

        {/* Business: service mode */}
        {business ? (
          <View style={styles.block}>
            <Text style={styles.blockTitle}>{t("serviceMode")}</Text>
            <Text style={styles.blockSub}>{t("serviceModeDesc")}</Text>
            <View style={styles.modeRow}>
              {MODES.map((m) => {
                const active = mode === m.id;
                return (
                  <Pressable key={m.id} testID={`mode-${m.id}`} style={[styles.modeChip, active && styles.modeChipOn]} onPress={() => { Haptics.selectionAsync().catch(() => {}); setMode(m.id); }}>
                    <Text style={{ fontSize: 22 }}>{m.emoji}</Text>
                    <Text style={[styles.modeText, active && { color: "#fff" }]}>{t(m.labelKey as any)}</Text>
                  </Pressable>
                );
              })}
            </View>
          </View>
        ) : null}

        {/* Service radius */}
        {showRadius ? (
          <View style={styles.block}>
            <View style={styles.radiusHead}>
              <Text style={styles.blockTitle}>{t("serviceRadius")}</Text>
              <Text style={styles.radiusValue}>{radiusKm} km</Text>
            </View>
            <Text style={styles.blockSub}>{t("serviceRadiusDesc")}</Text>
            <Slider
              testID="radius-slider"
              style={{ width: "100%", height: 40 }}
              minimumValue={1}
              maximumValue={50}
              step={1}
              value={radiusKm}
              onValueChange={(v) => setRadiusKm(Math.round(v))}
              minimumTrackTintColor={colors.brand}
              maximumTrackTintColor={colors.borderStrong}
              thumbTintColor={colors.brand}
            />
            <View style={styles.radiusScale}>
              <Text style={styles.scaleText}>1 km</Text>
              <Text style={styles.scaleText}>50 km</Text>
            </View>
          </View>
        ) : null}
      </ScrollView>
      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
        <Button testID="save-activities-button" label={t("save")} loading={loading} onPress={save} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  backBtn: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start" },
  backText: { color: colors.primary, fontSize: fsize.xl, fontFamily: font.medium },
  title: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface },
  desc: { fontSize: fsize.lg, fontFamily: font.regular, color: colors.muted, marginTop: spacing.sm, marginBottom: spacing.lg },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, ...shadow.card },
  chipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  block: { marginTop: spacing.xl, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, ...shadow.card },
  blockTitle: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  blockSub: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 2, marginBottom: spacing.md },
  modeRow: { flexDirection: "row", gap: spacing.sm },
  modeChip: { flex: 1, alignItems: "center", gap: 6, paddingVertical: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  modeChipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  modeText: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.onSurfaceTertiary, textAlign: "center" },
  radiusHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  radiusValue: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.brand },
  radiusScale: { flexDirection: "row", justifyContent: "space-between", marginTop: -4 },
  scaleText: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.lg, paddingTop: spacing.md, backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderTopColor: colors.divider },
});
