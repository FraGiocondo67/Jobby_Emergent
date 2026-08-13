// BLOCCO 9 (fix "il servizio non viene salvato" + "manca la gestione dei
// servizi" per le categorie senza verticale dedicata — sarta, pet sitting,
// hospitality, assistenza, tecnico): schermata di dettaglio del flusso "a
// preventivo" (vedi backend/routers/generic_requests.py). Mostra le
// risposte ai FIELD della categoria (service_categories.questions,
// admin-editabili — vedi jobby-admin), le proposte ricevute (lato cliente)
// o permette di inviarne una (lato provider). Stesso modello "nessun
// pagamento in piattaforma" già usato in routers/business.py — l'incasso
// si concorda fuori piattaforma dopo la conferma.
import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, Alert } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Button } from "@/src/components/UI";

export default function GenericRequestDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { t } = useLang();
  const { user } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [r, setR] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [price, setPrice] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    try { setR(await api.getGenericRequest(id as string)); } catch {}
  }, [id]);
  useEffect(() => { load(); }, [load]);

  if (!r) return <View style={styles.container} />;

  const brief = r.brief_answers || {};
  const isClient = r.client_id === user?.id;
  const proposte = brief.proposte || [];
  const myProposal = proposte.find((p: any) => p.provider_id === user?.id);

  const act = async (fn: () => Promise<any>) => {
    setBusy(true);
    try { await fn(); await load(); Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {}); }
    catch { Alert.alert(t("error")); }
    finally { setBusy(false); }
  };

  const openChat = async () => {
    const otherId = isClient ? r.provider_id : r.client_id;
    if (!otherId) return;
    try {
      const convos = await api.conversations();
      const c = convos.find((x: any) => x.other_id === otherId);
      if (c) router.push(`/chat/${c.conversation_id}`);
      else router.push("/(tabs)/chat");
    } catch { router.push("/(tabs)/chat"); }
  };

  const sendProposal = () => {
    const p = Number(price);
    if (!p || p <= 0) { Alert.alert(t("error")); return; }
    act(() => api.proposeGenericRequest(id as string, p, message.trim()));
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="generic-back" onPress={() => router.back()} hitSlop={12}>
          <Ionicons name="arrow-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>{r.category?.icon || "🧩"} {r.category?.name_it || r.title}</Text>
        <View style={{ width: 24 }} />
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }} showsVerticalScrollIndicator={false}>
        <View style={[styles.card, shadow.card]}>
          <View style={styles.pill}><Text style={styles.pillText}>{t(`status_${brief.stato}` as any) || brief.stato}</Text></View>
          {brief.note ? <Text style={styles.summary}>{brief.note}</Text> : null}
          {r.address ? (
            <View style={styles.detRow}><Ionicons name="location-outline" size={16} color={colors.muted} /><Text style={styles.detText}>{r.address}</Text></View>
          ) : null}
          {r.scheduled_at ? (
            <View style={styles.detRow}><Ionicons name="calendar-outline" size={16} color={colors.muted} /><Text style={styles.detText}>{String(r.scheduled_at).replace("T", " ").slice(0, 16)}</Text></View>
          ) : null}
        </View>

        {Object.keys(brief.answers || {}).length > 0 ? (
          <View style={[styles.card, shadow.card]}>
            <Text style={styles.sectionLabel}>{t("yourAnswers")}</Text>
            {(r.category?.questions || []).map((q: any) => {
              const a = brief.answers?.[q.id];
              if (a === undefined || a === null || (Array.isArray(a) && a.length === 0)) return null;
              return (
                <Text key={q.id} style={styles.answerRow}>
                  <Text style={styles.answerLabel}>{q.text}: </Text>
                  {Array.isArray(a) ? a.join(", ") : String(a)}
                </Text>
              );
            })}
          </View>
        ) : null}

        {isClient && brief.stato === "pubblicata" ? (
          <>
            <Text style={styles.sectionLabel}>{t("proposals")}</Text>
            {proposte.length === 0 ? (
              <View style={styles.waiting}><Ionicons name="hourglass-outline" size={22} color={colors.muted} /><Text style={styles.waitingText}>{t("noProposalsYet")}</Text></View>
            ) : proposte.map((p: any) => (
              <View key={p.provider_id} style={[styles.propCard, shadow.card]} testID={`gen-prop-${p.provider_id}`}>
                <View style={styles.rowBetween}>
                  <Text style={styles.propPrice}>€{Number(p.price).toFixed(2)}</Text>
                </View>
                {p.message ? <Text style={styles.propMsg}>"{p.message}"</Text> : null}
                <Button testID={`accept-prop-${p.provider_id}`} label={t("acceptProposal")} loading={busy} onPress={() => act(() => api.confirmGenericRequest(id as string, p.provider_id))} style={{ marginTop: spacing.sm }} />
              </View>
            ))}
          </>
        ) : null}

        {!isClient && brief.stato === "pubblicata" ? (
          <View style={[styles.card, shadow.card]}>
            {myProposal ? (
              <Text style={styles.propMeta}>{t("proposalSent")} · €{Number(myProposal.price).toFixed(2)}</Text>
            ) : (
              <>
                <Text style={styles.sectionLabel}>{t("yourProposal")}</Text>
                <TextInput testID="gen-price-input" style={styles.input} value={price} onChangeText={setPrice} keyboardType="numeric" placeholder="€" placeholderTextColor={colors.muted} />
                <TextInput testID="gen-msg-input" style={[styles.input, { marginTop: spacing.sm }]} value={message} onChangeText={setMessage} placeholder={t("messageOptional")} placeholderTextColor={colors.muted} multiline />
                <Button testID="gen-send-proposal" label={t("sendProposal")} loading={busy} onPress={sendProposal} style={{ marginTop: spacing.md }} />
              </>
            )}
          </View>
        ) : null}

        {brief.stato === "confermata" ? (
          <View style={[styles.card, shadow.card]}>
            <Text style={styles.sectionLabel}>{t("confirmed")}</Text>
            {r.price_agreed ? <Text style={styles.propPrice}>€{Number(r.price_agreed).toFixed(2)}</Text> : null}
            <Pressable testID="gen-chat" style={styles.chatBtn} onPress={openChat}>
              <Text style={styles.chatBtnText}>💬 {t("chat")}</Text>
            </Pressable>
            <Button testID="gen-complete" label={t("markCompleted")} variant="secondary" loading={busy} onPress={() => act(() => api.completeGenericRequest(id as string))} style={{ marginTop: spacing.sm }} />
          </View>
        ) : null}

        {isClient && brief.stato === "pubblicata" ? (
          <Pressable testID="gen-cancel" style={styles.cancelBtn} onPress={() => act(() => api.cancelGenericRequest(id as string))} disabled={busy}>
            <Text style={styles.cancelText}>✕ {t("cancelRequest")}</Text>
          </Pressable>
        ) : null}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.divider },
  headerTitle: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.lg, gap: spacing.sm },
  rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  pill: { alignSelf: "flex-start", paddingHorizontal: spacing.md, paddingVertical: 4, borderRadius: radius.pill, backgroundColor: colors.brandTertiary },
  pillText: { fontSize: fsize.sm, fontFamily: font.bold, color: colors.brand },
  summary: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  detRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  detText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurfaceTertiary },
  sectionLabel: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: spacing.xs },
  answerRow: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface, marginTop: 2 },
  answerLabel: { fontFamily: font.medium, color: colors.onSurfaceTertiary },
  waiting: { alignItems: "center", gap: spacing.sm, padding: spacing.xl },
  waitingText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted },
  propCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.md, gap: 4 },
  propPrice: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.brand },
  propMeta: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted },
  propMsg: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurfaceTertiary, fontStyle: "italic" },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface },
  chatBtn: { alignSelf: "flex-start", marginTop: spacing.sm, paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brand },
  chatBtnText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.brand },
  cancelBtn: { alignSelf: "center", marginTop: spacing.md, paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.error },
  cancelText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.error },
});
