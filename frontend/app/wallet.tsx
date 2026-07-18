import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";

export default function Wallet() {
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [balance, setBalance] = useState(0);
  const [txs, setTxs] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { const w = await api.wallet(); setBalance(w.balance); setTxs(w.transactions); } catch {}
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const add = async (amount: number) => {
    setBusy(true);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    const r = await api.addFunds(amount);
    setBalance(r.balance);
    await load();
    setBusy(false);
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="wallet-back" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.primary} />
          <Text style={styles.backText}>Back</Text>
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />} showsVerticalScrollIndicator={false}>
        <View style={styles.hero}>
          <Text style={styles.heroLabel}>{t("balance")}</Text>
          <Text style={styles.heroValue}>€{balance.toFixed(2)}</Text>
          <View style={styles.mockBadge}><Text style={styles.mockText}>{t("mockNote")}</Text></View>
        </View>

        <Text style={styles.section}>{t("addFunds")}</Text>
        <View style={styles.addRow}>
          {[10, 25, 50].map((a) => (
            <Pressable key={a} testID={`add-${a}`} style={styles.addChip} disabled={busy} onPress={() => add(a)}>
              <Text style={styles.addChipText}>+€{a}</Text>
            </Pressable>
          ))}
        </View>

        <Text style={styles.section}>{t("transactions")}</Text>
        {txs.length === 0 ? (
          <Text style={styles.emptyText}>{t("noTransactions")}</Text>
        ) : (
          txs.map((tx) => (
            <View key={tx.tx_id} style={[styles.txRow, shadow.card]} testID={`tx-${tx.tx_id}`}>
              <Text style={{ fontSize: 22 }}>{tx.type === "topup" ? "➕" : "💸"}</Text>
              <View style={{ flex: 1 }}>
                <Text style={styles.txLabel}>{tx.label}</Text>
                <Text style={styles.txDate}>{new Date(tx.created_at).toLocaleString()}</Text>
              </View>
              <Text style={[styles.txAmount, { color: tx.amount >= 0 ? colors.success : colors.error }]}>
                {tx.amount >= 0 ? "+" : ""}€{Math.abs(tx.amount).toFixed(2)}
              </Text>
            </View>
          ))
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
  hero: { backgroundColor: colors.brand, borderRadius: radius.lg, padding: spacing.xl, alignItems: "center" },
  heroLabel: { color: "rgba(255,255,255,0.85)", fontSize: fsize.base, fontFamily: font.regular },
  heroValue: { color: "#fff", fontSize: 44, fontFamily: font.bold, marginTop: 4 },
  mockBadge: { marginTop: spacing.sm, backgroundColor: "rgba(255,255,255,0.2)", paddingHorizontal: spacing.md, paddingVertical: 3, borderRadius: radius.pill },
  mockText: { color: "#fff", fontSize: fsize.sm, fontFamily: font.medium },
  section: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface, marginTop: spacing.xl, marginBottom: spacing.md },
  addRow: { flexDirection: "row", gap: spacing.md },
  addChip: { flex: 1, height: 54, borderRadius: radius.md, borderWidth: 1, borderColor: colors.greenBorder, backgroundColor: colors.greenBg, alignItems: "center", justifyContent: "center" },
  addChipText: { color: colors.green, fontSize: fsize.lg, fontFamily: font.bold },
  emptyText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted },
  txRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.sm },
  txLabel: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  txDate: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 1 },
  txAmount: { fontSize: fsize.lg, fontFamily: font.bold },
});
