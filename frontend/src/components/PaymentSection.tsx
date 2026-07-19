import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, Alert, Platform } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import * as Haptics from "expo-haptics";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, fsize, shadow } from "@/src/theme";
import { Button } from "@/src/components/UI";

function getOrigin() {
  return Platform.OS === "web" && typeof window !== "undefined"
    ? window.location.origin
    : (process.env.EXPO_PUBLIC_BACKEND_URL || "");
}

/**
 * Sezione pagamento riutilizzabile per TUTTE le categorie (richiesta condivisa).
 * Mostra le opzioni di pagamento reale (Stripe destination charge / PayPal split)
 * o il fallback Portafoglio JOBBY dopo la conferma del professionista.
 */
export default function PaymentSection({ r, onDone }: { r: any; onDone: () => void }) {
  const { t } = useLang();
  const params = useLocalSearchParams();
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(false);

  const rid = r.richiesta_id;
  const pl = r.pagamento_lavoro || {};
  const stato = pl.stato;
  const isLF = r.binario === "persona_lf";
  const total = Number(r.prezzo_finale || 0);
  const net = Number(pl.importo || 0);
  const fee = Number(pl.jobby_fee_total || 0);

  const pollStripe = useCallback(async (sessionId: string) => {
    setChecking(true);
    for (let i = 0; i < 8; i++) {
      try {
        const s = await api.payRichiestaStripeStatus(sessionId);
        if (s.paid) { await onDone(); Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
          Alert.alert(t("paySuccess")); break; }
      } catch {}
      await new Promise((res) => setTimeout(res, 1500));
    }
    setChecking(false);
  }, [onDone, t]);

  // Ritorno da Stripe/PayPal su web (redirect con ?pay=success&session_id=...)
  useEffect(() => {
    if (params.pay === "success" && params.session_id) pollStripe(params.session_id as string);
    else if (params.pay === "success" && params.order_id) {
      (async () => { try { await api.payRichiestaPaypalCapture(params.order_id as string); await onDone(); } catch {} })();
    }
  }, [params.pay, params.session_id, params.order_id, pollStripe, onDone]);

  if (isLF || !rid) return null;

  const startPay = async (method: "stripe" | "paypal" | "wallet") => {
    setBusy(true);
    Haptics.selectionAsync().catch(() => {});
    try {
      const origin = getOrigin();
      const res = await api.payRichiestaCheckout(rid, method, origin);
      if (method === "wallet") { await onDone(); Alert.alert(t("payHeld"), t("payHeldMsg")); return; }
      if (res.url) {
        if (Platform.OS === "web" && typeof window !== "undefined") { window.location.href = res.url; }
        else {
          await WebBrowser.openBrowserAsync(res.url);
          if (method === "stripe") await pollStripe(res.session_id);
          else if (res.order_id) { try { await api.payRichiestaPaypalCapture(res.order_id); await onDone(); } catch {} }
        }
      }
    } catch (e: any) {
      const m = String(e?.message || "");
      if (m.includes("not_onboarded")) Alert.alert(t("payTitle"), t("payProviderNotOnboarded"));
      else if (m.includes("insufficient")) Alert.alert(t("payTitle"), t("payInsufficient"));
      else Alert.alert(t("payError"));
    } finally { setBusy(false); }
  };

  const release = async () => {
    setBusy(true);
    try { await api.releaseRichiestaPayment(rid); await onDone(); }
    catch { Alert.alert(t("error")); } finally { setBusy(false); }
  };

  // Già pagato / in garanzia
  if (stato === "held" || stato === "charged") {
    return (
      <View style={[styles.card, shadow.card]}>
        <View style={styles.rowTop}><Ionicons name="lock-closed" size={18} color={colors.success} />
          <Text style={styles.heldTitle}>{t("payHeld")}</Text></View>
        <Text style={styles.heldMsg}>{t("payHeldMsg")}</Text>
        {net > 0 ? <Text style={styles.line}>{t("payNet")}: €{net.toFixed(2)}</Text> : null}
        {pl.psp === "simulato" ? (
          <Button testID="release-payment" label={t("payReleaseBtn")} variant="secondary" loading={busy}
            onPress={release} style={{ marginTop: spacing.sm }} />
        ) : null}
      </View>
    );
  }
  if (stato === "released") {
    return (
      <View style={[styles.card, shadow.card]}>
        <View style={styles.rowTop}><Ionicons name="checkmark-done" size={18} color={colors.success} />
          <Text style={styles.heldTitle}>{t("payReleased")}</Text></View>
      </View>
    );
  }

  // Da pagare
  return (
    <View style={[styles.card, shadow.card]}>
      <Text style={styles.title}>{t("payTitle")}</Text>
      <Text style={styles.subtitle}>{t("paySubtitle")}</Text>
      <View style={styles.amountRow}>
        <Text style={styles.amount}>€{total.toFixed(2)}</Text>
        {fee > 0 ? <Text style={styles.breakdown}>{t("payFee")} €{fee.toFixed(2)} · {t("payNet")} €{net.toFixed(2)}</Text> : null}
      </View>
      {checking ? <Text style={styles.processing}>{t("payProcessing")}</Text> : null}
      <Button testID="pay-card" label={`💳 ${t("payCard")}`} loading={busy} onPress={() => startPay("stripe")} style={{ marginTop: spacing.sm }} />
      <Button testID="pay-paypal" label={`🅿️ ${t("payPaypal")}`} variant="secondary" loading={busy} onPress={() => startPay("paypal")} style={{ marginTop: spacing.sm }} />
      <Button testID="pay-wallet" label={`👛 ${t("payWallet")}`} variant="ghost" loading={busy} onPress={() => startPay("wallet")} style={{ marginTop: spacing.sm }} />
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginTop: spacing.md },
  title: { fontSize: fsize.lg, fontWeight: "700", color: colors.onSurface },
  subtitle: { fontSize: fsize.sm, color: colors.onSurfaceTertiary, marginTop: 4 },
  amountRow: { marginTop: spacing.sm, alignItems: "center" },
  amount: { fontSize: 32, fontWeight: "800", color: colors.primary },
  breakdown: { fontSize: fsize.sm, color: colors.onSurfaceTertiary, marginTop: 2 },
  processing: { fontSize: fsize.sm, color: colors.warning, marginTop: spacing.sm, textAlign: "center" },
  rowTop: { flexDirection: "row", alignItems: "center", gap: 8 },
  heldTitle: { fontSize: fsize.base, fontWeight: "700", color: colors.success },
  heldMsg: { fontSize: fsize.sm, color: colors.onSurfaceTertiary, marginTop: 4 },
  line: { fontSize: fsize.sm, color: colors.onSurface, marginTop: 6 },
});
