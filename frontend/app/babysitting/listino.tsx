import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, Alert, KeyboardAvoidingView, Platform } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize } from "@/src/theme";
import { Button } from "@/src/components/UI";

const DEFAULT = {
  tariffa_oraria: 10, tariffa_ripetizioni: { elementari: 12, medie: 16, superiori: 20 },
  materie: [], maggiorazione_serale_pct: 0, maggiorazione_festiva_pct: 0,
  supplemento_bambino: 0, raggio_km: 15, minimo_ore: 2,
};

export default function BsListino() {
  const { lang, t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [binario, setBinario] = useState("persona_lf");
  const [f, setF] = useState<any>(DEFAULT);
  const [subjects, setSubjects] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => { (async () => {
    try {
      const meta = await api.bsConfig(); setSubjects(meta.subjects || []);
      const r = await api.bsGetListino();
      if (r.bs_binario) setBinario(r.bs_binario);
      if (r.listino) setF({ ...DEFAULT, ...r.listino, tariffa_ripetizioni: { ...DEFAULT.tariffa_ripetizioni, ...(r.listino.tariffa_ripetizioni || {}) } });
    } catch {}
  })(); }, []);

  const setNum = (k: string, v: string) => setF((p: any) => ({ ...p, [k]: v === "" ? "" : Number(v) }));
  const setRip = (k: string, v: string) => setF((p: any) => ({ ...p, tariffa_ripetizioni: { ...p.tariffa_ripetizioni, [k]: v === "" ? "" : Number(v) } }));
  const toggleMat = (id: string) => setF((p: any) => ({ ...p, materie: p.materie.includes(id) ? p.materie.filter((x: string) => x !== id) : [...p.materie, id] }));

  const save = async () => {
    setBusy(true);
    try { await api.bsSetListino(binario, f); Alert.alert(t("saved")); router.back(); }
    catch { Alert.alert(t("error")); } finally { setBusy(false); }
  };

  const NumRow = ({ label, k, rip }: { label: string; k: string; rip?: boolean }) => (
    <View style={styles.numRow}>
      <Text style={styles.numLabel}>{label}</Text>
      <View style={styles.numInputWrap}>
        <Text style={styles.euro}>€</Text>
        <TextInput testID={`bl-${k}`} style={styles.numInput} keyboardType="numeric"
          value={String(rip ? f.tariffa_ripetizioni[k] : f[k])}
          onChangeText={(v) => (rip ? setRip(k, v) : setNum(k, v))} />
      </View>
    </View>
  );

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="bl-back" onPress={() => router.back()} hitSlop={12}><Ionicons name="arrow-back" size={24} color={colors.onSurface} /></Pressable>
        <Text style={styles.headerTitle}>{t("bsListinoTitle")}</Text>
        <View style={{ width: 24 }} />
      </View>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }} keyboardShouldPersistTaps="handled">
          <Text style={styles.section}>{t("bsBinario")}</Text>
          <View style={styles.trackRow}>
            {[["persona_lf", t("bsBinarioLf")], ["piva", t("bsBinarioPiva")]].map(([id, label]) => (
              <Pressable key={id} testID={`bl-bin-${id}`} style={[styles.trackBtn, binario === id && styles.trackOn]} onPress={() => setBinario(id as string)}>
                <Text style={[styles.trackText, binario === id && styles.trackTextOn]}>{label}</Text>
              </Pressable>))}
          </View>

          <Text style={styles.section}>{t("bsRateHourly")}</Text>
          <NumRow label={`${t("bsRateHourly")} (€/h)`} k="tariffa_oraria" />

          <Text style={styles.section}>{t("bsRateRip")}</Text>
          <NumRow label={t("bsSchoolLevel") + " · Elementari"} k="elementari" rip />
          <NumRow label={t("bsSchoolLevel") + " · Medie"} k="medie" rip />
          <NumRow label={t("bsSchoolLevel") + " · Superiori"} k="superiori" rip />

          <Text style={styles.section}>{t("bsSubjects")}</Text>
          <View style={styles.wrap}>{subjects.map((o: any) => (
            <Pressable key={o.id} testID={`bl-mat-${o.id}`} style={[styles.chip, f.materie.includes(o.id) && styles.chipOn]} onPress={() => toggleMat(o.id)}>
              <Text style={[styles.chipText, f.materie.includes(o.id) && styles.chipTextOn]}>{o[lang]}</Text></Pressable>))}</View>

          <Text style={styles.section}>{t("otherSettings")}</Text>
          <NumRow label={t("bsSuppChild")} k="supplemento_bambino" />
          <NumRow label={t("bsEveningPct")} k="maggiorazione_serale_pct" />
          <NumRow label={t("bsHolidayPct")} k="maggiorazione_festiva_pct" />
          <NumRow label={`${t("radius")} (km)`} k="raggio_km" />
          <NumRow label={`${t("minHours")} (h)`} k="minimo_ore" />

          <Button testID="bl-save" label={t("save")} loading={busy} onPress={save} style={{ marginTop: spacing.xl }} />
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.divider },
  headerTitle: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  section: { fontSize: fsize.sm, fontFamily: font.bold, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.5, marginTop: spacing.lg, marginBottom: spacing.sm },
  trackRow: { flexDirection: "row", gap: spacing.sm },
  trackBtn: { flex: 1, paddingVertical: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, alignItems: "center", backgroundColor: colors.surfaceSecondary },
  trackOn: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  trackText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  trackTextOn: { color: colors.onBrandTertiary },
  numRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  numLabel: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface, flex: 1 },
  numInputWrap: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md },
  euro: { fontSize: fsize.base, color: colors.muted, fontFamily: font.regular },
  numInput: { width: 64, paddingVertical: spacing.sm, textAlign: "right", fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  wrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: { paddingVertical: spacing.sm, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  chipOn: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  chipText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface },
  chipTextOn: { color: colors.onBrandTertiary, fontFamily: font.medium },
});
