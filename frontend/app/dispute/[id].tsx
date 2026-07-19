import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, Alert, KeyboardAvoidingView, Platform } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Button } from "@/src/components/UI";

const STATUS_META: Record<string, { key: string; color: string; bg: string }> = {
  open: { key: "statusOpen", color: "#E8912A", bg: "#FDF0DD" },
  provider_responded: { key: "statusProviderResponded", color: "#6D3BEA", bg: "#EEE7FD" },
  resolved_mutual: { key: "statusResolvedMutual", color: "#1E9E5B", bg: "#E4F6EC" },
  resolved_jobby: { key: "statusResolvedJobby", color: "#1E9E5B", bg: "#E4F6EC" },
  escalated: { key: "statusEscalated", color: "#0E1F3D", bg: "#E1E6F0" },
  rejected: { key: "statusRejected", color: "#DE4B3F", bg: "#FBE0DD" },
};

const REC_KEY: Record<string, string> = {
  refund_full: "refundFull",
  refund_partial: "refundPartial",
  reject: "disputeReject",
};

export default function DisputeScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { user } = useAuth();
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [d, setD] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const [pct, setPct] = useState(100);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const doc = await api.getDispute(id as string);
      setD(doc);
      if (doc?.ai_recommendation?.refund_pct != null) setPct(doc.ai_recommendation.refund_pct);
    } catch {}
  }, [id]);

  useEffect(() => { load(); }, [load]);

  if (!d) return <View style={styles.container} />;

  const isProvider = d.role === "provider";
  const active = !["resolved_mutual", "resolved_jobby", "rejected"].includes(d.status);
  const canRespond = isProvider && (d.status === "open" || d.status === "provider_responded");
  const meta = STATUS_META[d.status] || STATUS_META.open;
  const ai = d.ai_recommendation;

  const send = async () => {
    if (!msg.trim()) return;
    setBusy(true);
    try {
      await api.disputeMessage(id as string, msg.trim());
      setMsg("");
      await load();
    } catch { Alert.alert(t("error")); } finally { setBusy(false); }
  };

  const accept = async () => {
    setBusy(true);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    try {
      await api.disputeRespond(id as string, { accept: true, refund_pct: pct });
      await load();
    } catch { Alert.alert(t("error")); } finally { setBusy(false); }
  };

  const rejectResp = async () => {
    setBusy(true);
    try {
      await api.disputeRespond(id as string, { accept: false, message: t("disputeReject") });
      await load();
    } catch { Alert.alert(t("error")); } finally { setBusy(false); }
  };

  const escalate = async () => {
    setBusy(true);
    try {
      await api.disputeEscalate(id as string);
      await load();
      Alert.alert(t("statusEscalated"));
    } catch { Alert.alert(t("error")); } finally { setBusy(false); }
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="dispute-back" onPress={() => router.back()} hitSlop={12}>
          <Ionicons name="arrow-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>{t("disputeTitle")}</Text>
        <View style={{ width: 24 }} />
      </View>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }} showsVerticalScrollIndicator={false}>
          <View style={[styles.card, shadow.card]}>
            <View style={styles.rowBetween}>
              <View style={[styles.pill, { backgroundColor: meta.bg }]}>
                <Text style={[styles.pillText, { color: meta.color }]}>{t(meta.key as any)}</Text>
              </View>
              <Text style={styles.amount}>€{Number(d.amount || 0).toFixed(2)}</Text>
            </View>
            <Text style={styles.reasonLabel}>{t("disputeReason")}</Text>
            <Text style={styles.reasonText} testID="dispute-reason">{d.reason_code}</Text>
            {d.description ? <Text style={styles.descText}>{d.description}</Text> : null}
          </View>

          {ai ? (
            <View style={[styles.aiCard, shadow.card]} testID="ai-recommendation">
              <View style={styles.aiHead}>
                <Ionicons name="sparkles" size={18} color={colors.brand} />
                <Text style={styles.aiTitle}>{t("aiRecommendation")}</Text>
              </View>
              <Text style={styles.aiRec}>{t(REC_KEY[ai.recommendation] as any)}{ai.recommendation === "refund_partial" ? ` · ${ai.refund_pct}%` : ""}</Text>
              <View style={styles.confRow}>
                <Text style={styles.confLabel}>{t("aiConfidence")}</Text>
                <View style={styles.confBar}><View style={[styles.confFill, { width: `${Math.round((ai.confidence || 0) * 100)}%` }]} /></View>
                <Text style={styles.confPct}>{Math.round((ai.confidence || 0) * 100)}%</Text>
              </View>
              {ai.rationale ? <Text style={styles.rationale}>{ai.rationale}</Text> : null}
              <Text style={styles.aiNote}>{t("aiProposalNote")}</Text>
            </View>
          ) : null}

          {d.resolution ? (
            <View style={[styles.resCard, shadow.card]} testID="dispute-resolution">
              <Text style={styles.resTitle}>{t("resolutionLabel")}</Text>
              <Text style={styles.resText}>
                {d.resolution.refund_pct >= 100 ? t("refundFull") : d.resolution.refund_pct > 0 ? `${t("refundPartial")} · ${d.resolution.refund_pct}%` : t("disputeReject")}
              </Text>
              {d.resolution.refund_amount != null ? <Text style={styles.resSub}>€{Number(d.resolution.refund_amount).toFixed(2)}</Text> : null}
              {d.resolution.note ? <Text style={styles.resSub}>{d.resolution.note}</Text> : null}
            </View>
          ) : null}

          {/* Provider response UI */}
          {canRespond ? (
            <View style={[styles.card, shadow.card]}>
              <Text style={styles.sectionLabel}>{t("yourResponse")}</Text>
              <Text style={styles.reasonLabel}>{t("refundPct")}</Text>
              <View style={styles.pctRow}>
                {[25, 50, 75, 100].map((p) => (
                  <Pressable key={p} testID={`pct-${p}`} style={[styles.pctChip, pct === p && styles.pctChipOn]} onPress={() => setPct(p)}>
                    <Text style={[styles.pctChipText, pct === p && styles.pctChipTextOn]}>{p}%</Text>
                  </Pressable>
                ))}
              </View>
              <Button testID="accept-refund" label={`${t("acceptRefund")} · ${pct}%`} icon="checkmark-circle" loading={busy} onPress={accept} style={{ marginTop: spacing.md }} />
              <Pressable testID="reject-dispute" style={styles.rejectBtn} onPress={rejectResp} disabled={busy}>
                <Text style={styles.rejectText}>{t("rejectDispute")}</Text>
              </Pressable>
            </View>
          ) : null}

          {/* Messages */}
          <Text style={styles.sectionLabel}>{t("disputeMessages")}</Text>
          {(d.messages || []).map((m: any, i: number) => {
            const mine = (m.from === "client" && !isProvider) || (m.from === "provider" && isProvider);
            return (
              <View key={i} style={[styles.msgBubble, mine ? styles.msgMine : styles.msgOther]}>
                <Text style={[styles.msgText, mine && { color: "#fff" }]}>{m.text}</Text>
              </View>
            );
          })}

          {active ? (
            <>
              <View style={styles.msgInputRow}>
                <TextInput testID="dispute-msg-input" style={styles.msgInput} value={msg} onChangeText={setMsg} placeholder={t("messagePlaceholder")} placeholderTextColor={colors.muted} />
                <Pressable testID="dispute-send" style={styles.sendBtn} onPress={send} disabled={busy}>
                  <Ionicons name="send" size={18} color="#fff" />
                </Pressable>
              </View>
              {d.status !== "escalated" ? (
                <Pressable testID="escalate-btn" style={styles.escalateBtn} onPress={escalate} disabled={busy}>
                  <Ionicons name="shield-outline" size={16} color={colors.brand} />
                  <Text style={styles.escalateText}>{t("escalateToJobby")}</Text>
                </Pressable>
              ) : (
                <Text style={styles.escalatedNote}>⚖️ {t("statusEscalated")}</Text>
              )}
            </>
          ) : null}
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.divider },
  headerTitle: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.lg, gap: spacing.sm },
  rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  pill: { paddingHorizontal: spacing.md, paddingVertical: 4, borderRadius: radius.pill },
  pillText: { fontSize: fsize.sm, fontFamily: font.bold },
  amount: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.brand },
  reasonLabel: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.5, marginTop: spacing.sm },
  reasonText: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  descText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurfaceTertiary },
  aiCard: { backgroundColor: "#F5F1FF", borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.lg, borderWidth: 1, borderColor: "#E0D4FF" },
  aiHead: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  aiTitle: { fontSize: fsize.base, fontFamily: font.bold, color: colors.brand, textTransform: "uppercase", letterSpacing: 0.5 },
  aiRec: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.onSurface, marginTop: spacing.sm },
  confRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.md },
  confLabel: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.muted },
  confBar: { flex: 1, height: 8, borderRadius: 4, backgroundColor: "#E0D4FF", overflow: "hidden" },
  confFill: { height: 8, borderRadius: 4, backgroundColor: colors.brand },
  confPct: { fontSize: fsize.sm, fontFamily: font.bold, color: colors.brand },
  rationale: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurfaceTertiary, marginTop: spacing.md, lineHeight: 20 },
  aiNote: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: spacing.sm, fontStyle: "italic" },
  resCard: { backgroundColor: "#E8F0EA", borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.lg, gap: 4 },
  resTitle: { fontSize: fsize.sm, fontFamily: font.bold, color: colors.success, textTransform: "uppercase" },
  resText: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  resSub: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurfaceTertiary },
  sectionLabel: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: spacing.sm },
  pctRow: { flexDirection: "row", gap: spacing.sm },
  pctChip: { flex: 1, paddingVertical: spacing.sm, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, alignItems: "center", backgroundColor: colors.surface },
  pctChipOn: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  pctChipText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  pctChipTextOn: { color: colors.onBrandTertiary, fontFamily: font.bold },
  rejectBtn: { alignSelf: "center", marginTop: spacing.md, paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.error },
  rejectText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.error },
  msgBubble: { maxWidth: "80%", padding: spacing.md, borderRadius: radius.lg, marginBottom: spacing.sm },
  msgMine: { alignSelf: "flex-end", backgroundColor: colors.brand, borderBottomRightRadius: 4 },
  msgOther: { alignSelf: "flex-start", backgroundColor: colors.surfaceSecondary, borderBottomLeftRadius: 4 },
  msgText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface },
  msgInputRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.sm },
  msgInput: { flex: 1, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface },
  sendBtn: { width: 46, height: 46, borderRadius: 23, backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" },
  escalateBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, marginTop: spacing.lg, paddingVertical: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.brand },
  escalateText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.brand },
  escalatedNote: { textAlign: "center", marginTop: spacing.lg, fontSize: fsize.base, fontFamily: font.medium, color: colors.muted },
});
