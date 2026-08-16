import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, Alert, ActivityIndicator, Switch } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useLocalSearchParams, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Button } from "@/src/components/UI";
import { ClientDeliveryQR, EarnerConfirm } from "@/src/components/DeliveryConfirm";
import StatusTimeline from "@/src/components/StatusTimeline";

const STATE_LABEL: Record<string, string> = {
  pubblicata: "In pubblicazione", in_matching: "Ricerca artigiano", con_proposte: "Proposte disponibili",
  confermata: "Confermata", preventivo: "Preventivo inviato", in_corso: "In corso",
  completata: "Completata", recensita: "Recensita", annullata: "Annullata",
};
const FASCIA_LABEL: Record<string, string> = {
  mattina: "Mattina (8–13)", pomeriggio: "Pomeriggio (13–18)", sera: "Sera (18–21)",
  immediato: "Immediato (oggi)", serale: "Serale", festivo: "Festivo",
};

export default function ArtigianiDetail() {
  const { id, new: isNew } = useLocalSearchParams<{ id: string; new?: string }>();
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [r, setR] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");
  // preventivo composer
  const [esito, setEsito] = useState("preventivo");
  const [voci, setVoci] = useState<any[]>([{ descrizione: "Manodopera", tipo: "manodopera", qta: "1", prezzo_unit: "" }]);
  const [workDesc, setWorkDesc] = useState("");
  const [scomputoChiamata, setScomputoChiamata] = useState(true);
  const [extraDesc, setExtraDesc] = useState("");
  const [extraAmt, setExtraAmt] = useState("");

  const load = useCallback(async () => { try { setR(await api.artGetRichiesta(id)); } catch {} }, [id]);
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
      else Alert.alert(t("error"), m.includes("expired") ? t("artQuoteExpired") : "");
    } finally { setBusy(false); }
  };

  const submitPreventivo = () => {
    if (esito === "preventivo") {
      const parsed = voci.filter((v) => v.descrizione && Number(v.prezzo_unit) > 0).map((v) => ({ descrizione: v.descrizione, tipo: v.tipo, qta: Number(v.qta) || 1, prezzo_unit: Number(v.prezzo_unit) }));
      if (!parsed.length) { Alert.alert(t("artQuoteLine")); return; }
      act(() => api.artPreventivo(id, { esito, voci: parsed, descrizione_lavoro: workDesc, tempi: "", scomputo_chiamata: scomputoChiamata }));
    } else act(() => api.artPreventivo(id, { esito, voci: [] }));
  };

  const quoteTotal = voci.reduce((s, v) => s + (Number(v.qta) || 1) * (Number(v.prezzo_unit) || 0), 0);

  if (!r) return <View style={[styles.container, { alignItems: "center", justifyContent: "center" }]}><ActivityIndicator color={colors.brand} /></View>;
  const isClient = r.role === "client";
  const isProvider = r.role === "provider";
  const cfg = r.config || {};
  const prev = r.preventivo;
  const pendingExtras = (r.extra || []).filter((e: any) => e.stato === "pending");

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="art-detail-back" onPress={() => router.back()} hitSlop={12}><Ionicons name="arrow-back" size={24} color={colors.onSurface} /></Pressable>
        <Text style={styles.headerTitle}>🛠️ {t("artigiani")}</Text>
        <View style={{ width: 24 }} />
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }}>
        {isNew ? <View style={styles.banner}><Ionicons name="checkmark-circle" size={20} color={colors.success} /><Text style={styles.bannerText}>{t("artRequestSent")}</Text></View> : null}
        <View style={[styles.statusChip, r.stato === "annullata" && { backgroundColor: colors.error }]}><Text style={styles.statusText}>{STATE_LABEL[r.stato] || r.stato}</Text></View>

        {r.stato !== "annullata" ? <StatusTimeline stato={r.stato} paid={["settled", "released", "captured"].includes(r.pagamento_lavoro?.stato) || r.pagato === true} reviewed={!!r.recensione} /> : null}

        {r.conferma_pending && isClient ? <ClientDeliveryQR refId={id as string} onReleased={load} /> : null}
        {r.conferma_pending && isProvider ? <EarnerConfirm refId={id as string} onConfirmed={load} /> : null}

        <View style={[styles.card, shadow.card]}>
          <Text style={styles.cardH}>{cfg.mestiere}{cfg.urgente ? " · ⚡" : ""}</Text>
          <Text style={styles.cardSub}>{cfg.modalita === "paniere" ? (cfg.intervento?.it || "Intervento") : t("artDiagnosi")}</Text>
          {cfg.descrizione ? <Text style={styles.cardSub}>{cfg.descrizione}</Text> : null}
          {(r.data_ora || cfg.fascia_oraria || cfg.fascia_urgenza) ? <Text style={styles.cardSub}>📅 {cfg.urgente ? (FASCIA_LABEL[cfg.fascia_urgenza] || t("artUrgente")) : `${r.data_ora || ""} · ${FASCIA_LABEL[cfg.fascia_oraria] || ""}`}</Text> : null}
          {r.indirizzo ? <Text style={styles.cardSub}>📍 {r.indirizzo}</Text> : null}
        </View>

        {/* CLIENT proposals */}
        {isClient && r.stato === "con_proposte" ? (
          <View>
            <Text style={styles.sectionH}>{t("artProposals")}</Text>
            {(r.proposte || []).map((p: any) => (
              <View key={p.provider_id} style={[styles.propCard, shadow.card]}>
                <Text style={styles.propName}>{p.provider_nome} {p.abilitazione_ok ? "🛡️" : ""}</Text>
                <Text style={styles.propMeta}>⭐ {p.provider_rating?.toFixed(1) || "—"}{p.tariffa_oraria ? ` · ${t("artHourly")} €${p.tariffa_oraria}` : ""}{p.tempi_tipici ? ` · ${p.tempi_tipici}` : ""}</Text>
                <View style={styles.propFoot}>
                  <View><Text style={styles.propPrice}>€{p.prezzo?.toFixed(2)}</Text><Text style={styles.propPriceLbl}>{p.modalita === "diagnosi" ? t("artCallFee") : t("artFixedPrice")}</Text></View>
                  <Button testID={`art-choose-${p.provider_id}`} label={t("artChoose")} loading={busy} onPress={() => act(() => api.artConfirm(id, p.provider_id))} style={{ height: 44, paddingHorizontal: spacing.xl }} />
                </View>
              </View>))}
          </View>) : null}
        {isClient && (r.stato === "pubblicata" || r.stato === "in_matching") ? <Text style={styles.waiting}>⏳ {t("artWaitingProviders")}</Text> : null}

        {/* PROVIDER: compose preventivo (stage 2, after chiamata) */}
        {isProvider && (r.stato === "confermata") && cfg.modalita === "diagnosi" ? (
          <View style={[styles.card, shadow.card]}>
            <Text style={styles.sectionH}>{t("artComposeQuote")}</Text>
            <View style={styles.segRow}>
              {[["preventivo", t("artComposeQuote")], ["risolto_diagnosi", t("artSolvedDiagnosi")], ["non_riparabile", t("artNotRepairable")]].map(([eid, lbl]) => (
                <Pressable key={eid} testID={`art-esito-${eid}`} style={[styles.segMini, esito === eid && styles.segOn]} onPress={() => setEsito(eid as string)}><Text style={[styles.segTextMini, esito === eid && styles.segTextOn]}>{lbl}</Text></Pressable>))}
            </View>
            {esito === "preventivo" ? (<>
              {voci.map((v, i) => (
                <View key={i} style={styles.voceRow}>
                  <TextInput testID={`art-voce-desc-${i}`} style={[styles.input, { flex: 2 }]} value={v.descrizione} onChangeText={(t2) => setVoci(voci.map((x, j) => j === i ? { ...x, descrizione: t2 } : x))} placeholder={t("artLineDesc")} placeholderTextColor={colors.muted} />
                  <TextInput testID={`art-voce-qta-${i}`} style={[styles.input, { flex: 0.6 }]} value={String(v.qta)} onChangeText={(t2) => setVoci(voci.map((x, j) => j === i ? { ...x, qta: t2 } : x))} keyboardType="numeric" placeholder="1" placeholderTextColor={colors.muted} />
                  <TextInput testID={`art-voce-price-${i}`} style={[styles.input, { flex: 0.9 }]} value={String(v.prezzo_unit)} onChangeText={(t2) => setVoci(voci.map((x, j) => j === i ? { ...x, prezzo_unit: t2 } : x))} keyboardType="numeric" placeholder="€" placeholderTextColor={colors.muted} />
                </View>))}
              <Pressable testID="art-add-voce" onPress={() => setVoci([...voci, { descrizione: "", tipo: "materiale", qta: "1", prezzo_unit: "" }])}><Text style={styles.addLine}>{t("artAddLine")}</Text></Pressable>
              <TextInput testID="art-work-desc" style={[styles.input, { minHeight: 50, textAlignVertical: "top", marginTop: spacing.sm }]} value={workDesc} onChangeText={setWorkDesc} multiline placeholder={t("artWorkDesc")} placeholderTextColor={colors.muted} />
              <View style={styles.scomputoRow}>
                <Text style={styles.scomputoLabel}>{t("artScomputoToggle")} (€{(r.chiamata_fee || 0).toFixed(2)})</Text>
                <Switch testID="art-scomputo-toggle" value={scomputoChiamata} onValueChange={setScomputoChiamata} trackColor={{ true: colors.brand, false: colors.borderStrong }} thumbColor="#fff" />
              </View>
              <Text style={styles.quoteTot}>{t("artQuoteTotal")}: €{quoteTotal.toFixed(2)}{scomputoChiamata ? ` · ${t("artScomputo")}: −€${(r.chiamata_fee || 0).toFixed(2)}` : ""}</Text>
            </>) : null}
            <Button testID="art-submit-preventivo" label={esito === "preventivo" ? t("artComposeQuote") : t("artComplete")} loading={busy} onPress={submitPreventivo} style={{ marginTop: spacing.md }} />
          </View>) : null}

        {/* preventivo display */}
        {prev && prev.stato ? (
          <View style={[styles.card, shadow.card]}>
            <Text style={styles.sectionH}>{t("artComposeQuote")} · {prev.stato === "in_attesa" ? t("artQuotePending") : prev.stato}</Text>
            {(prev.voci || []).map((v: any, i: number) => (
              <Text key={i} style={styles.cardSub}>{v.descrizione} — {v.qta} × €{v.prezzo_unit} = €{(v.qta * v.prezzo_unit).toFixed(2)}</Text>))}
            {prev.descrizione_lavoro ? <Text style={styles.cardSub}>{prev.descrizione_lavoro}</Text> : null}
            <Text style={styles.quoteTot}>{t("artQuoteTotal")}: €{prev.totale?.toFixed(2)}</Text>
            <Text style={styles.cardSub}>{t("artScomputo")}: −€{prev.scomputo?.toFixed(2)} → {t("artToPay")}: €{prev.da_pagare?.toFixed(2)}</Text>
            {prev.big_job ? <Text style={styles.warnMini}>⚠️ Lavoro importante — supervisione admin</Text> : null}
            {isClient && prev.stato === "in_attesa" ? (
              <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.md }}>
                <Button testID="art-accept-quote" label={t("artAcceptQuote")} loading={busy} onPress={() => act(() => api.artAcceptPreventivo(id))} style={{ flex: 1, height: 46 }} />
                <Button testID="art-reject-quote" label={t("artRejectQuote")} variant="secondary" onPress={() => act(() => api.artRejectPreventivo(id))} style={{ flex: 1, height: 46 }} />
              </View>) : null}
          </View>) : null}

        {/* CLIENT extra approvals */}
        {isClient && pendingExtras.map((e: any) => (
          <View key={e.extra_id} style={[styles.card, shadow.card]}>
            <Text style={styles.sectionH}>{t("artExtras")}</Text>
            <Text style={styles.cardSub}>{e.descrizione} · €{e.importo?.toFixed(2)}</Text>
            <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm }}>
              <Button testID={`art-extra-ok-${e.extra_id}`} label={t("drvApprove")} loading={busy} onPress={() => act(() => api.artExtraApprove(id, e.extra_id, true))} style={{ flex: 1, height: 44 }} />
              <Button testID={`art-extra-no-${e.extra_id}`} label={t("drvReject")} variant="secondary" onPress={() => act(() => api.artExtraApprove(id, e.extra_id, false))} style={{ flex: 1, height: 44 }} />
            </View>
          </View>))}

        {/* PROVIDER in_corso: extras + complete */}
        {isProvider && r.stato === "in_corso" ? (
          <View style={[styles.card, shadow.card]}>
            <Text style={styles.sectionH}>{t("artAddExtra")}</Text>
            <TextInput testID="art-extra-desc" style={styles.input} value={extraDesc} onChangeText={setExtraDesc} placeholder={t("artLineDesc")} placeholderTextColor={colors.muted} />
            <TextInput testID="art-extra-amt" style={[styles.input, { marginTop: spacing.sm }]} value={extraAmt} onChangeText={setExtraAmt} keyboardType="numeric" placeholder="€" placeholderTextColor={colors.muted} />
            <Button testID="art-add-extra" label={t("artAddExtra")} variant="secondary" onPress={() => act(() => api.artExtra(id, { descrizione: extraDesc, importo: Number(extraAmt) || 0 }), () => { setExtraDesc(""); setExtraAmt(""); })} style={{ marginTop: spacing.sm, height: 44 }} />
            <Button testID="art-complete" label={t("artComplete")} loading={busy} onPress={() => act(() => api.artComplete(id))} style={{ marginTop: spacing.md }} />
          </View>) : null}

        {/* totals + garanzia */}
        {(r.stato === "completata" || r.stato === "recensita") ? (
          <View style={[styles.card, shadow.card]}>
            <Text style={styles.sectionH}>{t("drvTotal")}</Text>
            <Text style={styles.priceLine}>€{(r.importo_totale ?? 0).toFixed(2)}</Text>
            {r.esito ? <Text style={styles.cardSub}>{r.esito}</Text> : null}
            {r.garanzia_fino ? <Text style={styles.garanzia}>🛡️ {t("artGaranziaActive")} {r.garanzia_fino.slice(0, 10)}</Text> : null}
            {isClient && r.garanzia_fino ? <Button testID="art-garanzia" label={t("artOpenGaranzia")} variant="secondary" onPress={() => act(() => api.artGaranzia(id))} style={{ marginTop: spacing.sm, height: 44 }} /> : null}
          </View>) : null}

        {/* CLIENT review */}
        {isClient && r.stato === "completata" ? (
          <View style={[styles.card, shadow.card]}>
            <Text style={styles.sectionH}>{t("leaveReview") || "Recensione"}</Text>
            <View style={styles.stars}>{[1, 2, 3, 4, 5].map((n) => (
              <Pressable key={n} testID={`art-star-${n}`} onPress={() => setRating(n)}><Ionicons name={n <= rating ? "star" : "star-outline"} size={30} color={colors.warning} /></Pressable>))}</View>
            <TextInput testID="art-review-comment" style={[styles.input, { minHeight: 50, textAlignVertical: "top" }]} value={comment} onChangeText={setComment} multiline placeholderTextColor={colors.muted} />
            <Button testID="art-submit-review" label={t("save")} loading={busy} onPress={() => act(() => api.artReview(id, rating, comment))} style={{ marginTop: spacing.md }} />
          </View>) : null}
        {r.recensione ? <View style={[styles.card, shadow.card]}><Text style={styles.cardSub}>⭐ {r.recensione.rating} — {r.recensione.comment}</Text></View> : null}

        {isClient && (r.stato === "pubblicata" || r.stato === "in_matching" || r.stato === "con_proposte") ? (
          <Button testID="art-cancel" label={t("cancel")} variant="secondary" onPress={() => act(() => api.artCancelRichiesta(id), () => router.back())} style={{ marginTop: spacing.lg }} />) : null}
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
  cardH: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface, textTransform: "capitalize" },
  cardSub: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 4 },
  sectionH: { fontSize: fsize.base, fontFamily: font.bold, color: colors.onSurface, marginBottom: spacing.sm },
  priceLine: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.brand, marginTop: spacing.sm },
  waiting: { fontSize: fsize.base, fontFamily: font.medium, color: colors.muted, textAlign: "center", marginVertical: spacing.lg },
  propCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.md },
  propName: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  propMeta: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 2 },
  propFoot: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: spacing.md },
  propPrice: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.brand },
  propPriceLbl: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted },
  segRow: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.md },
  segMini: { flex: 1, paddingVertical: spacing.sm, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, alignItems: "center", backgroundColor: colors.surface },
  segOn: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  segTextMini: { fontSize: 11, fontFamily: font.medium, color: colors.onSurface, textAlign: "center" },
  segTextOn: { color: colors.onBrandTertiary },
  voceRow: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.sm },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface },
  addLine: { fontSize: fsize.base, fontFamily: font.medium, color: colors.brand, marginTop: 4 },
  quoteTot: { fontSize: fsize.base, fontFamily: font.bold, color: colors.onSurface, marginTop: spacing.sm },
  scomputoRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: spacing.sm, gap: spacing.sm },
  scomputoLabel: { flex: 1, fontSize: fsize.sm, fontFamily: font.medium, color: colors.onSurface },
  warnMini: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.warning, marginTop: 4 },
  garanzia: { fontSize: fsize.base, fontFamily: font.medium, color: colors.success, marginTop: spacing.sm },
  stars: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.md },
});
