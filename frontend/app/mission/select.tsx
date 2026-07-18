import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import { Image } from "expo-image";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Button, Stars, Badge } from "@/src/components/UI";

export default function SelectProvider() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [mission, setMission] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setMission(await api.getMission(id as string)); } catch {}
  }, [id]);

  useEffect(() => {
    load();
    const iv = setInterval(load, 3000);
    return () => clearInterval(iv);
  }, [load]);

  const select = async (providerId: string) => {
    setBusy(providerId);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    try {
      const booking = await api.selectProvider(id as string, providerId);
      router.replace(`/booking/${booking.booking_id}?new=1`);
    } catch {
      setBusy(null);
    }
  };

  const accepted = mission?.accepted || [];

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="select-back" onPress={() => router.back()} hitSlop={12}>
          <Ionicons name="arrow-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>{t("chooseProvider")}</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }} showsVerticalScrollIndicator={false}>
        {accepted.length === 0 ? (
          <View style={styles.empty}>
            <Ionicons name="hourglass-outline" size={40} color={colors.muted} />
            <Text style={styles.emptyText}>{t("searching")}</Text>
          </View>
        ) : (
          accepted.map((p: any) => (
            <View key={p.provider_id} style={[styles.card, shadow.card]} testID={`provider-${p.provider_id}`}>
              <View style={styles.cardTop}>
                {p.picture ? (
                  <Image source={{ uri: p.picture }} style={styles.avatar} contentFit="cover" />
                ) : (
                  <View style={[styles.avatar, styles.avatarFallback]}><Text style={styles.avatarInitial}>{p.name[0]}</Text></View>
                )}
                <View style={{ flex: 1 }}>
                  <View style={styles.nameRow}>
                    <Text style={styles.name}>{p.name}</Text>
                    {p.verified ? <Ionicons name="shield-checkmark" size={16} color={colors.brand} /> : null}
                  </View>
                  <View style={styles.metaRow}>
                    <Stars rating={p.rating} size={13} />
                    <Text style={styles.meta}>{p.rating.toFixed(1)} ({p.reviews_count})</Text>
                  </View>
                  <Text style={styles.meta}>{p.distance_km} km {t("away")} · ~{p.eta_min} min</Text>
                </View>
              </View>

              <View style={styles.priceBox}>
                <View style={styles.priceLine}>
                  <Text style={styles.priceLabel}>{t("labor")}</Text>
                  <Text style={styles.priceVal}>€{p.price.toFixed(2)}</Text>
                </View>
                <View style={styles.priceLine}>
                  <Text style={styles.priceLabel}>{t("jobbyFee")}</Text>
                  <Text style={styles.priceVal}>€{(p.price * 0.15).toFixed(2)}</Text>
                </View>
                <View style={[styles.priceLine, styles.totalLine]}>
                  <Text style={styles.totalLabel}>{t("total")}</Text>
                  <Text style={styles.totalVal}>€{(p.price * 1.15).toFixed(2)}</Text>
                </View>
              </View>

              <Button
                testID={`select-${p.provider_id}`}
                label={t("selectProvider")}
                loading={busy === p.provider_id}
                onPress={() => select(p.provider_id)}
              />
            </View>
          ))
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.divider },
  headerTitle: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  empty: { alignItems: "center", padding: spacing["3xl"], gap: spacing.md },
  emptyText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.lg, gap: spacing.md },
  cardTop: { flexDirection: "row", gap: spacing.md, alignItems: "center" },
  avatar: { width: 56, height: 56, borderRadius: 28 },
  avatarFallback: { backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" },
  avatarInitial: { color: "#fff", fontSize: 22, fontFamily: font.medium },
  nameRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  name: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 2 },
  meta: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 1 },
  priceBox: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md },
  priceLine: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 3 },
  priceLabel: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurfaceTertiary },
  priceVal: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  totalLine: { borderTopWidth: 1, borderTopColor: colors.divider, marginTop: 4, paddingTop: 8 },
  totalLabel: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  totalVal: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.brand },
});
