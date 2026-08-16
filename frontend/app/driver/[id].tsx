import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, Alert, ActivityIndicator } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useLocalSearchParams, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLang } from "@/src/context/LanguageContext";
import { useAuth } from "@/src/context/AuthContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Button } from "@/src/components/UI";
import { ClientDeliveryQR, EarnerConfirm } from "@/src/components/DeliveryConfirm";
import StatusTimeline from "@/src/components/StatusTimeline";

const STATE_LABEL: Record<string, string> = {
  pubblicata: "In pubblicazione", in_matching: "Ricerca driver", con_proposte: "Proposte disponibili",
  confermata: "Confermata", in_corso: "In corso", completata: "Completata", recensita: "Recensita", annullata: "Annullata",
};

export default function DriverDetail() {
  const { id, new: isNew } = useLocalSearchParams<{ id: string; new?: string }>();
  const { t } = useLang();
  const { user } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [r, setR] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [meter, setMeter] = useState("");
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");
  const [extraType, setExtraType] = useState("attesa");
  const [extraAmt, setExtraAmt] = useState("");
  const [showPrice, setShowPrice] = useState(false);
  const [propPrice, setPropPrice] = useState("");
  const [propReason, setPropReason] = useState("");

  const RITOCCO = [["bagagli", "Bagagli voluminosi"], ["seggiolino", "Seggiolino richiesto"], ["attesa", "Attesa programmata"], ["pedaggi", "Pedaggi/ZTL"]];

  const load = useCallback(async () => { try { setR(await api.drvGetRichiesta(id)); } catch {} }, [id]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const act = async (fn: () => Promise<any>, after?: () => void) => {
    setBusy(true);
    try { await fn(); await load(); after?.(); } catch (e: any) {
      const m = String(e?.message || "");
      if (m.includes("insufficient_wallet")) Alert.alert("Fondi insufficienti", "Ricarica il portafoglio per confermare: l'importo viene bloccato a garanzia.", [{ text: "Annulla", style: "cancel" }, { text: "Ricarica", onPress: () => router.push("/wallet") }]);
      // BLOCCO 9 (stesso fix di pulizie/[id].tsx: confirm() sul binario
      // 'impresa' rifiuta con questi dettagli se manca l'onboarding Stripe
      // del provider o la carta salvata del cliente).
      else if (m.includes("provider_not_onboarded")) Alert.alert(t("error"), t("providerNotOnboardedMsg"));
      else if (m.includes("client_payment_method_missing")) Alert.alert(t("error"), t("paymentMethodMissingMsg"), [{ text: t("cancel") || "Annulla", style: "cancel" }, { text: t("addCardAction"), onPress: () => router.push("/payments-settings") }]);
      else Alert.alert(t("error"), m.includes("ritocco") ? "Motivazione richiesta per aumentare il prezzo" : "");
    } finally { setBusy(false); }
  };

  if (!r) return <View style={[styles.container, { alignItems: "center", justifyContent: "center" }]}><ActivityIndicator color={colors.brand} /></View>;
  const isClient = r.role === "client";
  const isProvider = r.role === "provider";
  const cfg = r.config || {};
  const isTaxi = cfg.tipo === "taxi";
  const pendingExtras = (r.extra || []).filter((e: any) => e.stato === "pending");

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="drv-detail-back" onPress={() => router.back()} hitSlop={12}><Ionicons name="arrow-back" size={24} color={colors.onSurface} /></Pressable>
        <Text style={styles.headerTitle}>{isTaxi ? "🚕" : "🚘"} {isTaxi ? t("drvTaxi") : t("drvNcc")}</Text>
        <View style={{ width: 24 }} />
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }}>
        {isNew ? <View style={styles.banner}><Ionicons name="checkmark-circle" size={20} color={colors.success} /><Text style={styles.bannerText}>{t("drvRequestSent")}</Text></View> : null}
        <View style={[styles.statusChip, r.stato === "annullata" && { backgroundColor: colors.error }]}><Text style={styles.statusText}>{STATE_LABEL[r.stato] || r.stato}</Text></View>

        {r.stato !== "annullata" ? <StatusTimeline stato={r.stato} paid={r.pagamento?.stato === "settled" || r.pagamento?.stato === "paid" || (r.stato !== "completata" && r.provider_scelto && !isTaxi)} reviewed={!!r.recensione} /> : null}

        {r.conferma_pending && isClient ? <ClientDeliveryQR refId={id as string} onReleased={load} /> : null}
        {r.conferma_pending && isProvider ? <EarnerConfirm refId={id as string} onConfirmed={load} /> : null}

        <View style={[styles.card, shadow.card]}>
          <Text style={styles.route}>📍 {r.partenza?.label}</Text>
          <Text style={styles.routeArrow}>↓</Text>
          <Text style={styles.route}>🏁 {r.destinazione?.label}</Text>
          <Text style={styles.cardSub}>{r.pickup_at?.replace("T", " ").slice(0, 16)}{cfg.flight_number ? ` · ✈️ ${cfg.flight_number}` : ""}</Text>
          <Text style={styles.cardSub}>{cfg.classe} · {cfg.passeggeri}👤 · {cfg.bagagli}🧳 · {cfg.route?.distance_km} km</Text>
          {r.passeggero ? <Text style={styles.cardSub}>🧑 {t("drvWhoTravels")}: {r.passeggero.nome} {r.passeggero.tel}</Text> : null}
          {isProvider ? <Text style={styles.cardSub}>👤 {t("clientLabel")}: {r.cliente_nome || "—"}</Text> : null}
          {r.note ? <Text style={styles.cardSub}>📝 {r.note}</Text> : null}
        </View>

        {/* PROVIDER: accept / counter-price / decline for OPEN requests */}
        {isProvider && ["pubblicata", "in_matching", "con_proposte"].includes(r.stato) ? (() => {
          const mine = (r.proposte || []).find((p: any) => p.provider_id === user?.user_id);
          if (mine) return (
            <View style={[styles.card, shadow.card]}>
              <Text style={styles.sectionH}>⏳ {t("proposalSent")}</Text>
              <Text style={styles.priceLine}>€{Number(mine.prezzo).toFixed(2)}</Text>
              <Text style={styles.cardSub}>{t("drvWaitClientConfirm")}</Text>
              {r.cliente_id ? <Button testID="drv-chat-client" label={`💬 ${t("chat")}`} variant="secondary" onPress={() => router.push(`/chat/${r.cliente_id}`)} style={{ marginTop: spacing.md, height: 44 }} /> : null}
            </View>
          );
          return (
            <View style={[styles.card, shadow.card]}>
              <Text style={styles.sectionH}>{t("drvConfirmTrip")}</Text>
              {!showPrice ? (
                <>
                  <Button testID="drv-accept-trip" label={t("drvConfirmTripBtn")} icon="checkmark-circle" loading={busy} onPress={() => act(() => api.drvPropose(id, { accept: true }))} />
                  <Button testID="drv-modify-price" label={t("drvModifyPrice")} variant="secondary" onPress={() => setShowPrice(true)} style={{ marginTop: spacing.sm, height: 46 }} />
                  {r.cliente_id ? <Button testID="drv-chat-client" label={`💬 ${t("chat")}`} variant="secondary" onPress={() => router.push(`/chat/${r.cliente_id}`)} style={{ marginTop: spacing.sm, height: 46 }} /> : null}
                  <Button testID="drv-decline-trip" label={t("drvReject")} variant="secondary" onPress={() => act(() => api.drvPropose(id, { accept: false }), () => router.back())} style={{ marginTop: spacing.sm, height: 46 }} />
                </>
              ) : (
                <>
                  <Text style={styles.label}>{t("drvNewPrice")} (€)</Text>
                  <TextInput testID="drv-prop-price" style={styles.input} value={propPrice} onChangeText={setPropPrice} keyboardType="numeric" placeholder="0.00" placeholderTextColor={colors.muted} />
                  <Text style={styles.label}>{t("drvPriceReason")}</Text>
                  <View style={styles.segRow2}>
                    {RITOCCO.map(([rid2, lbl]) => (
                      <Pressable key={rid2} testID={`drv-reason-${rid2}`} style={[styles.reasonChip, propReason === rid2 && styles.segOn]} onPress={() => setPropReason(rid2)}>
                        <Text style={[styles.segText, propReason === rid2 && styles.segTextOn]}>{lbl}</Text>
                      </Pressable>))}
                  </View>
                  <Text style={styles.cardSub}>ℹ️ {t("drvCounterPending")}</Text>
                  <Button testID="drv-send-price" label={t("drvSendProposal")} loading={busy} disabled={!propPrice}
                    onPress={() => act(() => api.drvPropose(id, { accept: true, prezzo: Number(String(propPrice).replace(",", ".")), ritocco_motivo: propReason }), () => setShowPrice(false))} style={{ marginTop: spacing.md }} />
                  <Button testID="drv-price-back" label={t("cancel")} variant="secondary" onPress={() => setShowPrice(false)} style={{ marginTop: spacing.sm, height: 44 }} />
                </>
              )}
            </View>
          );
        })() : null}

        {/* CLIENT: proposals */}
        {isClient && r.stato === "con_proposte" ? (
          <View>
            <Text style={styles.sectionH}>{t("drvProposals")}</Text>
            {(r.proposte || []).map((p: any) => (
              <View key={p.provider_id} style={[styles.propCard, shadow.card]}>
                <View style={styles.propHead}>
                  <View style={styles.propAvatar}><Text style={{ fontSize: 24 }}>{isTaxi ? "🚕" : "🚘"}</Text></View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.propName}>{p.provider_nome}</Text>
                    <Text style={styles.propMeta}>⭐ {p.provider_rating?.toFixed(1) || "—"} · {p.vehicle?.modello || p.classe} · {p.vehicle?.targa || ""}</Text>
                    {p.ritocco ? <Text style={styles.ritocco}>+€{p.ritocco.delta} · {p.ritocco.motivo}</Text> : null}
                  </View>
                </View>
                <View style={styles.propFoot}>
                  <View>
                    <Text style={styles.propPrice}>€{p.prezzo?.toFixed(2)}</Text>
                    <Text style={styles.propPriceLbl}>{p.is_estimate ? t("drvTaximeter") : t("drvFirmPrice")}</Text>
                  </View>
                  <Button testID={`drv-choose-${p.provider_id}`} label={t("drvChoose")} loading={busy} onPress={() => act(() => api.drvConfirm(id, p.provider_id))} style={{ height: 44, paddingHorizontal: spacing.xl }} />
                </View>
              </View>))}
          </View>) : null}

        {isClient && (r.stato === "pubblicata" || r.stato === "in_matching") ? (
          <Text style={styles.waiting}>⏳ {t("drvWaitingDrivers")}</Text>) : null}

        {/* Confirmed driver identity */}
        {(r.stato === "confermata" || r.stato === "in_corso") && r.provider_scelto ? (() => {
          const chosen = (r.proposte || []).find((p: any) => p.provider_id === r.provider_scelto);
          return chosen ? (
            <View style={[styles.card, shadow.card]}>
              <Text style={styles.sectionH}>{t("drvVehicle")}</Text>
              <Text style={styles.cardSub}>{chosen.provider_nome} · {chosen.vehicle?.modello || chosen.classe}</Text>
              <Text style={styles.cardSub}>{t("drvPlate")}: {chosen.vehicle?.targa || "—"}</Text>
              <Text style={styles.priceLine}>€{r.prezzo_finale?.toFixed(2)} {isTaxi ? `(${t("drvTaximeter")})` : ""}</Text>
            </View>) : null;
        })() : null}

        {/* CLIENT tracking */}
        {isClient && r.stato === "in_corso" && r.tracking ? (
          <View style={[styles.trackCard]}><Text style={styles.trackText}>🚗 {t("drvDriverEnRoute")}</Text><Text style={styles.cardSub}>{t("drvTracking")}: {r.tracking.lat?.toFixed(4)}, {r.tracking.lng?.toFixed(4)}</Text></View>) : null}

        {/* CLIENT extra approvals */}
        {isClient && pendingExtras.map((e: any) => (
          <View key={e.extra_id} style={[styles.card, shadow.card]}>
            <Text style={styles.sectionH}>{t("drvExtraToApprove")}</Text>
            <Text style={styles.cardSub}>{e.tipo} · €{e.importo?.toFixed(2)} {e.motivo ? `· ${e.motivo}` : ""}</Text>
            <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm }}>
              <Button testID={`drv-extra-ok-${e.extra_id}`} label={t("drvApprove")} loading={busy} onPress={() => act(() => api.drvExtraApprove(id, e.extra_id, true))} style={{ flex: 1, height: 44 }} />
              <Button testID={`drv-extra-no-${e.extra_id}`} label={t("drvReject")} variant="secondary" onPress={() => act(() => api.drvExtraApprove(id, e.extra_id, false))} style={{ flex: 1, height: 44 }} />
            </View>
          </View>))}

        {/* PROVIDER actions */}
        {isProvider && r.stato === "confermata" ? (
          <Button testID="drv-depart" label={t("drvDepart")} icon="car" loading={busy} onPress={() => act(() => api.drvDepart(id))} />) : null}
        {isProvider && r.stato === "in_corso" ? (
          <View style={[styles.card, shadow.card]}>
            <Text style={styles.sectionH}>{t("drvAddExtra")}</Text>
            <View style={styles.segRow}>
              {[["attesa", t("drvExtraWait")], ["fermata", t("drvExtraStop")], ["cambio", t("drvExtraChange")]].map(([id2, lbl]) => (
                <Pressable key={id2} testID={`drv-extype-${id2}`} style={[styles.seg, extraType === id2 && styles.segOn]} onPress={() => setExtraType(id2 as string)}><Text style={[styles.segText, extraType === id2 && styles.segTextOn]}>{lbl}</Text></Pressable>))}
            </View>
            <TextInput testID="drv-extra-amt" style={styles.input} value={extraAmt} onChangeText={setExtraAmt} keyboardType="numeric" placeholder="€" placeholderTextColor={colors.muted} />
            <Button testID="drv-add-extra" label={t("drvAddExtra")} variant="secondary" onPress={() => act(() => api.drvExtra(id, { tipo: extraType, importo: Number(extraAmt) || 0 }), () => setExtraAmt(""))} style={{ marginTop: spacing.sm, height: 44 }} />
            {isTaxi ? (<>
              <Text style={styles.label}>{t("drvMeterAmount")}</Text>
              <TextInput testID="drv-meter" style={styles.input} value={meter} onChangeText={setMeter} keyboardType="numeric" placeholder="€" placeholderTextColor={colors.muted} />
            </>) : null}
            <Button testID="drv-complete" label={t("drvComplete")} loading={busy} onPress={() => act(() => api.drvComplete(id, isTaxi ? Number(meter) : undefined))} style={{ marginTop: spacing.md }} />
            <Button testID="drv-noshow" label={t("drvNoShow")} variant="secondary" onPress={() => act(() => api.drvNoshow(id))} style={{ marginTop: spacing.sm, height: 44 }} />
          </View>) : null}

        {/* totals + settle */}
        {r.stato === "completata" || r.stato === "recensita" ? (
          <View style={[styles.card, shadow.card]}>
            <Text style={styles.sectionH}>{t("drvTotal")}</Text>
            <Text style={styles.priceLine}>€{(r.importo_totale ?? r.prezzo_finale ?? r.importo_dovuto)?.toFixed(2)}</Text>
            {r.extra_totale ? <Text style={styles.cardSub}>{t("drvExtraTotal")}: €{r.extra_totale.toFixed(2)}</Text> : null}
            {r.no_show ? <Text style={styles.cardSub}>⚠️ {t("drvNoShow")}</Text> : null}
            {isClient && (r.pagamento?.stato === "meter_to_settle") ? (
              <Button testID="drv-settle" label={`${t("drvSettle")} €${r.importo_totale?.toFixed(2)}`} loading={busy} onPress={() => act(() => api.drvPay(id))} style={{ marginTop: spacing.md }} />) : null}
            {r.pagamento?.stato === "settled" ? <Text style={styles.okLine}>✓ {t("drvSettled")}</Text> : null}
          </View>) : null}

        {/* CLIENT review */}
        {isClient && r.stato === "completata" ? (
          <View style={[styles.card, shadow.card]}>
            <Text style={styles.sectionH}>{t("leaveReview") || "Recensione"}</Text>
            <View style={styles.stars}>{[1, 2, 3, 4, 5].map((n) => (
              <Pressable key={n} testID={`drv-star-${n}`} onPress={() => setRating(n)}><Ionicons name={n <= rating ? "star" : "star-outline"} size={30} color={colors.warning} /></Pressable>))}</View>
            <TextInput testID="drv-review-comment" style={[styles.input, { minHeight: 56, textAlignVertical: "top" }]} value={comment} onChangeText={setComment} multiline placeholderTextColor={colors.muted} />
            <Button testID="drv-submit-review" label={t("save")} loading={busy} onPress={() => act(() => api.drvReview(id, rating, comment))} style={{ marginTop: spacing.md }} />
          </View>) : null}
        {r.recensione ? <View style={[styles.card, shadow.card]}><Text style={styles.cardSub}>⭐ {r.recensione.rating} — {r.recensione.comment}</Text></View> : null}

        {isClient && (r.stato === "pubblicata" || r.stato === "in_matching" || r.stato === "con_proposte" || r.stato === "confermata") ? (
          <Button testID="drv-cancel" label={t("cancel")} variant="secondary" onPress={() => act(() => api.drvCancelRichiesta(id), () => router.back())} style={{ marginTop: spacing.lg }} />) : null}
        <Text style={styles.cancelNote}>ℹ️ {t("drvCancelRules")}</Text>
        {isClient && r.provider_scelto && false ? (
          <View />) : null}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  headerTitle: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  banner: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.greenBg, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.md },
  bannerText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.success },
  statusChip: { alignSelf: "flex-start", backgroundColor: colors.brand, borderRadius: radius.pill, paddingVertical: 6, paddingHorizontal: spacing.md, marginBottom: spacing.md },
  statusText: { color: "#fff", fontSize: fsize.sm, fontFamily: font.bold },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.md },
  route: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  routeArrow: { fontSize: fsize.base, color: colors.muted, marginLeft: 4, marginVertical: 2 },
  cardSub: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 4 },
  priceLine: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.brand, marginTop: spacing.sm },
  sectionH: { fontSize: fsize.base, fontFamily: font.bold, color: colors.onSurface, marginBottom: spacing.sm },
  waiting: { fontSize: fsize.base, fontFamily: font.medium, color: colors.muted, textAlign: "center", marginVertical: spacing.lg },
  propCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.md },
  propHead: { flexDirection: "row", gap: spacing.md },
  propAvatar: { width: 48, height: 48, borderRadius: 24, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  propName: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  propMeta: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 2 },
  ritocco: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.warning, marginTop: 2 },
  propFoot: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: spacing.md },
  propPrice: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.brand },
  propPriceLbl: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted },
  trackCard: { backgroundColor: colors.brandTertiary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.md },
  trackText: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onBrandTertiary },
  label: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary, marginTop: spacing.md, marginBottom: spacing.sm },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  segRow: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.sm },
  seg: { flex: 1, paddingVertical: spacing.sm, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, alignItems: "center", backgroundColor: colors.surface },
  segOn: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  segText: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.onSurface },
  segTextOn: { color: colors.onBrandTertiary },
  okLine: { fontSize: fsize.base, fontFamily: font.medium, color: colors.success, marginTop: spacing.sm },
  stars: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.md },
  cancelNote: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: spacing.md },
});
