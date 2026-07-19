import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, Alert, ActivityIndicator, Linking } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useLocalSearchParams, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Button } from "@/src/components/UI";
import PaymentSection from "@/src/components/PaymentSection";
import { TimeField } from "@/src/components/DateTimeField";

const STATE_LABEL: Record<string, string> = {
  pubblicata: "In pubblicazione", in_matching: "Ricerca babysitter", con_proposte: "Babysitter disponibili",
  confermata: "Confermata", in_corso: "In corso", completata: "Completata", recensita: "Recensita", annullata: "Annullata",
};

export default function BabysittingDetail() {
  const { id, new: isNew } = useLocalSearchParams<{ id: string; new?: string }>();
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [r, setR] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState("");
  const [meetSlot, setMeetSlot] = useState("18:00");
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");

  const load = useCallback(async () => { try { setR(await api.bsGetRichiesta(id)); } catch {} }, [id]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const act = async (fn: () => Promise<any>, after?: () => void) => {
    setBusy(true);
    try { await fn(); await load(); after?.(); } catch (e: any) {
      const m = String(e?.message || "");
      if (m.includes("lf_insufficient")) Alert.alert(t("error"), "Borsellino LF insufficiente");
      else if (m.includes("invalid_code")) Alert.alert(t("otpInvalid"));
      else Alert.alert(t("error"));
    } finally { setBusy(false); }
  };

  const emergency = async () => {
    try {
      const res = await api.bsEmergency(id);
      const nums = res.emergency_numbers.map((n: any) => `${n.number}`).join(" · ");
      Alert.alert(t("bsEmergency"), `${t("bsEmergencyNumbers")}: ${nums}\n${t("bsParentContact")}: ${res.parent_contact?.nome || ""} ${res.parent_contact?.phone || ""}`,
        [{ text: "112", onPress: () => Linking.openURL("tel:112") }, { text: "OK" }]);
    } catch { Alert.alert(t("error")); }
  };

  if (!r) return <View style={[styles.container, { alignItems: "center", justifyContent: "center" }]}><ActivityIndicator color={colors.brand} /></View>;
  const isClient = r.role === "client";
  const isProvider = r.role === "provider";
  const cfg = r.config || {};

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="bs-detail-back" onPress={() => router.back()} hitSlop={12}><Ionicons name="arrow-back" size={24} color={colors.onSurface} /></Pressable>
        <Text style={styles.headerTitle}>🧸 {t("babysitting")}</Text>
        <View style={{ width: 24 }} />
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }}>
        {isNew ? <View style={styles.banner}><Ionicons name="checkmark-circle" size={20} color={colors.success} /><Text style={styles.bannerText}>{t("bsRequestSent")}</Text></View> : null}
        <View style={[styles.statusChip, r.stato === "annullata" && { backgroundColor: colors.error }]}><Text style={styles.statusText}>{STATE_LABEL[r.stato] || r.stato}</Text></View>

        <View style={[styles.card, shadow.card]}>
          <Text style={styles.cardH}>{cfg.durata_ore}h · {cfg.n_bambini} {cfg.n_bambini > 1 ? "bambini" : "bambino"}{r.urgente ? " · ⚡" : ""}</Text>
          <Text style={styles.cardSub}>{r.data_ora?.replace("T", " ").slice(0, 16)} → {r.ora_fine?.slice(11, 16)}</Text>
          {cfg.ripetizioni_attiva ? <Text style={styles.cardSub}>📚 {cfg.ripetizioni_ore}h ripetizioni ({cfg.ripetizioni_livello})</Text> : null}
          {r.indirizzo ? <Text style={styles.cardSub}>📍 {r.indirizzo}</Text> : null}
        </View>

        {/* children (full for client & confirmed provider) */}
        {r.bambini_full?.length ? (
          <View style={[styles.card, shadow.card]}>
            <Text style={styles.sectionH}>{t("bsChildren")}</Text>
            {r.bambini_full.map((c: any) => (
              <View key={c.card_id} style={styles.childRow}>
                <Text style={styles.childName}>{c.sesso === "f" ? "👧" : c.sesso === "m" ? "👦" : "🧒"} {c.nome} · {Math.floor(c.eta_mesi / 12)}a</Text>
                {c.allergie ? <Text style={styles.allergy}>⚠️ {c.allergie}</Text> : null}
                {c.note ? <Text style={styles.childNote}>{c.note}</Text> : null}
              </View>))}
          </View>
        ) : r.bambini_generic?.length ? (
          <View style={[styles.card, shadow.card]}>
            <Text style={styles.sectionH}>{t("bsStep_children")}</Text>
            {r.bambini_generic.map((c: any, i: number) => (
              <Text key={i} style={styles.cardSub}>🧒 {c.eta_band_it}{c.esigenza ? ` · ⚠️ ${c.esigenza}` : ""}</Text>))}
          </View>) : null}

        {/* CLIENT: proposals */}
        {isClient && r.stato === "con_proposte" ? (
          <View>
            <Text style={styles.sectionH}>{t("bsProfileFirst")}</Text>
            {(r.proposte || []).map((p: any) => (
              <View key={p.provider_id} style={[styles.propCard, shadow.card]}>
                <View style={styles.propHead}>
                  <View style={styles.propAvatar}><Text style={{ fontSize: 26 }}>🧑‍🍼</Text></View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.propName}>{p.provider_nome}</Text>
                    <Text style={styles.propMeta}>⭐ {p.provider_rating?.toFixed(1) || "—"} · {p.esperienza_anni} {t("bsYears")} {t("bsExperience")}</Text>
                    <View style={styles.badgeRow}>
                      {p.casellario_ok ? <View style={styles.badge}><Text style={styles.badgeText}>✓ {t("bsCertBadge")}</Text></View> : null}
                      {(p.certificazioni || []).includes("primo_soccorso_pediatrico") ? <View style={styles.badge}><Text style={styles.badgeText}>🩹 {t("bsFirstAid")}</Text></View> : null}
                    </View>
                  </View>
                </View>
                {p.presentazione?.perche ? <Text style={styles.propBio}>{`“${p.presentazione.perche}”`}</Text> : null}
                {p.message ? <Text style={styles.propBio}>{p.message}</Text> : null}
                <View style={styles.propFoot}>
                  <Text style={styles.propPrice}>€{p.price?.toFixed(2)}</Text>
                  <Button testID={`choose-${p.provider_id}`} label={t("bsSelectProvider")} loading={busy} onPress={() => act(() => api.bsConfirm(id, p.provider_id))} style={{ height: 44, paddingHorizontal: spacing.xl }} />
                </View>
              </View>))}
          </View>) : null}

        {isClient && (r.stato === "pubblicata" || r.stato === "in_matching") ? (
          <Text style={styles.waiting}>⏳ {t("bsWaitingProviders")}</Text>) : null}

        {/* CLIENT: meet & greet (confermata) */}
        {isClient && r.stato === "confermata" ? (
          <View style={[styles.card, shadow.card]}>
            <Text style={styles.sectionH}>{t("bsMeetGreet")}</Text>
            <Text style={styles.cardSub}>{t("bsMeetGreetSub")}</Text>
            {!r.incontro ? (<>
              <Text style={styles.label}>{t("bsMeetVideo")} — {t("time")}</Text>
              <TimeField testID="meet-slot" value={meetSlot} onChange={setMeetSlot} />
              <Button testID="meet-video" label={t("bsMeetVideo")} icon="videocam" onPress={() => act(() => api.bsSetIncontro(id, "video", `${r.data_ora?.slice(0, 10)}T${meetSlot}:00`))} style={{ marginTop: spacing.md }} />
              <Button testID="meet-person" label={t("bsMeetInPerson")} variant="secondary" onPress={() => act(() => api.bsSetIncontro(id, "persona", ""))} style={{ marginTop: spacing.sm }} />
            </>) : (<>
              {r.incontro.mode === "video" && r.incontro.link ? (
                <Button testID="open-video" label={t("bsOpenVideo")} icon="videocam" onPress={() => Linking.openURL(r.incontro.link)} style={{ marginTop: spacing.md }} />
              ) : <Text style={styles.okLine}>✓ {t("bsMeetInPerson")}</Text>}
              <View style={styles.guaranteeBox}>
                <Text style={styles.guaranteeTitle}>🛡️ {t("bsGuarantee")}</Text>
                <Text style={styles.cardSub}>{t("bsGuaranteeSub")}</Text>
                <Button testID="cancel-refund" label={t("bsCancelRefund")} variant="secondary" onPress={() => act(() => api.bsCancelRefund(id))} style={{ marginTop: spacing.sm, height: 44 }} />
              </View>
            </>)}
            {r.inizio?.provider_at && !r.inizio?.confirmed_at ? (
              <View style={styles.codeBox}>
                <Text style={styles.label}>{t("bsConfirmStart")}</Text>
                <Button testID="confirm-start" label={t("bsConfirmStart")} loading={busy} onPress={() => act(() => api.bsInizioConfirm(id, ""))} style={{ marginTop: spacing.sm }} />
              </View>) : null}
          </View>) : null}

        {/* CLIENT: end confirm (in_corso) */}
        {isClient && r.stato === "in_corso" ? (
          <View style={[styles.card, shadow.card]}>
            <Text style={styles.sectionH}>{t("bsEndActivity")}</Text>
            {r.fine?.provider_at ? (<>
              <Text style={styles.label}>{t("bsEnterEndCode")}</Text>
              <TextInput testID="end-code" style={styles.input} value={code} onChangeText={setCode} keyboardType="number-pad" maxLength={4} placeholder="0000" placeholderTextColor={colors.muted} />
              <Button testID="confirm-end" label={t("bsConfirmEnd")} loading={busy} onPress={() => act(() => api.bsFineConfirm(id, code), () => setCode(""))} style={{ marginTop: spacing.sm }} />
              <Text style={styles.subMini}>{t("bsAutoConfirm")}</Text>
            </>) : <Text style={styles.cardSub}>{t("bsWaitingParent")}...</Text>}
          </View>) : null}

        {/* PROVIDER: double code buttons */}
        {isProvider && r.stato === "confermata" ? (
          r.inizio?.provider_at ? (
            <View style={[styles.card, shadow.card]}><Text style={styles.codeBig}>{r.inizio.code}</Text><Text style={styles.cardSub}>{t("bsWaitingParent")}</Text></View>
          ) : <Button testID="start-activity" label={t("bsStartActivity")} icon="play" loading={busy} onPress={() => act(() => api.bsInizio(id))} />) : null}
        {isProvider && r.stato === "in_corso" ? (
          r.fine?.provider_at ? (
            <View style={[styles.card, shadow.card]}><Text style={styles.codeBig}>{r.fine.code}</Text><Text style={styles.cardSub}>{t("bsWaitingParent")}</Text></View>
          ) : <Button testID="end-activity" label={t("bsEndActivity")} icon="stop" loading={busy} onPress={() => act(() => api.bsFine(id))} />) : null}

        {/* consuntivo */}
        {r.consuntivo ? (
          <View style={[styles.card, shadow.card]}>
            <Text style={styles.sectionH}>{t("bsConsuntivo")}</Text>
            <Text style={styles.cardSub}>{t("bsHoursCertified")}: {r.consuntivo.billable_ore}h</Text>
            {r.consuntivo.extra_ore > 0 ? <Text style={styles.cardSub}>{t("bsExtraHours")}: +{r.consuntivo.extra_ore}h (€{r.consuntivo.extra_importo?.toFixed(2)})</Text> : null}
          </View>) : null}

        {/* CLIENT review */}
        {isClient && r.stato === "completata" ? (
          <View style={[styles.card, shadow.card]}>
            <Text style={styles.sectionH}>{t("leaveReview") || "Recensione"}</Text>
            <View style={styles.stars}>{[1, 2, 3, 4, 5].map((n) => (
              <Pressable key={n} testID={`star-${n}`} onPress={() => setRating(n)}><Ionicons name={n <= rating ? "star" : "star-outline"} size={30} color={colors.warning} /></Pressable>))}</View>
            <TextInput testID="review-comment" style={[styles.input, { minHeight: 60, textAlignVertical: "top" }]} value={comment} onChangeText={setComment} multiline placeholderTextColor={colors.muted} />
            <Button testID="submit-review" label={t("save")} loading={busy} onPress={() => act(() => api.bsReview(id, rating, comment))} style={{ marginTop: spacing.md }} />
          </View>) : null}

        {r.recensione ? <View style={[styles.card, shadow.card]}><Text style={styles.cardSub}>⭐ {r.recensione.rating} — {r.recensione.comment}</Text></View> : null}

        {/* emergency button during active service */}
        {(r.stato === "confermata" || r.stato === "in_corso") ? (
          <Pressable testID="emergency-btn" style={styles.emergency} onPress={emergency}>
            <Ionicons name="warning" size={20} color="#fff" />
            <Text style={styles.emergencyText}>{t("bsEmergency")}</Text>
          </Pressable>) : null}

        {isClient && (r.stato === "pubblicata" || r.stato === "in_matching" || r.stato === "con_proposte") ? (
          <Button testID="cancel-req" label={t("cancel")} variant="secondary" onPress={() => act(() => api.bsCancelRichiesta(id), () => router.back())} style={{ marginTop: spacing.lg }} />) : null}
        {isClient && r.provider_scelto && ["confermata", "in_corso", "completata"].includes(r.stato) ? (
          <PaymentSection r={r} onDone={load} />) : null}
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
  cardH: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  cardSub: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 4 },
  sectionH: { fontSize: fsize.base, fontFamily: font.bold, color: colors.onSurface, marginBottom: spacing.sm },
  childRow: { paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  childName: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  allergy: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.error, marginTop: 2 },
  childNote: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 2 },
  waiting: { fontSize: fsize.base, fontFamily: font.medium, color: colors.muted, textAlign: "center", marginVertical: spacing.lg },
  propCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.md },
  propHead: { flexDirection: "row", gap: spacing.md },
  propAvatar: { width: 52, height: 52, borderRadius: 26, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  propName: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  propMeta: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 2 },
  badgeRow: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 6 },
  badge: { backgroundColor: colors.greenBg, borderRadius: radius.sm, paddingVertical: 3, paddingHorizontal: 8 },
  badgeText: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.success },
  propBio: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurfaceTertiary, fontStyle: "italic", marginTop: spacing.sm },
  propFoot: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: spacing.md },
  propPrice: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.brand },
  label: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary, marginTop: spacing.md, marginBottom: spacing.sm },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  subMini: { fontSize: fsize.sm, color: colors.muted, fontFamily: font.regular, marginTop: spacing.sm },
  okLine: { fontSize: fsize.base, fontFamily: font.medium, color: colors.success, marginTop: spacing.md },
  guaranteeBox: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, marginTop: spacing.md, borderWidth: 1, borderColor: colors.border },
  guaranteeTitle: { fontSize: fsize.base, fontFamily: font.bold, color: colors.onSurface },
  codeBox: { marginTop: spacing.md, borderTopWidth: 1, borderTopColor: colors.divider, paddingTop: spacing.md },
  codeBig: { fontSize: 40, fontFamily: font.bold, color: colors.brand, textAlign: "center", letterSpacing: 8 },
  stars: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.md },
  emergency: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, backgroundColor: colors.error, borderRadius: radius.md, padding: spacing.md, marginTop: spacing.lg },
  emergencyText: { color: "#fff", fontSize: fsize.base, fontFamily: font.bold },
});
