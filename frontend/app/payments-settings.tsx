import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, Platform, Alert } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import * as WebBrowser from "expo-web-browser";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import Dropdown from "@/src/components/Dropdown";

const TOKEN_OPTIONS = [
  { value: "USDT_TRC", label: "USDT (Tron)" },
  { value: "USDT_ETH", label: "USDT (Ethereum)" },
  { value: "USDC_ETH", label: "USDC (Ethereum)" },
  { value: "XRP", label: "XRP" },
  { value: "BTC", label: "Bitcoin (BTC)" },
];
const NETWORK_OPTIONS = [
  { value: "TRC20", label: "TRC20 (Tron)" },
  { value: "ERC20", label: "ERC20 (Ethereum)" },
  { value: "XRPL", label: "XRP Ledger" },
  { value: "BTC", label: "Bitcoin" },
];
const DEFAULT_NETWORK: Record<string, string> = {
  USDT_TRC: "TRC20", USDT_ETH: "ERC20", USDC_ETH: "ERC20", XRP: "XRPL", BTC: "BTC",
};

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
  const [card, setCard] = useState({ card_holder: "", card_last4: "", expiry: "", cvv: "" });
  const [iban, setIban] = useState({ account_holder: "", iban: "" });
  const [paypalEmail, setPaypalEmail] = useState("");
  const [paypalOpen, setPaypalOpen] = useState(false);
  // add-crypto form
  const [cwOpen, setCwOpen] = useState(false);
  const [cwToken, setCwToken] = useState<string | null>(null);
  const [cwName, setCwName] = useState("");
  const [cwAddr, setCwAddr] = useState("");
  const [cwNetwork, setCwNetwork] = useState<string | null>(null);
  const [connect, setConnect] = useState<any>(null);
  const [connBusy, setConnBusy] = useState(false);

  const isProvider = user?.role === "provider" || user?.role === "business";

  const load = useCallback(async () => {
    try { const w = await api.wallet(); setPm(w.payment_method); setBank(w.bank_account); setWallets(w.crypto_wallets || []); setPaypalEmail(w.paypal_email || ""); } catch {}
    if (user?.role === "provider" || user?.role === "business") {
      try { setConnect(await api.connectStatus()); } catch {}
    }
  }, [user?.role]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const startStripeOnboarding = async () => {
    setConnBusy(true);
    Haptics.selectionAsync().catch(() => {});
    try {
      const origin = Platform.OS === "web" && typeof window !== "undefined"
        ? window.location.origin
        : (process.env.EXPO_PUBLIC_BACKEND_URL || "");
      const { url } = await api.connectOnboarding(origin);
      if (Platform.OS === "web" && typeof window !== "undefined") {
        window.location.href = url;
      } else {
        await WebBrowser.openBrowserAsync(url);
        await load();
      }
    } catch (e: any) {
      const m = String(e?.message || "");
      if (m.includes("stripe_connect_not_enabled") || m.includes("Connect")) Alert.alert(t("stripePayout"), t("stripeConnectNotEnabled"));
      else Alert.alert(t("error"));
    } finally { setConnBusy(false); }
  };

  const savePaypal = async () => {
    try { const r = await api.setPaypalEmail(paypalEmail.trim()); setPaypalEmail(r.paypal_email); setPaypalOpen(false); Haptics.selectionAsync().catch(() => {}); } catch {}
  };

  const saveCard = async () => {
    try {
      const r = await api.setPaymentMethod({ ...card, card_brand: "visa", card_last4: card.card_last4.slice(-4) });
      setPm(r.payment_method); setCardOpen(false); setCard({ card_holder: "", card_last4: "", expiry: "", cvv: "" });
      Haptics.selectionAsync().catch(() => {});
    } catch (e: any) {
      if (String(e?.message) !== "unauthorized") Alert.alert(t("error"));
    }
  };
  const saveBank = async () => {
    try { const r = await api.setBankAccount(iban); setBank(r.bank_account); setBankOpen(false); Haptics.selectionAsync().catch(() => {}); }
    catch (e: any) { if (String(e?.message) !== "unauthorized") Alert.alert(t("error")); }
  };

  const pickToken = (tk: string) => { setCwToken(tk); setCwNetwork(DEFAULT_NETWORK[tk] || null); };
  const saveCrypto = async () => {
    if (!cwToken || !cwAddr.trim()) return;
    try {
      const r = await api.setCryptoWallet({ token: cwToken, name: cwName.trim(), address: cwAddr.trim(), network: cwNetwork || "" });
      setWallets(r.crypto_wallets);
      setCwOpen(false); setCwToken(null); setCwName(""); setCwAddr(""); setCwNetwork(null);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    } catch (e: any) {
      if (String(e?.message) !== "unauthorized") Alert.alert(t("error"));
    }
  };
  const deleteCrypto = async (id: string) => {
    const r = await api.deleteCryptoWallet(id); setWallets(r.crypto_wallets);
    Haptics.selectionAsync().catch(() => {});
  };

  const tokenLabel = (v: string) => TOKEN_OPTIONS.find((o) => o.value === v)?.label || v;
  const netLabel = (v: string) => NETWORK_OPTIONS.find((o) => o.value === v)?.label || v;

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="payments-back" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.primary} />
          <Text style={styles.backText}>Back</Text>
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>{t("paymentsSettings")}</Text>
        <Text style={styles.desc}>{isProvider ? t("payoutDesc") : t("clientPayoutDesc")}</Text>

        {/* Card */}
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
            <View style={styles.row2}>
              <TextInput testID="card-expiry" style={[styles.input, { flex: 1 }]} placeholder="MM/YY" placeholderTextColor={colors.muted} value={card.expiry} onChangeText={(v) => setCard({ ...card, expiry: v })} />
              <TextInput testID="card-cvv" style={[styles.input, { flex: 1 }]} placeholder="CVV" placeholderTextColor={colors.muted} keyboardType="number-pad" secureTextEntry maxLength={4} value={card.cvv} onChangeText={(v) => setCard({ ...card, cvv: v })} />
            </View>
            <Pressable testID="save-card" style={styles.saveBtn} onPress={saveCard}><Text style={styles.saveText}>{t("save")}</Text></Pressable>
          </View>
        ) : null}

        {/* Payout / withdrawal methods (client & provider) */}
        {user ? (
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

            {/* PayPal payout email */}
            <Text style={styles.section}>{t("paypalEmailLabel")}</Text>
            <Pressable style={[styles.setupRow, shadow.card]} testID="paypal-row" onPress={() => setPaypalOpen((v) => !v)}>
              <Ionicons name="logo-paypal" size={22} color="#0070BA" />
              <Text style={styles.setupText}>{paypalEmail || t("notSet")}</Text>
              <Text style={styles.setupAction}>{paypalEmail ? t("save") : t("addBank")}</Text>
            </Pressable>
            {paypalOpen ? (
              <View style={styles.form}>
                <TextInput testID="paypal-email" style={styles.input} placeholder="you@paypal.com" placeholderTextColor={colors.muted} keyboardType="email-address" autoCapitalize="none" value={paypalEmail} onChangeText={setPaypalEmail} />
                <Pressable testID="save-paypal" style={styles.saveBtn} onPress={savePaypal}><Text style={styles.saveText}>{t("save")}</Text></Pressable>
              </View>
            ) : null}

            {/* Crypto payout */}
            <View style={styles.cryptoHead}>
              <Text style={styles.section}>{t("cryptoPayout")}</Text>
              <Pressable testID="add-crypto" style={styles.addLink} onPress={() => setCwOpen((v) => !v)}>
                <Ionicons name={cwOpen ? "close" : "add"} size={18} color={colors.brand} />
                <Text style={styles.addLinkText}>{cwOpen ? t("cancel") : t("addWallet")}</Text>
              </Pressable>
            </View>

            {wallets.length === 0 && !cwOpen ? <Text style={styles.emptyText}>{t("noCryptoWallets")}</Text> : null}

            {wallets.map((w) => (
              <View key={w.wallet_id} style={[styles.walletCard, shadow.card]} testID={`crypto-wallet-${w.wallet_id}`}>
                <Text style={{ fontSize: 22 }}>🪙</Text>
                <View style={{ flex: 1 }}>
                  <Text style={styles.walletName}>{w.name}</Text>
                  <Text style={styles.walletMeta}>{tokenLabel(w.token)} · {netLabel(w.network)}</Text>
                  <Text style={styles.walletAddr} numberOfLines={1}>{w.address}</Text>
                </View>
                <Pressable testID={`delete-crypto-${w.wallet_id}`} hitSlop={10} onPress={() => deleteCrypto(w.wallet_id)}>
                  <Ionicons name="trash-outline" size={20} color={colors.error} />
                </Pressable>
              </View>
            ))}

            {cwOpen ? (
              <View style={[styles.cryptoForm, shadow.card]}>
                <Text style={styles.fieldLabel}>{t("cryptoAsset")}</Text>
                <Dropdown testID="crypto-token-dd" value={cwToken} options={TOKEN_OPTIONS} placeholder={t("selectCrypto")} onChange={pickToken} />

                <Text style={styles.fieldLabel}>{t("walletName")}</Text>
                <TextInput testID="crypto-name" style={styles.input} placeholder={t("walletNamePlaceholder")} placeholderTextColor={colors.muted} value={cwName} onChangeText={setCwName} />

                <Text style={styles.fieldLabel}>{t("walletAddress")}</Text>
                <TextInput testID="crypto-address" style={styles.input} placeholder={t("pasteAddress")} placeholderTextColor={colors.muted} autoCapitalize="none" value={cwAddr} onChangeText={setCwAddr} />

                <Text style={styles.fieldLabel}>{t("confirmNetwork")}</Text>
                <Dropdown testID="crypto-network-dd" value={cwNetwork} options={NETWORK_OPTIONS} placeholder={t("selectNetwork")} onChange={setCwNetwork} />

                <Pressable testID="save-crypto" style={[styles.saveBtn, { marginTop: spacing.md, opacity: cwToken && cwAddr.trim() && cwNetwork ? 1 : 0.5 }]} disabled={!(cwToken && cwAddr.trim() && cwNetwork)} onPress={saveCrypto}>
                  <Text style={styles.saveText}>{t("confirm")}</Text>
                </Pressable>
              </View>
            ) : null}
          </>
        ) : null}

        {/* Stripe Connect real payout (providers/business) */}
        {isProvider ? (
          <>
            <Text style={styles.section}>{t("stripePayout")}</Text>
            <View style={[styles.setupRow, shadow.card]}>
              <Ionicons name="card-outline" size={22} color="#635BFF" />
              <View style={{ flex: 1 }}>
                <Text style={styles.setupText}>
                  {connect?.payouts_enabled ? t("stripePayoutReady") : connect?.connected ? t("stripePayoutPending") : t("stripeConnectDesc")}
                </Text>
              </View>
            </View>
            <Pressable testID="stripe-connect-btn" style={[styles.saveBtn, { backgroundColor: "#635BFF", marginTop: spacing.sm, opacity: connBusy ? 0.6 : 1 }]} disabled={connBusy} onPress={startStripeOnboarding}>
              <Text style={styles.saveText}>{connect?.payouts_enabled ? t("save") : t("configureStripe")}</Text>
            </Pressable>
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
  setupAction: { fontSize: fsize.base, fontFamily: font.medium, color: colors.primary },
  form: { marginTop: spacing.sm, gap: spacing.sm, marginBottom: spacing.sm },
  row2: { flexDirection: "row", gap: spacing.sm },
  input: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  saveBtn: { height: 48, borderRadius: radius.md, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center" },
  saveText: { color: "#fff", fontSize: fsize.lg, fontFamily: font.medium },
  cryptoHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: spacing.xl },
  addLink: { flexDirection: "row", alignItems: "center", gap: 2 },
  addLinkText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.brand },
  emptyText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: spacing.sm },
  walletCard: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, marginTop: spacing.sm },
  walletName: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  walletMeta: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.brand, marginTop: 1 },
  walletAddr: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 1 },
  cryptoForm: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginTop: spacing.md, gap: spacing.sm },
  fieldLabel: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary, marginTop: spacing.sm },
  mockBadge: { marginTop: spacing.xl, alignSelf: "center", backgroundColor: colors.surfaceTertiary, paddingHorizontal: spacing.md, paddingVertical: 4, borderRadius: radius.pill },
  mockText: { color: colors.muted, fontSize: fsize.sm, fontFamily: font.medium },
});
