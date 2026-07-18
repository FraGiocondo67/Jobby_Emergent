import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";

const CRYPTO_TOKENS = [
  { id: "BTC", label: "Bitcoin (BTC)" },
  { id: "USDT_TRC20", label: "USDT (TRC20)" },
  { id: "USDC_ERC20", label: "USDC (ERC20)" },
  { id: "USDT_ERC20", label: "USDT (ERC20)" },
  { id: "XRP", label: "XRP" },
];

export default function PaymentsSettings() {
  const { user } = useAuth();
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [pm, setPm] = useState<any>(null);
  const [bank, setBank] = useState<any>(null);
  const [wallets, setWallets] = useState<any[]>([]);
  const [cardOpen, setCardOpen] = useState(false);
  const [bankOpen, setBankOpen] = useState(false);
  const [card, setCard] = useState({ card_holder: "", card_last4: "", expiry: "" });
  const [iban, setIban] = useState({ account_holder: "", iban: "" });
  const [cryptoToken, setCryptoToken] = useState<string | null>(null);
  const [cryptoAddr, setCryptoAddr] = useState("");

  const isProvider = user?.role === "provider" || user?.role === "business";

  const load = useCallback(async () => {
    try { const w = await api.wallet(); setPm(w.payment_method); setBank(w.bank_account); setWallets(w.crypto_wallets || []); } catch {}
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const saveCard = async () => { const r = await api.setPaymentMethod({ ...card, card_brand: "visa", card_last4: card.card_last4.slice(-4) }); setPm(r.payment_method); setCardOpen(false); Haptics.selectionAsync().catch(() => {}); };
  const saveBank = async () => { const r = await api.setBankAccount(iban); setBank(r.bank_account); setBankOpen(false); Haptics.selectionAsync().catch(() => {}); };
  const saveCrypto = async () => {
    if (!cryptoToken) return;
    const r = await api.setCryptoWallet(cryptoToken, cryptoAddr);
    setWallets(r.crypto_wallets); setCryptoToken(null); setCryptoAddr("");
    Haptics.selectionAsync().catch(() => {});
  };

  const walletFor = (tk: string) => wallets.find((w) => w.token === tk);

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="payments-back" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.primary} />
          <Text style={styles.backText}>Back</Text>
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>{t("paymentsSettings")}</Text>
        <Text style={styles.desc}>{isProvider ? t("payoutDesc") : t("paymentDesc")}</Text>

        {/* Card — how the client pays */}
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

        {/* Provider/Business payout: bank + crypto */}
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

            <Text style={styles.section}>{t("cryptoPayout")}</Text>
            {CRYPTO_TOKENS.map((tk) => {
              const w = walletFor(tk.id);
              const open = cryptoToken === tk.id;
              return (
                <View key={tk.id}>
                  <Pressable style={[styles.setupRow, shadow.card]} testID={`crypto-${tk.id}`} onPress={() => { setCryptoToken(open ? null : tk.id); setCryptoAddr(w?.address || ""); }}>
                    <Text style={{ fontSize: 20 }}>🪙</Text>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.setupText}>{tk.label}</Text>
                      {w ? <Text style={styles.cryptoAddr} numberOfLines={1}>{w.address}</Text> : null}
                    </View>
                    <Text style={styles.setupAction}>{w ? t("edit") : t("add")}</Text>
                  </Pressable>
                  {open ? (
                    <View style={styles.form}>
                      <TextInput testID={`crypto-addr-${tk.id}`} style={styles.input} placeholder={`${tk.label} address`} placeholderTextColor={colors.muted} autoCapitalize="none" value={cryptoAddr} onChangeText={setCryptoAddr} />
                      <Pressable testID={`save-crypto-${tk.id}`} style={styles.saveBtn} onPress={saveCrypto}><Text style={styles.saveText}>{t("save")}</Text></Pressable>
                    </View>
                  ) : null}
                </View>
              );
            })}
          </>
        ) : null}

        <View style={styles.mockBadge}><Text style={styles.mockText}>{t("mockNote")}</Text></View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  backBtn: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start" },
  backText: { color: colors.primary, fontSize: fsize.xl, fontFamily: font.medium },
  title: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface },
  desc: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: spacing.sm },
  section: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface, marginTop: spacing.xl, marginBottom: spacing.md },
  setupRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.lg, marginBottom: spacing.sm },
  setupText: { flex: 1, fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  cryptoAddr: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 2 },
  setupAction: { fontSize: fsize.base, fontFamily: font.medium, color: colors.primary },
  form: { marginTop: spacing.sm, gap: spacing.sm, marginBottom: spacing.sm },
  input: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  saveBtn: { height: 48, borderRadius: radius.md, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center" },
  saveText: { color: "#fff", fontSize: fsize.lg, fontFamily: font.medium },
  mockBadge: { marginTop: spacing.xl, alignSelf: "center", backgroundColor: colors.surfaceTertiary, paddingHorizontal: spacing.md, paddingVertical: 4, borderRadius: radius.pill },
  mockText: { color: colors.muted, fontSize: fsize.sm, fontFamily: font.medium },
});
