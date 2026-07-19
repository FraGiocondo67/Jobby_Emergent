import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";

const EMOJI: Record<string, string> = { topup: "📱", bill: "🧾", abroad: "🌍", local: "💶" };
const FILTERS = [
  { id: "all", key: "filterAll" },
  { id: "topup", key: "filterTopup" },
  { id: "bill", key: "filterBill" },
  { id: "abroad", key: "filterAbroad" },
  { id: "local", key: "filterLocal" },
] as const;

export default function PayHistory() {
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<any[]>([]);
  const [filter, setFilter] = useState<string>("all");
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (kind: string) => {
    try { setItems(await api.paymentHistory(kind)); } catch {}
  }, []);
  useFocusEffect(useCallback(() => { load(filter); }, [load, filter]));

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="hist-back" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.primary} />
          <Text style={styles.backText}>{t("backStep")}</Text>
        </Pressable>
      </View>
      <Text style={styles.title}>{t("txHistory")}</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipScroll} contentContainerStyle={{ paddingHorizontal: spacing.lg, gap: spacing.sm }}>
        {FILTERS.map((f) => (
          <Pressable key={f.id} testID={`hist-filter-${f.id}`} style={[styles.chip, filter === f.id && styles.chipOn]} onPress={() => setFilter(f.id)}>
            <Text style={[styles.chipText, filter === f.id && styles.chipTextOn]}>{t(f.key as any)}</Text>
          </Pressable>
        ))}
      </ScrollView>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(filter); setRefreshing(false); }} />} showsVerticalScrollIndicator={false}>
        {items.length === 0 ? (
          <View style={styles.empty}><Text style={{ fontSize: 36 }}>🧾</Text><Text style={styles.emptyText}>{t("noPaymentsYet")}</Text></View>
        ) : items.map((tx) => (
          <View key={tx.tx_id} style={[styles.row, shadow.card]} testID={`hist-${tx.tx_id}`}>
            <Text style={{ fontSize: 24 }}>{EMOJI[tx.kind] || "💸"}</Text>
            <View style={{ flex: 1 }}>
              <Text style={styles.rowLabel}>{tx.label}</Text>
              <Text style={styles.rowSub}>{new Date(tx.created_at).toLocaleString()} · {tx.source === "wallet" ? t("fromWallet") : t("fromCard")}</Text>
            </View>
            <Text style={styles.rowAmount}>-€{Math.abs(tx.amount).toFixed(2)}</Text>
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  backBtn: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start" },
  backText: { color: colors.primary, fontSize: fsize.xl, fontFamily: font.medium },
  title: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface, paddingHorizontal: spacing.lg, marginBottom: spacing.md },
  chipScroll: { flexGrow: 0, marginBottom: spacing.sm },
  chip: { paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  chipOn: { backgroundColor: colors.brand, borderColor: colors.brand },
  chipText: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.onSurfaceTertiary },
  chipTextOn: { color: "#fff" },
  empty: { alignItems: "center", gap: spacing.sm, paddingVertical: spacing["2xl"] },
  emptyText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.sm, borderWidth: 1, borderColor: colors.border },
  rowLabel: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  rowSub: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 1 },
  rowAmount: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.error },
});
