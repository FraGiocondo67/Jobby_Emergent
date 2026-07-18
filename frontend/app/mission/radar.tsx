import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Button } from "@/src/components/UI";
import MapCanvas from "@/src/components/MapCanvas";

export default function Radar() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [mission, setMission] = useState<any>(null);

  const load = useCallback(async () => {
    try {
      const m = await api.getMission(id as string);
      setMission(m);
    } catch {}
  }, [id]);

  useEffect(() => {
    load();
    const iv = setInterval(load, 2000);
    return () => clearInterval(iv);
  }, [load]);

  const accepted = mission?.accepted || [];
  const invited = mission?.invited_provider_ids?.length || 0;
  const pins = accepted.map((a: any) => ({ lat: mission.lat + (Math.random() - 0.5) * 0.02, lng: mission.lng + (Math.random() - 0.5) * 0.02, highlight: true }));

  return (
    <View style={styles.container}>
      <View style={{ height: "58%" }}>
        <MapCanvas center={{ lat: mission?.lat || 45.6669, lng: mission?.lng || 12.2433 }} pins={pins} radar height={9999} />
        <Pressable testID="radar-back" style={[styles.backBtn, { top: insets.top + spacing.sm }]} onPress={() => router.replace("/(tabs)")} hitSlop={12}>
          <Ionicons name="close" size={22} color={colors.onSurface} />
        </Pressable>
      </View>

      <View style={[styles.sheet, shadow.card]}>
        <View style={styles.handle} />
        <Text style={styles.title}>{t("searching")}</Text>
        <View style={styles.counters}>
          <View style={styles.counter}>
            <Text style={styles.counterVal}>{invited}</Text>
            <Text style={styles.counterLbl}>{t("invited")}</Text>
          </View>
          <View style={styles.counterDivider} />
          <View style={styles.counter}>
            <Text style={[styles.counterVal, { color: colors.brand }]}>{accepted.length}</Text>
            <Text style={styles.counterLbl}>{t("accepted")}</Text>
          </View>
        </View>

        <View style={{ flex: 1 }} />

        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          <Button
            testID="see-providers-button"
            label={`${t("seeProviders")} (${accepted.length})`}
            disabled={accepted.length === 0}
            onPress={() => router.push(`/mission/select?id=${id}`)}
          />
          <Button testID="cancel-request-button" label={t("cancelRequest")} variant="ghost" onPress={() => router.replace("/(tabs)")} style={{ height: 44 }} />
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  backBtn: { position: "absolute", left: spacing.lg, width: 40, height: 40, borderRadius: 20, backgroundColor: "#fff", alignItems: "center", justifyContent: "center", ...shadow.card },
  sheet: { flex: 1, backgroundColor: colors.surfaceSecondary, borderTopLeftRadius: 28, borderTopRightRadius: 28, marginTop: -28, padding: spacing.xl },
  handle: { width: 44, height: 5, borderRadius: 3, backgroundColor: colors.borderStrong, alignSelf: "center", marginBottom: spacing.lg },
  title: { fontSize: fsize.xl, fontFamily: font.medium, color: colors.onSurface, textAlign: "center", marginBottom: spacing.xl },
  counters: { flexDirection: "row", alignItems: "center", justifyContent: "center", backgroundColor: colors.surface, borderRadius: radius.lg, paddingVertical: spacing.lg },
  counter: { flex: 1, alignItems: "center" },
  counterDivider: { width: 1, height: 40, backgroundColor: colors.border },
  counterVal: { fontSize: 34, fontFamily: font.bold, color: colors.onSurface },
  counterLbl: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 2 },
  footer: { gap: spacing.sm },
});
