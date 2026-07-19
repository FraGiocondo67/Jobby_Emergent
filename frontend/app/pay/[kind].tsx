import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, KeyboardAvoidingView, Platform, Alert } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useLocalSearchParams, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize } from "@/src/theme";
import { Button } from "@/src/components/UI";
import Dropdown from "@/src/components/Dropdown";

const TITLE: Record<string, string> = { topup: "topupTitle", bill: "billTitle", abroad: "abroadTitle", local: "localTitle" };
const NOTE: Record<string, string> = { topup: "topupNote", abroad: "abroadNote", local: "localNote" };

export default function PayService() {
  const { kind } = useLocalSearchParams<{ kind: string }>();
  const k = kind as string;
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [balance, setBalance] = useState(0);
  const [hasCard, setHasCard] = useState(false);
  const [operators, setOperators] = useState<{ id: string; name: string }[]>([]);
  const [billers, setBillers] = useState<{ id: string; name: string }[]>([]);
  const [bens, setBens] = useState<any[]>([]);

  const [operatorId, setOperatorId] = useState<string | null>(null);
  const [phone, setPhone] = useState("");
  const [billerId, setBillerId] = useState<string | null>(null);
  const [billRef, setBillRef] = useState("");
  const [beneficiaryId, setBeneficiaryId] = useState<string | null>(null);
  const [amount, setAmount] = useState("");
  const [source, setSource] = useState<"wallet" | "card">("wallet");
  const [busy, setBusy] = useState(false);

  const loadWallet = useCallback(async () => {
    try { const w = await api.wallet(); setBalance(w.balance); setHasCard(!!w.payment_method); } catch {}
  }, []);
  const loadBens = useCallback(async () => {
    if (k === "abroad" || k === "local") {
      try { setBens(await api.beneficiaries(k)); } catch {}
    }
  }, [k]);

  useEffect(() => {
    (async () => {
      try { const o = await api.paymentOptions("IT"); setOperators(o.operators); setBillers(o.billers); } catch {}
    })();
  }, []);
  useFocusEffect(useCallback(() => { loadWallet(); loadBens(); }, [loadWallet, loadBens]));

  const validate = () => {
    const amt = Number(amount);
    if (!amt || amt <= 0) return t("amountLabel");
    if (k === "topup" && (!operatorId || !phone.trim())) return t("operatorLabel");
    if (k === "bill" && !billerId) return t("providerLabel");
    if ((k === "abroad" || k === "local") && !beneficiaryId) return t("selectBeneficiary");
    if (source === "wallet" && amt > balance) return t("insufficientFundsMsg");
    if (source === "card" && !hasCard) return t("noCardSetMsg");
    return null;
  };

  const pay = async () => {
    const err = validate();
    if (err) { Alert.alert(err); return; }
    setBusy(true);
    try {
      await api.servicePayment({
        kind: k, amount: Number(amount), source,
        operator_id: operatorId, phone_number: phone.trim(),
        biller_id: billerId, bill_ref: billRef.trim(),
        beneficiary_id: beneficiaryId,
      });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      Alert.alert(t("paymentDoneMsg"));
      router.replace("/pay/history");
    } catch (e: any) {
      const m = String(e?.message || "");
      if (m.includes("insufficient_funds")) Alert.alert(t("insufficientFundsMsg"));
      else if (m.includes("no_card")) Alert.alert(t("noCardSetMsg"));
      else Alert.alert(t("error"));
      setBusy(false);
    }
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="svc-back" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.primary} />
          <Text style={styles.backText}>{t("backStep")}</Text>
        </Pressable>
      </View>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 160 }} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
          <Text style={styles.title}>{t(TITLE[k] as any)}</Text>

          {k === "topup" ? (
            <>
              <Text style={styles.label}>{t("operatorLabel")}</Text>
              <Dropdown testID="svc-operator" value={operatorId} onChange={setOperatorId} placeholder={t("operatorLabel")} options={operators.map((o) => ({ value: o.id, label: o.name }))} />
              <Text style={styles.label}>{t("phoneNumberLabel")}</Text>
              <TextInput testID="svc-phone" style={styles.input} value={phone} onChangeText={setPhone} keyboardType="phone-pad" placeholder="+39 ..." placeholderTextColor={colors.muted} />
            </>
          ) : null}

          {k === "bill" ? (
            <>
              <Text style={styles.label}>{t("providerLabel")}</Text>
              <Dropdown testID="svc-biller" value={billerId} onChange={setBillerId} placeholder={t("providerLabel")} options={billers.map((b) => ({ value: b.id, label: b.name }))} />
              <Text style={styles.label}>{t("billReferenceLabel")}</Text>
              <TextInput testID="svc-billref" style={styles.input} value={billRef} onChangeText={setBillRef} placeholder="000000000" placeholderTextColor={colors.muted} />
            </>
          ) : null}

          {(k === "abroad" || k === "local") ? (
            <>
              <Text style={styles.label}>{t("selectBeneficiary")}</Text>
              {bens.length ? (
                <Dropdown testID="svc-beneficiary" value={beneficiaryId} onChange={setBeneficiaryId} placeholder={t("selectBeneficiary")} options={bens.map((b) => ({ value: b.ben_id, label: `${b.name} · ${b.iban}` }))} />
              ) : (
                <Text style={styles.emptyBen}>{t("noBeneficiaries")}</Text>
              )}
              <Pressable testID="svc-add-ben" style={styles.addBen} onPress={() => router.push(`/pay/beneficiaries?type=${k}`)}>
                <Ionicons name="add-circle-outline" size={18} color={colors.brand} />
                <Text style={styles.addBenText}>{t("addBeneficiary")}</Text>
              </Pressable>
            </>
          ) : null}

          <Text style={styles.label}>{t("amountLabel")}</Text>
          <TextInput testID="svc-amount" style={styles.input} value={amount} onChangeText={setAmount} keyboardType="numeric" placeholder="0.00" placeholderTextColor={colors.muted} />

          <Text style={styles.label}>{t("payFrom")}</Text>
          <View style={styles.sourceRow}>
            <Pressable testID="svc-src-wallet" style={[styles.srcBtn, source === "wallet" && styles.srcOn]} onPress={() => setSource("wallet")}>
              <Ionicons name="wallet-outline" size={18} color={source === "wallet" ? "#fff" : colors.onSurface} />
              <Text style={[styles.srcText, source === "wallet" && { color: "#fff" }]}>{t("fromWallet")} · €{balance.toFixed(2)}</Text>
            </Pressable>
            <Pressable testID="svc-src-card" style={[styles.srcBtn, source === "card" && styles.srcOn]} onPress={() => setSource("card")}>
              <Ionicons name="card-outline" size={18} color={source === "card" ? "#fff" : colors.onSurface} />
              <Text style={[styles.srcText, source === "card" && { color: "#fff" }]}>{t("fromCard")}</Text>
            </Pressable>
          </View>

          {NOTE[k] ? <Text style={styles.note}>{t(NOTE[k] as any)}</Text> : null}
        </ScrollView>
        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          <Button testID="svc-pay" label={t("payNowBtn")} loading={busy} onPress={pay} />
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  backBtn: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start" },
  backText: { color: colors.primary, fontSize: fsize.xl, fontFamily: font.medium },
  title: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface, marginBottom: spacing.sm },
  label: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary, marginTop: spacing.lg, marginBottom: spacing.sm },
  input: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  emptyBen: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted },
  addBen: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: spacing.sm, alignSelf: "flex-start" },
  addBenText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.brand },
  sourceRow: { flexDirection: "row", gap: spacing.md },
  srcBtn: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  srcOn: { backgroundColor: colors.brand, borderColor: colors.brand },
  srcText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  note: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: spacing.lg, fontStyle: "italic" },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.lg, paddingTop: spacing.md, backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderTopColor: colors.divider },
});
