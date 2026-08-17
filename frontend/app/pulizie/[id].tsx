import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, Alert, Modal } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Button } from "@/src/components/UI";
import { ClientDeliveryQR, EarnerConfirm } from "@/src/components/DeliveryConfirm";
import StatusTimeline from "@/src/components/StatusTimeline";

const STATE_META: Record<string, { color: string; bg: string }> = {
  pubblicata: { color: "#E8912A", bg: "#FDF0DD" }, in_matching: { color: "#6D3BEA", bg: "#EEE7FD" },
  con_proposte: { color: "#0E1F3D", bg: "#E1E6F0" }, confermata: { color: "#1E9E5B", bg: "#E4F6EC" },
  in_corso: { color: "#1E9E5B", bg: "#E4F6EC" }, completata: { color: "#1E9E5B", bg: "#E4F6EC" },
  recensita: { color: "#8A8781", bg: "#EDEBE6" }, scaduta: { color: "#DE4B3F", bg: "#FBE0DD" },
  annullata: { color: "#DE4B3F", bg: "#FBE0DD" },
};

export default function RichiestaDetail() {
  const { id, new: isNew } = useLocalSearchParams<{ id: string; new?: string }>();
  const { t, lang } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [r, setR] = useState<any>(null);
  const [bors, setBors] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");
  // provider propose modal
  const [propModal, setPropModal] = useState(false);
  const [varReason, setVarReason] = useState<string | null>(null);
  const [varPrice, setVarPrice] = useState("");
  const [propMsg, setPropMsg] = useState("");
  const [reasons, setReasons] = useState<any[]>([]);
  // Spec 4 — provider client-rating + reply
  const [cRating, setCRating] = useState(5);
  const [cFlags, setCFlags] = useState<string[]>([]);
  const [cNote, setCNote] = useState("");
  const [reply, setReply] = useState("");

  const load = useCallback(async () => {
    try { const d = await api.getRichiesta(id as string); setR(d);
      if (d.role === "client" && d.binario === "persona_lf") { try { setBors(await api.lfBorsellino()); } catch {} }
    } catch {}
  }, [id]);
  useEffect(() => { load(); }, [load]);

  if (!r) return <View style={styles.container} />;
  const isClient = r.role === "client";
  const meta = STATE_META[r.stato] || STATE_META.pubblicata;
  const c = r.config || {};

  const confirmProvider = async (pid: string, prop: any) => {
    if (r.binario === "persona_lf" && bors && (prop.breakdown?.lf_nominale || prop.price) > bors.borsellino) {
      Alert.alert(t("lfInsufficient"), t("lfTopupNeeded")); return;
    }
    setBusy(true);
    try { await api.confirmRichiesta(id as string, pid); await load(); Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {}); }
    catch (e: any) {
      const m = String(e?.message);
      if (m.includes("lf_insufficient")) Alert.alert(t("lfInsufficient"), t("lfTopupNeeded"));
      else if (m.includes("insufficient_wallet")) Alert.alert("Fondi insufficienti", "Ricarica il portafoglio per confermare: l'importo viene bloccato a garanzia.", [{ text: "Annulla", style: "cancel" }, { text: "Ricarica", onPress: () => router.push("/wallet") }]);
      // BLOCCO 9 (fix "il cliente vede il prezzo proposto ma non può
      // confermare"): per il binario 'impresa' (Stripe Connect reale)
      // confirm() rifiuta con questi due dettagli se il provider non ha
      // completato l'onboarding pagamenti o il cliente non ha una carta
      // salvata — prima finivano entrambi nel generico t("error") senza
      // dire perché, quindi sembrava che "confermare" non facesse nulla.
      else if (m.includes("provider_not_onboarded")) Alert.alert(t("error"), t("providerNotOnboardedMsg"));
      else if (m.includes("client_payment_method_missing")) Alert.alert(t("error"), t("paymentMethodMissingMsg"), [{ text: t("cancel") || "Annulla", style: "cancel" }, { text: t("addCardAction"), onPress: () => router.push("/payments-settings") }]);
      else Alert.alert(t("error"));
    }
    finally { setBusy(false); }
  };
  const topup = async () => { setBusy(true); try { await api.lfTopup(100); setBors(await api.lfBorsellino()); Alert.alert(t("lfTopupDone")); } catch {} finally { setBusy(false); } };
  const act = async (fn: () => Promise<any>) => { setBusy(true); try { await fn(); await load(); } catch { Alert.alert(t("error")); } finally { setBusy(false); } };

  const doCancel = async () => {
    let msg = t("cancelRequest");
    try {
      const p = await api.cancelPolicy(id as string);
      const tierTxt = p.tier === "free" ? t("s4TierFree") : p.tier === "fee_only" ? t("s4TierFeeOnly") : p.tier === "lf_late" ? t("s4TierLfLate") : t("s4TierLate");
      msg = `${tierTxt}${p.free_until ? `\n\n${t("s4FreeUntil")} ${p.free_until}` : ""}`;
    } catch {}
    Alert.alert(t("s4CancelTitle"), msg, [
      { text: t("cancel") || "Annulla", style: "cancel" },
      { text: "OK", style: "destructive", onPress: () => act(() => api.cancelRichiesta(id as string, "")) },
    ]);
  };
  const doNoShow = (against: "client" | "provider") => act(async () => { await api.reportNoShow(id as string, against); Alert.alert(t("s4NoShow"), t("s4NoShowReported")); });
  const toggleFlag = (f: string) => setCFlags((p) => p.includes(f) ? p.filter((x) => x !== f) : [...p, f]);

  const openPropose = async () => { try { const m = await api.pulizieConfig(); setReasons(m.variation_reasons || []); } catch {} setVarReason(null); setVarPrice(""); setPropMsg(""); setPropModal(true); };
  const sendPropose = async (withVar: boolean) => {
    setBusy(true);
    try {
      await api.proposeRichiesta(id as string, { accept: true, message: propMsg,
        variation_reason: withVar ? varReason : null, variation_price: withVar && varPrice ? Number(varPrice) : null });
      setPropModal(false); await load();
    } catch { Alert.alert(t("error")); } finally { setBusy(false); }
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="richiesta-back" onPress={() => router.replace("/(tabs)")} hitSlop={12}><Ionicons name={isNew ? "close" : "arrow-back"} size={24} color={colors.onSurface} /></Pressable>
        <Text style={styles.headerTitle}>🧹 {t("cleaning")}</Text>
        <View style={{ width: 24 }} />
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }} showsVerticalScrollIndicator={false}>
        {isNew ? <View style={styles.okBanner}><Ionicons name="checkmark-circle" size={26} color={colors.success} /><Text style={styles.okText}>{t("requestPublished")}</Text></View> : null}

        {r.stato !== "annullata" ? <StatusTimeline stato={r.stato} paid={["settled", "released", "captured"].includes(r.pagamento_lavoro?.stato) || r.pagato === true} reviewed={!!r.recensione} /> : null}

        {r.conferma_pending && isClient ? <ClientDeliveryQR refId={id as string} onReleased={load} /> : null}
        {r.conferma_pending && !isClient ? <EarnerConfirm refId={id as string} onConfirmed={load} /> : null}

        <View style={[styles.card, shadow.card]}>
          <View style={styles.rowBetween}>
            <View style={[styles.pill, { backgroundColor: meta.bg }]}><Text style={[styles.pillText, { color: meta.color }]}>{t(`status_${r.stato}` as any)}</Text></View>
            <Text style={styles.track}>{r.binario === "impresa" ? t("trackImpresa") : t("trackLF")}</Text>
          </View>
          <Text style={styles.summary}>{t(`tipo_${c.tipo_pulizia}` as any) || c.tipo_pulizia} · {c.mq_band?.replace("_", "–")} m² · {c.durata_ore}h</Text>
          {c.extra?.length ? <Text style={styles.summarySub}>{t("extra")}: {c.extra.join(", ")}</Text> : null}
          {r.indirizzo ? <View style={styles.detRow}><Ionicons name="location-outline" size={16} color={colors.muted} /><Text style={styles.detText}>{r.indirizzo}</Text></View> : null}
          <View style={styles.detRow}><Ionicons name="calendar-outline" size={16} color={colors.muted} /><Text style={styles.detText}>{r.data_ora} · {t(`flex_${r.flessibilita}` as any) || r.flessibilita}</Text></View>
        </View>

        {/* LF borsellino (client) */}
        {isClient && r.binario === "persona_lf" && bors ? (
          <View style={[styles.card, shadow.card]}>
            <Text style={styles.sectionLabel}>{t("lfBorsellino")}</Text>
            <Text style={styles.borsVal}>€{(bors.borsellino || 0).toFixed(2)}</Text>
            {bors.alert ? <Text style={styles.borsAlert}>⚠️ {t("lfCeilingAlert")}</Text> : null}
            <Text style={styles.borsSub}>{t("lfYearUsed")}: €{(bors.year_total || 0).toFixed(2)} / {bors.ceiling_eur} · {bors.year_hours}h / {bors.ceiling_hours}h</Text>
            <Pressable testID="lf-topup" style={styles.topupBtn} onPress={topup} disabled={busy}><Text style={styles.topupText}>+ €100 {t("lfTopup")}</Text></Pressable>
          </View>
        ) : null}

        {/* CLIENT: proposals */}
        {isClient && r.stato === "con_proposte" ? (
          <>
            <Text style={styles.sectionLabel}>{t("proposals")}</Text>
            {(r.proposte || []).map((p: any) => (
              <View key={p.provider_id} style={[styles.propCard, shadow.card]} testID={`prop-${p.provider_id}`}>
                <View style={styles.rowBetween}>
                  <Text style={styles.propName}>{p.provider_nome}</Text>
                  <Text style={styles.propPrice}>€{(p.price || 0).toFixed(2)}</Text>
                </View>
                <Text style={styles.propMeta}>⭐ {(p.provider_rating || 0).toFixed(1)} · Trust {Math.round(p.provider_trust || 0)}</Text>
                {p.variation_reason ? <Text style={styles.propVar}>{t("priceVaried")}: {t(`vr_${p.variation_reason}` as any) || p.variation_reason}</Text> : null}
                {p.message ? <Text style={styles.propMsg}>“{p.message}”</Text> : null}
                <Button testID={`choose-${p.provider_id}`} label={t("chooseProvider")} loading={busy} onPress={() => confirmProvider(p.provider_id, p)} style={{ marginTop: spacing.sm }} />
              </View>
            ))}
          </>
        ) : null}

        {isClient && ["pubblicata", "in_matching"].includes(r.stato) ? (
          <View style={styles.waiting}><Ionicons name="hourglass-outline" size={22} color={colors.muted} /><Text style={styles.waitingText}>{t("waitingProposals")}</Text></View>
        ) : null}

        {/* Confirmed / in progress */}
        {isClient && ["confermata", "in_corso"].includes(r.stato) ? (
          <View style={[styles.card, shadow.card]}>
            <Text style={styles.sectionLabel}>{t("confirmed")}</Text>
            <Text style={styles.propPrice}>€{(r.prezzo_finale || 0).toFixed(2)}</Text>
            {r.stato === "confermata" ? <Button testID="start-btn" label={t("startService")} loading={busy} onPress={() => act(() => api.startRichiesta(id as string))} style={{ marginTop: spacing.sm }} /> : null}
            <Button testID="complete-btn" label={t("complete")} variant="secondary" loading={busy} onPress={() => act(() => api.completeRichiesta(id as string))} style={{ marginTop: spacing.sm }} />
            <Pressable testID="client-cancel-confirmed" style={styles.cancelBtn} onPress={doCancel} disabled={busy}><Text style={styles.cancelText}>✕ {t("s4CancelTitle")}</Text></Pressable>
            <Pressable testID="client-noshow" style={styles.linkBtn} onPress={() => doNoShow("provider")} disabled={busy}><Text style={styles.linkBtnText}>⚠️ {t("s4NoShow")}</Text></Pressable>
          </View>
        ) : null}

        {/* Pagamento gestito via escrow-portafoglio (bloccato alla conferma). */}

        {/* Review */}
        {isClient && r.stato === "completata" ? (
          <View style={[styles.card, shadow.card]}>
            <Text style={styles.sectionLabel}>{t("leaveReview")}</Text>
            <View style={styles.stars}>{[1, 2, 3, 4, 5].map((i) => (
              <Pressable key={i} testID={`star-${i}`} onPress={() => setRating(i)} hitSlop={6}><Ionicons name={i <= rating ? "star" : "star-outline"} size={32} color={colors.warning} /></Pressable>))}</View>
            <TextInput testID="review-input" style={styles.input} value={comment} onChangeText={setComment} placeholder="..." placeholderTextColor={colors.muted} multiline />
            <Button testID="submit-review" label={t("submitReview")} loading={busy} onPress={() => act(() => api.reviewRichiesta(id as string, rating, comment))} />
          </View>
        ) : null}
        {r.stato === "recensita" ? <View style={styles.okBanner}><Ionicons name="checkmark-done" size={20} color={colors.success} /><Text style={styles.okText}>{t("done")}</Text></View> : null}

        {/* PROVIDER view */}
        {!isClient ? (
          <View style={[styles.card, shadow.card]}>
            <Text style={styles.sectionLabel}>{t("yourProposal")}</Text>
            {r.proposte?.find((p: any) => p.provider_nome) && r.provider_scelto ? (
              <>
                <Text style={styles.propMeta}>{t("confirmed")}</Text>
                {/* BLOCCO 10: segnalato dall'utente — una volta confermata la
                    richiesta il professionista non vedeva più alcun prezzo
                    (e il cliente vedeva un €0.00 fisso, r.prezzo_finale non
                    era mai valorizzato dal backend). Vedi _richiesta_out(). */}
                {typeof r.prezzo_finale === "number" ? <Text style={styles.propPrice}>€{r.prezzo_finale.toFixed(2)}</Text> : null}
              </>
            ) : r.proposte?.length ? (
              <Text style={styles.propMeta}>{t("proposalSent")} · €{r.proposte[r.proposte.length - 1].price?.toFixed(2)}</Text>
            ) : (
              <>
                {/* BLOCCO 10: segnalato dall'utente — il provider doveva
                    accettare "al prezzo di listino" alla cieca, senza vedere
                    alcun prezzo. Mostriamo qui l'anteprima calcolata dal
                    backend (get_richiesta -> prezzo_listino) con lo stesso
                    listino/formula che userebbe propose(). */}
                {typeof r.prezzo_listino === "number" ? (
                  <View style={styles.listinoPreview}>
                    <Text style={styles.propMeta}>{t("listinoPricePreview")}</Text>
                    <Text style={styles.propPrice}>€{r.prezzo_listino.toFixed(2)}</Text>
                  </View>
                ) : null}
                <Button testID="accept-btn" label={t("acceptRequest")} loading={busy} onPress={() => act(() => api.proposeRichiesta(id as string, { accept: true }))} />
                <Pressable testID="propose-var-btn" style={styles.varLink} onPress={openPropose}><Text style={styles.varLinkText}>{t("proposeVariation")}</Text></Pressable>
                <Pressable testID="decline-btn" style={styles.declineLink} onPress={() => act(() => api.proposeRichiesta(id as string, { accept: false }))}><Text style={styles.declineText}>{t("decline")}</Text></Pressable>
              </>
            )}
          </View>
        ) : null}

        {/* Spec 4 — provider actions on confirmed/completed */}
        {!isClient && r.provider_scelto ? (
          <View style={[styles.card, shadow.card]}>
            {["confermata", "in_corso"].includes(r.stato) ? (
              <>
                <Pressable testID="provider-noshow" style={styles.linkBtn} onPress={() => doNoShow("client")} disabled={busy}><Text style={styles.linkBtnText}>⚠️ {t("s4NoShow")}</Text></Pressable>
                <Pressable testID="provider-cancel" style={styles.cancelBtn} onPress={() => Alert.alert(t("s4ProviderCancel"), "", [{ text: t("cancel") || "Annulla", style: "cancel" }, { text: "OK", style: "destructive", onPress: () => act(() => api.providerCancel(id as string, "")) }])} disabled={busy}><Text style={styles.cancelText}>✕ {t("s4ProviderCancel")}</Text></Pressable>
              </>
            ) : null}
            {["completata", "recensita"].includes(r.stato) && !r.valutazione_cliente ? (
              <>
                <Text style={styles.sectionLabel}>{t("s4RateClient")}</Text>
                <View style={styles.stars}>{[1, 2, 3, 4, 5].map((i) => (
                  <Pressable key={i} testID={`crate-${i}`} onPress={() => setCRating(i)} hitSlop={6}><Ionicons name={i <= cRating ? "star" : "star-outline"} size={28} color={colors.warning} /></Pressable>))}</View>
                {[["condizioni_diverse", t("s4FlagConditions")], ["richieste_fuori_accordo", t("s4FlagOutside")], ["comportamento_irrispettoso", t("s4FlagDisrespect")]].map(([id2, label]) => (
                  <Pressable key={id2} testID={`cflag-${id2}`} style={styles.flagRow} onPress={() => toggleFlag(id2)}>
                    <Ionicons name={cFlags.includes(id2) ? "checkbox" : "square-outline"} size={20} color={colors.brand} /><Text style={styles.flagTxt}>{label}</Text>
                  </Pressable>))}
                <TextInput testID="cnote-input" style={styles.input} value={cNote} onChangeText={setCNote} placeholder="..." placeholderTextColor={colors.muted} multiline />
                <Button testID="submit-crate" label={t("s4RateClient")} loading={busy} onPress={() => act(() => api.rateClient(id as string, cRating, cFlags, cNote))} />
              </>
            ) : null}
            {r.stato === "recensita" && r.recensione && !r.recensione.reply ? (
              <>
                <Text style={styles.sectionLabel}>{t("s4ReplyReview")}</Text>
                <TextInput testID="reply-input" style={styles.input} value={reply} onChangeText={setReply} placeholder={t("s4Reply")} placeholderTextColor={colors.muted} multiline />
                <Button testID="submit-reply" label={t("s4Send")} loading={busy} onPress={() => act(() => api.replyReview(id as string, reply))} />
              </>
            ) : null}
          </View>
        ) : null}
        {isClient && ["pubblicata", "in_matching", "con_proposte"].includes(r.stato) ? (
          <Pressable testID="cancel-richiesta" style={styles.cancelBtn} onPress={doCancel} disabled={busy}><Text style={styles.cancelText}>✕ {t("cancelRequest")}</Text></Pressable>
        ) : null}
      </ScrollView>

      {/* provider variation modal */}
      <Modal visible={propModal} transparent animationType="slide" onRequestClose={() => setPropModal(false)}>
        <View style={styles.modalBackdrop}><View style={styles.modalSheet}>
          <View style={styles.rowBetween}><Text style={styles.modalTitle}>{t("proposeVariation")}</Text><Pressable onPress={() => setPropModal(false)} hitSlop={10}><Ionicons name="close" size={24} color={colors.onSurface} /></Pressable></View>
          <Text style={styles.sectionLabel}>{t("variationReason")}</Text>
          {reasons.map((rr) => (
            <Pressable key={rr.id} testID={`vr-${rr.id}`} style={[styles.rowOpt, varReason === rr.id && styles.optOn]} onPress={() => setVarReason(rr.id)}>
              <Text style={[styles.optText, varReason === rr.id && { color: colors.onBrandTertiary, fontFamily: font.medium }]}>{rr[lang]}</Text>
              {varReason === rr.id ? <Ionicons name="checkmark-circle" size={20} color={colors.brand} /> : null}
            </Pressable>))}
          <Text style={styles.sectionLabel}>{t("newPrice")}</Text>
          <TextInput testID="var-price" style={styles.input} value={varPrice} onChangeText={setVarPrice} keyboardType="numeric" placeholder="€" placeholderTextColor={colors.muted} />
          <TextInput testID="prop-msg" style={[styles.input, { marginTop: spacing.sm }]} value={propMsg} onChangeText={setPropMsg} placeholder={t("messageOptional")} placeholderTextColor={colors.muted} />
          <Button testID="send-variation" label={t("sendProposal")} loading={busy} onPress={() => sendPropose(true)} style={{ marginTop: spacing.md }} disabled={!varReason || !varPrice} />
        </View></View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.divider },
  headerTitle: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  okBanner: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: "#E8F0EA", borderRadius: radius.lg, padding: spacing.md, marginBottom: spacing.lg },
  okText: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.success },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.lg, gap: spacing.sm },
  rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  pill: { paddingHorizontal: spacing.md, paddingVertical: 4, borderRadius: radius.pill },
  pillText: { fontSize: fsize.sm, fontFamily: font.bold },
  track: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.muted },
  summary: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  summarySub: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted },
  detRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  detText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurfaceTertiary },
  sectionLabel: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.5 },
  borsVal: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.brand },
  borsAlert: { fontSize: fsize.base, fontFamily: font.medium, color: colors.warning },
  borsSub: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted },
  topupBtn: { alignSelf: "flex-start", paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brand, marginTop: spacing.sm },
  topupText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.brand },
  propCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.md, gap: 4 },
  propName: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  propPrice: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.brand },
  propMeta: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted },
  listinoPreview: { alignItems: "center", marginBottom: spacing.md },
  propVar: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.warning },
  propMsg: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurfaceTertiary, fontStyle: "italic" },
  waiting: { alignItems: "center", gap: spacing.sm, padding: spacing.xl },
  waitingText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted },
  stars: { flexDirection: "row", justifyContent: "center", gap: spacing.sm, marginVertical: spacing.sm },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface },
  varLink: { alignSelf: "center", marginTop: spacing.md }, varLinkText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.brand },
  declineLink: { alignSelf: "center", marginTop: spacing.md }, declineText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.error },
  cancelBtn: { alignSelf: "center", marginTop: spacing.md, paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.error },
  cancelText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.error },
  linkBtn: { alignSelf: "center", marginTop: spacing.sm, paddingVertical: spacing.xs },
  linkBtnText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.warning },
  flagRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: spacing.sm },
  flagTxt: { flex: 1, fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface },
  rowOpt: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: spacing.md, paddingHorizontal: spacing.lg, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, marginBottom: spacing.sm },
  optOn: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  optText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface },
  modalBackdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "flex-end" },
  modalSheet: { backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.lg, maxHeight: "85%" },
  modalTitle: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.onSurface },
});
