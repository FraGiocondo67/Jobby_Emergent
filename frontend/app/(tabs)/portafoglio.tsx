import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl, ActivityIndicator, Modal, TextInput, Switch, Alert } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";

function Bar({ pct, warn }: { pct: number; warn?: boolean }) {
  return (
    <View style={styles.barTrack}>
      <View style={[styles.barFill, { width: `${Math.min(100, Math.round((pct || 0) * 100))}%`, backgroundColor: warn ? colors.warning : colors.brand }]} />
    </View>
  );
}

export default function PortafoglioTab() {
  const { user } = useAuth();
  const isProvider = user?.role === "provider" || user?.role === "business";
  return isProvider ? <ProviderDashboard /> : <ClientWallet />;
}

// ------------------ CLIENT ------------------
function ClientWallet() {
  const { user } = useAuth();
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [d, setD] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [extOpen, setExtOpen] = useState(false);
  const [extAmount, setExtAmount] = useState("");
  const [extName, setExtName] = useState("");

  const load = useCallback(async () => {
    try { setD(await api.walletDashboard()); } catch {} finally { setLoading(false); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const saveExternal = async () => {
    const amt = parseFloat(extAmount.replace(",", "."));
    if (!amt || amt <= 0) { Alert.alert(t("wExternalSave"), "€ > 0"); return; }
    try { await api.addExternalUsage(amt, extName.trim()); setExtOpen(false); setExtAmount(""); setExtName(""); load(); } catch {}
  };

  if (loading) return <View style={styles.center}><ActivityIndicator color={colors.brand} /></View>;
  const b = d?.borsellino || {}; const lim = d?.limiti || {}; const att = d?.attivita || {}; const fisc = d?.recupero_fiscale || {};
  const pm: any = d?.impresa?.payment_method;
  const pmLabel = (pm && typeof pm === "object")
    ? `${pm.card_brand || "Carta"} •••• ${pm.card_last4 || ""}`.trim()
    : (pm || d?.impresa?.paypal_email || t("wNoData"));

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingTop: insets.top + spacing.md, paddingBottom: insets.bottom + 160 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
        showsVerticalScrollIndicator={false}>
        <Text style={styles.h1}>{t("walletTitle")}</Text>

        {(user?.bonus_credit || 0) > 0 ? (
          <View style={[styles.bonusCard, shadow.card]}>
            <Ionicons name="gift" size={22} color="#fff" />
            <View style={{ flex: 1 }}>
              <Text style={styles.bonusLbl}>{t("bonusCredit")}</Text>
              <Text style={styles.bonusVal}>€{(user?.bonus_credit || 0).toFixed(2)}</Text>
              <View style={styles.bonusNote}>
                <Ionicons name="information-circle" size={14} color="#fff" />
                <Text style={styles.bonusNoteText}>{t("bonusInAppOnly")}</Text>
              </View>
            </View>
          </View>
        ) : null}

        {/* Block 1 — Borsellino / Impresa */}
        {d?.show_borsellino ? (
          <View style={[styles.card, shadow.card]}>
            <Text style={styles.blockTitle}>👛 {t("wBorsellinoTitle")}</Text>
            <View style={styles.numRow}>
              <View style={styles.numCol}><Text style={styles.numSmall}>€{(b.caricato || 0).toFixed(2)}</Text><Text style={styles.numLbl}>{t("wCaricato")}</Text></View>
              <View style={styles.numCol}><Text style={styles.numSmall}>€{(b.impegnato || 0).toFixed(2)}</Text><Text style={styles.numLbl}>{t("wImpegnato")}</Text></View>
              <View style={styles.numCol}><Text style={styles.numBig}>€{(b.spendibile || 0).toFixed(2)}</Text><Text style={[styles.numLbl, { color: colors.brand }]}>{t("wSpendibile")}</Text></View>
            </View>
            {(b.ricariche_in_transito || []).map((r: any, i: number) => (
              <Text key={i} style={styles.transito}>⏳ {t("wRicaricheTransito")} {r.eta || r.date || "—"} (€{(r.amount || 0).toFixed(0)})</Text>
            ))}
            <Pressable testID="wallet-topup" style={styles.primaryBtn} onPress={() => router.push("/pulizie/listino" as any)}>
              <Ionicons name="add-circle" size={18} color="#fff" /><Text style={styles.primaryBtnTxt}>{t("wTopup")}</Text>
            </Pressable>
          </View>
        ) : (
          <View style={[styles.card, shadow.card]}>
            <Text style={styles.blockTitle}>💳 {t("wImpresaTitle")}</Text>
            <Text style={styles.rowSub}>{t("wPaymentMethod")}: {pmLabel}</Text>
            <Pressable style={styles.linkRow} onPress={() => router.push("/wallet")}><Text style={styles.link}>{t("wReceipts")} →</Text></Pressable>
          </View>
        )}

        {/* Block 2 — Limiti di legge */}
        <View style={[styles.card, shadow.card]}>
          <Text style={styles.blockTitle}>⚖️ {t("wLimitiTitle")}</Text>
          <Text style={styles.usageTag}>{t("wUsageJobby")}</Text>
          <View style={styles.limRow}>
            <Text style={styles.limLbl}>{t("wAnnuo")}</Text>
            <Text style={styles.limVal}>€{(lim.annual_used || 0).toFixed(0)} / €{(lim.annual_ceiling || 0).toFixed(0)}</Text>
          </View>
          <Bar pct={lim.annual_pct} warn={lim.annual_warn} />
          {(lim.per_collaboratrice || []).map((c: any) => (
            <View key={c.provider_id} style={{ marginTop: spacing.md }}>
              <View style={styles.limRow}>
                <Text style={styles.limLbl} numberOfLines={1}>👤 {c.nome}</Text>
                <Text style={styles.limVal}>€{(c.used_weighted || 0).toFixed(0)} / €{(c.ceiling || 0).toFixed(0)}</Text>
              </View>
              <Bar pct={c.pct} warn={c.warn} />
              {c.agevolata ? <Text style={styles.note}>ℹ️ {c.nome} {t("wAgevolataNote")}</Text> : null}
              {c.upsell ? (
                <View style={styles.upsell}><Text style={styles.upsellTxt}>{t("wUpsell")}</Text></View>
              ) : null}
            </View>
          ))}
          <Pressable testID="add-external" style={styles.linkRow} onPress={() => setExtOpen(true)}>
            <Ionicons name="add" size={16} color={colors.blue} /><Text style={styles.link}>{t("wExternalAdd")}</Text>
          </Pressable>
          {(lim.external_usages || []).length ? (
            <Text style={styles.note}>{t("wExternalTitle")}: €{(lim.external_total || 0).toFixed(0)}</Text>
          ) : null}
        </View>

        {/* Block 3 — Attività e documenti */}
        <View style={[styles.card, shadow.card]}>
          <Text style={styles.blockTitle}>📋 {t("wAttivitaTitle")}</Text>
          <Text style={styles.subH}>{t("wUpcoming")}</Text>
          {(att.upcoming || []).length ? att.upcoming.map((u: any) => (
            <Pressable key={u.richiesta_id} style={styles.docRow} onPress={() => router.push(`/pulizie/${u.richiesta_id}` as any)}>
              <Text style={styles.docTxt}>📅 {u.data_ora || "—"}</Text>
              <Text style={styles.docMeta}>{u.voucher ? `${u.voucher} ${t("wVoucher")}` : `€${(u.importo || 0).toFixed(2)}`}</Text>
            </Pressable>
          )) : <Text style={styles.rowSub}>{t("wNoData")}</Text>}
          <Text style={[styles.subH, { marginTop: spacing.md }]}>{t("wDocs")}</Text>
          {(att.documenti || []).length ? att.documenti.slice(0, 8).map((doc: any) => (
            <View key={doc.richiesta_id} style={styles.docRow}>
              <Text style={styles.docTxt}>🧾 {doc.data_ora || "—"} · €{(doc.importo || 0).toFixed(2)}</Text>
              <Text style={styles.link}>{t("wDownload")}</Text>
            </View>
          )) : <Text style={styles.rowSub}>{t("wNoData")}</Text>}
        </View>

        {/* Block 4 — Recupero fiscale */}
        <View style={[styles.card, shadow.card, { backgroundColor: colors.surfaceTertiary }]}>
          <Text style={styles.blockTitle}>💶 {t("wFiscTitle")}</Text>
          <Text style={styles.fiscBig}>€{(fisc.stima_deducibile || 0).toFixed(2)}</Text>
          <Text style={styles.rowSub}>{t("wFiscEstimate")} ({fisc.anno})</Text>
          <Pressable style={styles.linkRow}><Text style={styles.link}>{t("wFiscSummary")} →</Text></Pressable>
        </View>
      </ScrollView>

      <Modal visible={extOpen} transparent animationType="slide" onRequestClose={() => setExtOpen(false)}>
        <View style={styles.modalBg}>
          <View style={[styles.modalCard, { paddingBottom: insets.bottom + spacing.lg }]}>
            <Text style={styles.blockTitle}>{t("wExternalAdd")}</Text>
            <TextInput testID="ext-amount" style={styles.input} keyboardType="numeric" placeholder="€" placeholderTextColor={colors.muted} value={extAmount} onChangeText={setExtAmount} />
            <TextInput testID="ext-name" style={styles.input} placeholder={t("wPerColl")} placeholderTextColor={colors.muted} value={extName} onChangeText={setExtName} />
            <Pressable testID="ext-save" style={styles.primaryBtn} onPress={saveExternal}><Text style={styles.primaryBtnTxt}>{t("wExternalSave")}</Text></Pressable>
            <Pressable style={styles.linkRow} onPress={() => setExtOpen(false)}><Text style={styles.link}>{t("cancel") || "Annulla"}</Text></Pressable>
          </View>
        </View>
      </Modal>
    </View>
  );
}

// ------------------ PROVIDER ------------------
function ProviderDashboard() {
  const { t } = useLang();
  const insets = useSafeAreaInsets();
  const [d, setD] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try { setD(await api.providerDashboard()); } catch {} finally { setLoading(false); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const toggleDnd = async (v: boolean) => { setD((p: any) => ({ ...p, dnd: v })); try { await api.setDnd(v); } catch {} };

  if (loading) return <View style={styles.center}><ActivityIndicator color={colors.brand} /></View>;
  const g = d?.guadagni || {}; const lim = d?.limiti || {};

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingTop: insets.top + spacing.md, paddingBottom: insets.bottom + 160 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
        showsVerticalScrollIndicator={false}>
        <Text style={styles.h1}>{t("provDashTitle")}</Text>

        {/* Guadagni */}
        <View style={[styles.card, shadow.card]}>
          <Text style={styles.blockTitle}>💰 {t("pGuadagni")}</Text>
          <Text style={styles.fiscBig}>€{(g.incoming_total || 0).toFixed(2)}</Text>
          {(g.items || []).slice(0, 10).map((it: any, i: number) => (
            <View key={i} style={styles.docRow}>
              <Text style={styles.docTxt}>€{(it.amount || 0).toFixed(2)} · {it.categoria}</Text>
              <Text style={styles.docMeta}>{it.source === "INPS" ? `${t("pAccreditoInps")} ${it.date}` : (it.stato === "trasferito" ? t("pTransferDone") : t("pTransferPending"))}</Text>
            </View>
          ))}
          {!(g.items || []).length ? <Text style={styles.rowSub}>{t("wNoData")}</Text> : null}
        </View>

        {/* Limiti personali */}
        <View style={[styles.card, shadow.card]}>
          <Text style={styles.blockTitle}>⚖️ {t("pLimitiPers")}</Text>
          <View style={styles.limRow}><Text style={styles.limLbl}>{t("pAnnuo")}</Text><Text style={styles.limVal}>€{(lim.annual_earned || 0).toFixed(0)} / €{(lim.annual_ceiling || 0).toFixed(0)}</Text></View>
          <Bar pct={lim.annual_pct} warn={lim.annual_warn} />
          <View style={[styles.limRow, { marginTop: spacing.md }]}><Text style={styles.limLbl}>{t("pOre")}</Text><Text style={styles.limVal}>{(lim.hours || 0).toFixed(0)} / {(lim.hours_ceiling || 0).toFixed(0)}h</Text></View>
          <Bar pct={lim.hours_pct} />
          <Text style={styles.note}>{t("pFamiglie")}: {lim.families || 0} · {t("pMaxFamily")}: €{(lim.max_family_used || 0).toFixed(0)} / €{(lim.family_ceiling || 0).toFixed(0)}</Text>
        </View>

        {/* Storico + affidabilità + DND */}
        <View style={[styles.card, shadow.card]}>
          <View style={styles.limRow}>
            <Text style={styles.blockTitle}>⭐ {t("pReliability")}</Text>
            <Text style={styles.limVal}>{(d?.reliability || 0).toFixed(0)}</Text>
          </View>
          <View style={styles.dndRow}>
            <Text style={styles.docTxt}>🌙 {t("pDnd")}</Text>
            <Switch testID="dnd-toggle" value={!!d?.dnd} onValueChange={toggleDnd} trackColor={{ true: colors.brand, false: colors.borderStrong }} thumbColor="#fff" />
          </View>
          <Text style={[styles.subH, { marginTop: spacing.md }]}>{t("pStorico")}</Text>
          {(d?.storico || []).length ? d.storico.slice(0, 10).map((s: any) => (
            <View key={s.richiesta_id} style={styles.docRow}>
              <Text style={styles.docTxt}>{s.data_ora || "—"} · €{(s.importo || 0).toFixed(2)}</Text>
              <Text style={styles.docMeta}>{s.recensione ? `⭐ ${s.recensione}` : "—"}</Text>
            </View>
          )) : <Text style={styles.rowSub}>{t("wNoData")}</Text>}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  h1: { fontSize: fsize["2xl"] || 24, fontFamily: font.bold, color: colors.onSurface, marginBottom: spacing.md },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.xl, borderWidth: 1, borderColor: colors.border },
  bonusCard: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.brand, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.lg },
  bonusLbl: { fontSize: fsize.sm, fontFamily: font.medium, color: "#fff", opacity: 0.9 },
  bonusVal: { fontSize: fsize["2xl"] || 24, fontFamily: font.bold, color: "#fff" },
  bonusNote: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 6, backgroundColor: "rgba(255,255,255,0.18)", alignSelf: "flex-start", paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.pill },
  bonusNoteText: { fontSize: 11, fontFamily: font.medium, color: "#fff" },
  blockTitle: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface, marginBottom: spacing.sm },
  numRow: { flexDirection: "row", justifyContent: "space-between", marginTop: spacing.sm },
  numCol: { flex: 1, alignItems: "center" },
  numBig: { fontSize: 26, fontFamily: font.bold, color: colors.brand },
  numSmall: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.onSurfaceSecondary },
  numLbl: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 2 },
  transito: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.warning, marginTop: spacing.sm },
  primaryBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: 12, marginTop: spacing.md },
  primaryBtnTxt: { color: "#fff", fontFamily: font.bold, fontSize: fsize.base },
  usageTag: { alignSelf: "flex-start", fontSize: fsize.sm, fontFamily: font.medium, color: colors.muted, backgroundColor: colors.surfaceTertiary, paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.pill, marginBottom: spacing.sm, overflow: "hidden" },
  limRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 6 },
  limLbl: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface, flex: 1, marginRight: spacing.sm },
  limVal: { fontSize: fsize.base, fontFamily: font.bold, color: colors.onSurfaceSecondary },
  barTrack: { height: 10, borderRadius: radius.pill, backgroundColor: colors.surfaceTertiary, overflow: "hidden" },
  barFill: { height: 10, borderRadius: radius.pill },
  note: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 6 },
  upsell: { backgroundColor: colors.surfaceTertiary, borderLeftWidth: 3, borderLeftColor: colors.warning, borderRadius: radius.sm, padding: spacing.sm, marginTop: spacing.sm },
  upsellTxt: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.onSurface },
  subH: { fontSize: fsize.base, fontFamily: font.bold, color: colors.onSurfaceTertiary, marginBottom: spacing.sm },
  docRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors.border },
  docTxt: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface, flex: 1, marginRight: spacing.sm },
  docMeta: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.muted },
  fiscBig: { fontSize: 30, fontFamily: font.bold, color: colors.brand, marginVertical: 4 },
  rowSub: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 4 },
  link: { fontSize: fsize.base, fontFamily: font.medium, color: colors.blue },
  linkRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: spacing.md },
  dndRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: spacing.sm },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  modalCard: { backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.lg },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface, marginTop: spacing.sm },
});
