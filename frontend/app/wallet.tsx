import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl, Platform, ActivityIndicator, Alert, TextInput } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useFocusEffect, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import * as WebBrowser from "expo-web-browser";
import { useAuth } from "@/src/context/AuthContext";
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
  const { user } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ session_id?: string }>();
  const [balance, setBalance] = useState(0);
  const [available, setAvailable] = useState(0);
  const [pending, setPending] = useState(0);
  const [holds, setHolds] = useState<any[]>([]);
  const [hasBank, setHasBank] = useState(false);
  const [hasCrypto, setHasCrypto] = useState(false);
  const [wMethod, setWMethod] = useState<"bank" | "crypto" | "yobpay" | "stripe">("bank");
  const [wAmount, setWAmount] = useState("");
  const [txs, setTxs] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(false);

  const load = useCallback(async () => {
    try {
      const w = await api.wallet();
      setBalance(w.total_balance ?? w.balance);
      setAvailable(w.available_balance ?? w.balance);
      setPending(w.pending_balance ?? 0);
      setHolds(w.holds || []);
      setHasBank(!!w.bank_account);
      setHasCrypto((w.crypto_wallets || []).length > 0);
      setTxs(w.transactions);
    } catch {}
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const withdraw = async () => {
    const amt = Number(wAmount);
    if (!amt || amt <= 0) { Alert.alert(t("amountLabel")); return; }
    setBusy(true);
    try {
      if (wMethod === "stripe") {
        await api.withdrawStripe(amt);
      } else {
        await api.withdraw({ method: wMethod, amount: amt });
      }
      setWAmount("");
      await load();
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      Alert.alert(t("withdrawDone"));
    } catch (e: any) {
      const m = String(e?.message || "");
      if (m.includes("insufficient_available")) Alert.alert(t("insufficientFundsMsg"));
      else if (m.includes("no_bank_account")) Alert.alert(t("methodBank"), t("notSet"));
      else if (m.includes("no_crypto_wallet")) Alert.alert(t("methodCrypto"), t("notSet"));
      else if (m.includes("no_connect_account")) Alert.alert(t("methodStripe"), t("noConnectAccountMsg"));
      else if (m.includes("payouts_not_enabled")) Alert.alert(t("methodStripe"), t("payoutsNotEnabledMsg"));
      else if (m.includes("signed up for Connect") || m.includes("Connect")) Alert.alert(t("methodStripe"), t("stripeConnectNotEnabled"));
      else Alert.alert(t("error"));
    } finally { setBusy(false); }
  };

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
          <Text style={styles.heroLabel}>{t("totalBalance")}</Text>
          <Text style={styles.heroValue}>€{balance.toFixed(2)}</Text>
          <View style={styles.splitRow}>
            <View style={styles.splitCol}>
              <Text style={styles.splitLabel}>{t("availableBalance")}</Text>
              <Text style={styles.splitValue} testID="wallet-available">€{available.toFixed(2)}</Text>
            </View>
            <View style={styles.splitDivider} />
            <View style={styles.splitCol}>
              <Text style={styles.splitLabel}>🔒 {t("blockedBalance")}</Text>
              <Text style={styles.splitValue} testID="wallet-pending">€{pending.toFixed(2)}</Text>
            </View>
          </View>
        </View>

        {holds.length ? (
          <>
            <Text style={styles.section}>{t("pendingReleaseLabel")}</Text>
            {holds.map((h) => (
              <View key={h.hold_id} style={[styles.txRow, shadow.card]} testID={`hold-${h.hold_id}`}>
                <Text style={{ fontSize: 22 }}>⏳</Text>
                <View style={{ flex: 1 }}>
                  <Text style={styles.txLabel}>€{h.amount.toFixed(2)}</Text>
                  <Text style={styles.txDate}>{t("releaseOn")} {new Date(h.release_at).toLocaleDateString()}</Text>
                </View>
              </View>
            ))}
          </>
        ) : null}

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

        <Text style={styles.section}>{t("withdraw")}</Text>
        <View style={styles.methodRow}>
          {(([["bank", "methodBank", "business-outline"], ["crypto", "methodCrypto", "logo-bitcoin"], ["yobpay", "methodYobpay", "card-outline"],
            ...((user?.role === "provider" || user?.role === "business") ? [["stripe", "methodStripe", "card"]] : []),
          ]) as [string, string, string][]).map(([m, key, icon]) => (
            <Pressable key={m} testID={`wm-${m}`} style={[styles.methodBtn, wMethod === m && styles.methodOn]} onPress={() => setWMethod(m as any)}>
              <Ionicons name={icon as any} size={18} color={wMethod === m ? "#fff" : colors.onSurface} />
              <Text style={[styles.methodText, wMethod === m && { color: "#fff" }]}>{t(key as any)}</Text>
            </Pressable>
          ))}
        </View>
        <View style={styles.withdrawRow}>
          <TextInput testID="withdraw-amount" style={styles.wInput} value={wAmount} onChangeText={setWAmount} keyboardType="numeric" placeholder="€ 0.00" placeholderTextColor={colors.muted} />
          <Pressable testID="withdraw-btn" style={styles.wBtn} disabled={busy} onPress={withdraw}>
            <Text style={styles.wBtnText}>{t("withdraw")}</Text>
          </Pressable>
        </View>
        <Text style={styles.stripeNote}>{wMethod === "yobpay" ? t("localNote") : `${t("availableBalance")}: €${available.toFixed(2)}`}</Text>

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
  splitRow: { flexDirection: "row", alignItems: "center", marginTop: spacing.md, backgroundColor: "rgba(255,255,255,0.15)", borderRadius: radius.md, paddingVertical: spacing.sm },
  splitCol: { flex: 1, alignItems: "center" },
  splitDivider: { width: 1, height: 32, backgroundColor: "rgba(255,255,255,0.3)" },
  splitLabel: { color: "rgba(255,255,255,0.85)", fontSize: fsize.sm, fontFamily: font.regular },
  splitValue: { color: "#fff", fontSize: fsize.xl, fontFamily: font.bold, marginTop: 2 },
  methodRow: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.md },
  methodBtn: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 4, paddingVertical: spacing.sm, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  methodOn: { backgroundColor: colors.brand, borderColor: colors.brand },
  methodText: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.onSurface },
  withdrawRow: { flexDirection: "row", gap: spacing.sm },
  wInput: { flex: 1, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  wBtn: { backgroundColor: colors.brand, borderRadius: radius.md, paddingHorizontal: spacing.lg, alignItems: "center", justifyContent: "center" },
  wBtnText: { color: "#fff", fontSize: fsize.lg, fontFamily: font.bold },
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
