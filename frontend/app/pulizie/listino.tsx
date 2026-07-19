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
  tariffa_ordinaria: 16, tariffa_afondo: 19, tariffa_posttrasloco: 22,
  prodotti_propri: true, supplemento_prodotti: 5,
  extra: { forno: 10, frigo: 8, finestre: 15, balconi: 12 },
  stiro_ora: 12, sconto_ricorrenza_pct: 10, raggio_km: 15, minimo_ore: 2,
};

export default function Listino() {
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [binario, setBinario] = useState("impresa");
  const [f, setF] = useState<any>(DEFAULT);
  const [busy, setBusy] = useState(false);

  useEffect(() => { (async () => {
    try { const r = await api.getListino(); if (r.pulizie_binario) setBinario(r.pulizie_binario); if (r.listino) setF({ ...DEFAULT, ...r.listino, extra: { ...DEFAULT.extra, ...(r.listino.extra || {}) } }); } catch {}
  })(); }, []);

  const setNum = (k: string, v: string) => setF((p: any) => ({ ...p, [k]: v === "" ? "" : Number(v) }));
  const setExtra = (k: string, v: string) => setF((p: any) => ({ ...p, extra: { ...p.extra, [k]: v === "" ? "" : Number(v) } }));

  const save = async () => {
    setBusy(true);
    try {
      const clean = { ...f, extra: { ...f.extra } };
      await api.setListino(binario, clean);
      Alert.alert(t("saved"));
      router.back();
    } catch { Alert.alert(t("error")); } finally { setBusy(false); }
  };

  const NumRow = ({ label, k, extra }: { label: string; k: string; extra?: boolean }) => (
    <View style={styles.numRow}>
      <Text style={styles.numLabel}>{label}</Text>
      <View style={styles.numInputWrap}>
        <Text style={styles.euro}>€</Text>
        <TextInput testID={`f-${k}`} style={styles.numInput} keyboardType="numeric"
          value={String(extra ? f.extra[k] : f[k])}
          onChangeText={(v) => (extra ? setExtra(k, v) : setNum(k, v))} />
      </View>
    </View>
  );

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="listino-back" onPress={() => router.back()} hitSlop={12}><Ionicons name="arrow-back" size={24} color={colors.onSurface} /></Pressable>
        <Text style={styles.headerTitle}>{t("listinoTitle")}</Text>
        <View style={{ width: 24 }} />
      </View>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
          <Text style={styles.section}>{t("track")}</Text>
          <View style={styles.trackRow}>
            {[["impresa", t("trackImpresa")], ["persona_lf", t("trackLF")]].map(([id, label]) => (
              <Pressable key={id} testID={`lb-${id}`} style={[styles.trackBtn, binario === id && styles.trackOn]} onPress={() => setBinario(id as string)}>
                <Text style={[styles.trackText, binario === id && styles.trackTextOn]}>{label}</Text>
              </Pressable>))}
          </View>

          <Text style={styles.section}>{t("hourlyRates")}</Text>
          <NumRow label={t("tipo_ordinaria")} k="tariffa_ordinaria" />
          <NumRow label={t("tipo_afondo")} k="tariffa_afondo" />
          <NumRow label={t("tipo_posttrasloco")} k="tariffa_posttrasloco" />

          <Text style={styles.section}>{t("extra")}</Text>
          <NumRow label={t("ex_forno")} k="forno" extra />
          <NumRow label={t("ex_frigo")} k="frigo" extra />
          <NumRow label={t("ex_finestre")} k="finestre" extra />
          <NumRow label={t("ex_balconi")} k="balconi" extra />
          <NumRow label={`${t("ironing")} (€/h)`} k="stiro_ora" />

          <Text style={styles.section}>{t("otherSettings")}</Text>
          <Pressable testID="prodotti-toggle" style={styles.numRow} onPress={() => setF((p: any) => ({ ...p, prodotti_propri: !p.prodotti_propri }))}>
            <Text style={styles.numLabel}>{t("ownProducts")}</Text>
            <Ionicons name={f.prodotti_propri ? "checkbox" : "square-outline"} size={24} color={f.prodotti_propri ? colors.brand : colors.muted} />
          </Pressable>
          <NumRow label={t("productsSupplement")} k="supplemento_prodotti" />
          <NumRow label={`${t("recurrenceDiscountPct")} (%)`} k="sconto_ricorrenza_pct" />
          <NumRow label={`${t("radius")} (km)`} k="raggio_km" />
          <NumRow label={`${t("minHours")} (h)`} k="minimo_ore" />

          <Button testID="save-listino" label={t("save")} loading={busy} onPress={save} style={{ marginTop: spacing.xl }} />
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
});
