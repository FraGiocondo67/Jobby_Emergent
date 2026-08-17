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
  // BLOCCO 10 (fix "provider nel raggio non vede le richieste generiche
  // persona_lf"): pulizie_compatible_providers (RPC) richiede
  // documents.lf_inps_registered=true per il binario persona_lf, ma prima
  // d'ora l'unico punto dell'app che scriveva questo campo lo fissava per
  // sempre a false durante l'onboarding (routers/provider_onboarding.py,
  // POST /onboarding/lf/inps) — nessuna schermata permetteva di aggiornarlo
  // in seguito. Aggiunto qui, unico posto sensato (stessa schermata del
  // binario a cui il flag si applica).
  const [inpsRegistered, setInpsRegistered] = useState(false);
  const [inpsBusy, setInpsBusy] = useState(false);

  useEffect(() => { (async () => {
    try { const r = await api.getListino(); if (r.pulizie_binario) setBinario(r.pulizie_binario); if (r.listino) setF({ ...DEFAULT, ...r.listino, extra: { ...DEFAULT.extra, ...(r.listino.extra || {}) } }); } catch {}
    try { const s = await api.providerStatus(); setInpsRegistered(!!s.lf_inps_registered); } catch {}
  })(); }, []);

  const toggleInps = async (v: boolean) => {
    setInpsRegistered(v); setInpsBusy(true);
    try { await api.setInps(v); } catch { setInpsRegistered(!v); Alert.alert(t("error")); } finally { setInpsBusy(false); }
  };

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

          {binario === "persona_lf" ? (
            <Pressable testID="inps-toggle" style={[styles.numRow, { opacity: inpsBusy ? 0.6 : 1 }]} disabled={inpsBusy} onPress={() => toggleInps(!inpsRegistered)}>
              <View style={{ flex: 1, paddingRight: spacing.sm }}>
                <Text style={styles.numLabel}>{t("inpsRegisteredLabel")}</Text>
                <Text style={styles.inpsDesc}>{t("inpsRegisteredDesc")}</Text>
              </View>
              <Ionicons name={inpsRegistered ? "checkbox" : "square-outline"} size={24} color={inpsRegistered ? colors.brand : colors.muted} />
            </Pressable>
          ) : null}

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
  inpsDesc: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 2 },
  numInputWrap: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md },
  euro: { fontSize: fsize.base, color: colors.muted, fontFamily: font.regular },
  numInput: { width: 64, paddingVertical: spacing.sm, textAlign: "right", fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
});
