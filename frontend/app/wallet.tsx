import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl, TextInput } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";

export default function Wallet() {
  const { user } = useAuth();
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [balance, setBalance] = useState(0);
  const [txs, setTxs] = useState<any[]>([]);
  const [pm, setPm] = useState<any>(null);
  const [bank, setBank] = useState<any>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [cardOpen, setCardOpen] = useState(false);
  const [bankOpen, setBankOpen] = useState(false);
  const [card, setCard] = useState({ card_holder: "", card_last4: "", expiry: "" });
  const [iban, setIban] = useState({ account_holder: "", iban: "" });

  const isProvider = user?.role === "provider" || user?.role === "business";

  const load = useCallback(async () => {
    try { const w = await api.wallet(); setBalance(w.balance); setTxs(w.transactions); setPm(w.payment_method); setBank(w.bank_account); } catch {}
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
  const saveCard = async () => { const r = await api.setPaymentMethod({ ...card, card_brand: "visa", card_last4: card.card_last4.slice(-4) }); setPm(r.payment_method); setCardOpen(false); };
  const saveBank = async () => { const r = await api.setBankAccount(iban); setBank(r.bank_account); setBankOpen(false); };

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

        <Text style={styles.section}>{t("paymentMethod")}</Text>
        <Pressable style={[styles.setupRow, shadow.card]} testID="payment-method-row" onPress={() => setCardOpen((v) => !v)}>
          <Ionicons name="card" size={22} color={colors.blue} />
          <Text style={styles.setupText}>{pm ? `${(pm.card_brand || "").toUpperCase()} •••• ${pm.card_last4}` : t("notSet")}</Text>
          <Text style={styles.setupAction}>{t("addCard")}</Text>
        </Pressable>
        {cardOpen ? (
          <View style={styles.form}>
            <TextInput testID="card-holder" style={styles.input} placeholder="Card holder" placeholderTextColor={colors.muted} value={card.card_holder} onChangeText={(v) => setCard({ ...card, card_holder: v })} />
            <TextInput testID="card-number" style={styles.input} placeholder="Card number" placeholderTextColor={colors.muted} keyboardType="number-pad" value={card.card_last4} onChangeText={(v) => setCard({ ...card, card_last4: v })} />
            <TextInput testID="card-expiry" style={styles.input} placeholder="MM/YY" placeholderTextColor={colors.muted} value={card.expiry} onChangeText={(v) => setCard({ ...card, expiry: v })} />
            <Pressable testID="save-card" style={styles.saveBtn} onPress={saveCard}><Text style={styles.saveText}>{t("save")}</Text></Pressable>
          </View>
        ) : null}

        {isProvider ? (
          <>
            <Text style={styles.section}>{t("bankAccount")}</Text>
            <Pressable style={[styles.setupRow, shadow.card]} testID="bank-row" onPress={() => setBankOpen((v) => !v)}>
              <Ionicons name="business" size={22} color={colors.green} />
              <Text style={styles.setupText}>{bank ? bank.iban : t("notSet")}</Text>
              <Text style={styles.setupAction}>{t("addBank")}</Text>
            </Pressable>
            {bankOpen ? (
              <View style={styles.form}>
                <TextInput testID="bank-holder" style={styles.input} placeholder="Account holder" placeholderTextColor={colors.muted} value={iban.account_holder} onChangeText={(v) => setIban({ ...iban, account_holder: v })} />
                <TextInput testID="bank-iban" style={styles.input} placeholder="IBAN" placeholderTextColor={colors.muted} autoCapitalize="characters" value={iban.iban} onChangeText={(v) => setIban({ ...iban, iban: v })} />
                <Pressable testID="save-bank" style={styles.saveBtn} onPress={saveBank}><Text style={styles.saveText}>{t("save")}</Text></Pressable>
              </View>
            ) : null}
          </>
        ) : null}

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
  setupRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.lg },
  setupText: { flex: 1, fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  setupAction: { fontSize: fsize.base, fontFamily: font.medium, color: colors.primary },
  form: { marginTop: spacing.sm, gap: spacing.sm },
  input: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  saveBtn: { height: 48, borderRadius: radius.md, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center" },
  saveText: { color: "#fff", fontSize: fsize.lg, fontFamily: font.medium },
  emptyText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted },
  txRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.sm },
  txLabel: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  txDate: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 1 },
  txAmount: { fontSize: fsize.lg, fontFamily: font.bold },
});
