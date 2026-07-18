import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl, Platform, ActivityIndicator, Alert } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useFocusEffect, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import * as WebBrowser from "expo-web-browser";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";

const PACKAGES = [
  { id: "p10", amt: 10 },
  { id: "p25", amt: 25 },
  { id: "p50", amt: 50 },
];

export default function Wallet() {
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ session_id?: string }>();
  const [balance, setBalance] = useState(0);
  const [txs, setTxs] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(false);

  const load = useCallback(async () => {
    try { const w = await api.wallet(); setBalance(w.balance); setTxs(w.transactions); } catch {}
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const pollStatus = useCallback(async (sessionId: string) => {
    setChecking(true);
    for (let i = 0; i < 6; i++) {
      try {
        const s = await api.topupStatus(sessionId);
        if (s.payment_status === "paid") {
          await load();
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
          Alert.alert(t("topupSuccess"), `+€${(s.amount || 0).toFixed(2)}`);
          break;
        }
        if (s.status === "expired") break;
      } catch {}
      await new Promise((r) => setTimeout(r, 1500));
    }
    setChecking(false);
  }, [load, t]);

  // Handle return from Stripe on web (redirect adds ?session_id=...)
  useEffect(() => {
    if (params.session_id) { pollStatus(params.session_id as string); }
  }, [params.session_id, pollStatus]);

  const buy = async (pkg: { id: string; amt: number }) => {
    setBusy(true);
    Haptics.selectionAsync().catch(() => {});
    try {
      const origin = Platform.OS === "web" && typeof window !== "undefined"
        ? window.location.origin
        : (process.env.EXPO_PUBLIC_BACKEND_URL || "");
      const { url, session_id } = await api.topupCheckout(pkg.id, origin);
      if (Platform.OS === "web" && typeof window !== "undefined") {
        window.location.href = url;
      } else {
        await WebBrowser.openBrowserAsync(url);
        await pollStatus(session_id);
      }
    } catch {
      Alert.alert(t("error") || "Error", t("topupError"));
    } finally { setBusy(false); }
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
        </View>

        <Text style={styles.section}>{t("addFunds")}</Text>
        {checking ? (
          <View style={styles.checking}><ActivityIndicator color={colors.brand} /><Text style={styles.checkingText}>{t("verifyingPayment")}</Text></View>
        ) : null}
        <View style={styles.addRow}>
          {PACKAGES.map((p) => (
            <Pressable key={p.id} testID={`add-${p.amt}`} style={styles.addChip} disabled={busy} onPress={() => buy(p)}>
              <Text style={styles.addChipText}>+€{p.amt}</Text>
            </Pressable>
          ))}
        </View>
        <Text style={styles.stripeNote}>💳 {t("securedByStripe")}</Text>

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
  checking: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.md },
  checkingText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.brand },
  stripeNote: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: spacing.sm },
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
