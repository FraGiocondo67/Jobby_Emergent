import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, Alert, KeyboardAvoidingView, Platform, Switch, Linking } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as ImagePicker from "expo-image-picker";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize } from "@/src/theme";
import { Button } from "@/src/components/UI";

export default function ArtigianiListino() {
  const { lang, t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [meta, setMeta] = useState<any>(null);
  const [mestiere, setMestiere] = useState("");
  const [f, setF] = useState<any>({ binario: "impresa", chiamata_fee: 50, tariffa_oraria: 35, paniere: [], urgenze: false, urgenze_pct: 0, raggio_km: 20, tempi_tipici: "", abilitazione_numero: "" });
  const [abil, setAbil] = useState<any>({ verified: false, uploaded: false, fgas: false });
  const [busy, setBusy] = useState(false);

  useEffect(() => { (async () => {
    try {
      const m = await api.artConfig(); setMeta(m);
      const first = m.mestieri[0].id; setMestiere(first);
      const r = await api.artGetListino();
      setAbil(r.abilitazioni || {});
      if (r.art_listini?.[first]) applyListino(r.art_listini[first], first, m);
      else initPaniere(first, m);
    } catch {}
  })(); }, []);

  const initPaniere = (mid: string, m: any) => {
    const p = (m.paniere[mid] || []).map((x: any) => ({ id: x.id, prezzo: x.prezzo }));
    setF((prev: any) => ({ ...prev, paniere: p }));
  };
  const applyListino = (l: any, mid: string, m: any) => {
    const defaults = (m.paniere[mid] || []);
    const merged = defaults.map((d: any) => ({ id: d.id, prezzo: (l.paniere || []).find((x: any) => x.id === d.id)?.prezzo ?? d.prezzo }));
    setF({ ...f, ...l, paniere: merged });
  };

  const switchMestiere = async (mid: string) => {
    setMestiere(mid);
    try {
      const r = await api.artGetListino();
      if (r.art_listini?.[mid]) applyListino(r.art_listini[mid], mid, meta);
      else { setF({ binario: "impresa", chiamata_fee: 50, tariffa_oraria: 35, paniere: [], urgenze: false, urgenze_pct: 0, raggio_km: 20, tempi_tipici: "", abilitazione_numero: "" }); initPaniere(mid, meta); }
    } catch {}
  };

  const mObj = meta?.mestieri.find((m: any) => m.id === mestiere);
  const setPanierePrice = (pid: string, v: string) => setF((p: any) => ({ ...p, paniere: p.paniere.map((x: any) => x.id === pid ? { ...x, prezzo: v === "" ? "" : Number(v) } : x) }));

  const uploadAbil = async (kind: string) => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) { Alert.alert(t("permissionNeeded"), "", [{ text: "OK" }, { text: t("openSettings"), onPress: () => Linking.openSettings() }]); return; }
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, quality: 0.4, base64: true });
    if (res.canceled || !res.assets?.[0]?.base64) return;
    try { await api.artUploadAbilitazione(kind, `data:image/jpeg;base64,${res.assets[0].base64}`); setAbil({ ...abil, uploaded: kind === "abilitazione" ? true : abil.uploaded, fgas: kind === "fgas" ? true : abil.fgas }); Alert.alert(t("saved")); }
    catch { Alert.alert(t("error")); }
  };

  const save = async () => {
    setBusy(true);
    try { await api.artSetListino(mestiere, f); Alert.alert(t("saved")); router.back(); }
    catch { Alert.alert(t("error")); } finally { setBusy(false); }
  };

  if (!meta) return <View style={styles.container} />;
  const paniereDefs = meta.paniere[mestiere] || [];

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="al-back" onPress={() => router.back()} hitSlop={12}><Ionicons name="arrow-back" size={24} color={colors.onSurface} /></Pressable>
        <Text style={styles.headerTitle}>{t("artListinoTitle")}</Text>
        <View style={{ width: 24 }} />
      </View>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }} keyboardShouldPersistTaps="handled">
          <Text style={styles.section}>{t("artSelectMestiere")}</Text>
          <View style={styles.wrap}>{meta.mestieri.map((m: any) => (
            <Pressable key={m.id} testID={`al-mest-${m.id}`} style={[styles.chip, mestiere === m.id && styles.chipOn]} onPress={() => switchMestiere(m.id)}><Text style={[styles.chipText, mestiere === m.id && styles.chipTextOn]}>{m.icon} {m[lang]}</Text></Pressable>))}</View>

          {mObj?.abilitazione ? (<>
            <Text style={styles.section}>{t("artAbilitazione")}</Text>
            {abil.verified ? <View style={styles.okBox}><Ionicons name="shield-checkmark" size={20} color={colors.success} /><Text style={styles.okText}>{t("artAbilVerified")}</Text></View>
              : abil.uploaded ? <View style={styles.pendBox}><Ionicons name="time" size={18} color={colors.warning} /><Text style={styles.pendText}>{t("artAbilPending")}</Text></View> : null}
            <TextInput testID="al-abil-num" style={styles.input} value={f.abilitazione_numero} onChangeText={(v) => setF({ ...f, abilitazione_numero: v })} placeholder={t("artAbilNumber")} placeholderTextColor={colors.muted} />
            <Button testID="al-upload-abil" label={t("artUploadAbil")} variant="secondary" icon="document-attach" onPress={() => uploadAbil("abilitazione")} style={{ marginTop: spacing.sm, height: 44 }} />
            {mObj?.fgas ? <Button testID="al-upload-fgas" label={t("artUploadFgas")} variant="secondary" icon="snow" onPress={() => uploadAbil("fgas")} style={{ marginTop: spacing.sm, height: 44 }} /> : null}
          </>) : null}

          <Text style={styles.section}>{t("artCallFee")} + {t("artHourly")}</Text>
          <NumRow label={t("artCallFee")} value={f.chiamata_fee} onChange={(v) => setF({ ...f, chiamata_fee: v })} testID="al-chiamata" />
          <NumRow label={t("artHourly")} value={f.tariffa_oraria} onChange={(v) => setF({ ...f, tariffa_oraria: v })} testID="al-oraria" />

          <Text style={styles.section}>{t("artPaniere")}</Text>
          {paniereDefs.map((p: any) => {
            const cur = f.paniere.find((x: any) => x.id === p.id);
            return (<View key={p.id} style={styles.numRow}><Text style={styles.numLabel}>{p[lang]}</Text>
              <View style={styles.numInputWrap}><Text style={styles.euro}>€</Text><TextInput testID={`al-pan-${p.id}`} style={styles.numInput} keyboardType="numeric" value={String(cur?.prezzo ?? p.prezzo)} onChangeText={(v) => setPanierePrice(p.id, v)} /></View></View>);
          })}

          <Text style={styles.section}>{t("otherSettings")}</Text>
          <View style={styles.rowOpt}><Text style={styles.optText}>⚡ {t("artUrgencyToggle")}</Text><Switch testID="al-urg" value={f.urgenze} onValueChange={(v) => setF({ ...f, urgenze: v })} trackColor={{ true: colors.brand, false: colors.borderStrong }} thumbColor="#fff" /></View>
          {f.urgenze ? <NumRow label={t("artUrgencyPct")} value={f.urgenze_pct} onChange={(v) => setF({ ...f, urgenze_pct: v })} testID="al-urgpct" /> : null}
          <NumRow label={`${t("radius")} (km)`} value={f.raggio_km} onChange={(v) => setF({ ...f, raggio_km: v })} testID="al-raggio" />
          <Text style={styles.label}>{t("artTimes")}</Text>
          <TextInput testID="al-tempi" style={styles.input} value={f.tempi_tipici} onChangeText={(v) => setF({ ...f, tempi_tipici: v })} placeholder="es. entro 48h" placeholderTextColor={colors.muted} />
          {mObj?.libretto ? (<>
            <Text style={styles.section}>{t("artBinario")}</Text>
            <View style={styles.segRow}>{meta.binari.map((b: any) => (
              <Pressable key={b.id} testID={`al-bin-${b.id}`} style={[styles.seg, f.binario === b.id && styles.chipOn]} onPress={() => setF({ ...f, binario: b.id })}><Text style={[styles.segText, f.binario === b.id && styles.chipTextOn]}>{b[lang]}</Text></Pressable>))}</View>
          </>) : null}

          <Button testID="al-save" label={t("save")} loading={busy} onPress={save} style={{ marginTop: spacing.xl }} />
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

function NumRow({ label, value, onChange, testID }: { label: string; value: any; onChange: (v: any) => void; testID: string }) {
  return (
    <View style={styles.numRow}>
      <Text style={styles.numLabel}>{label}</Text>
      <View style={styles.numInputWrap}><Text style={styles.euro}> </Text>
        <TextInput testID={testID} style={styles.numInput} keyboardType="numeric" value={String(value)} onChangeText={(v) => onChange(v === "" ? "" : Number(v))} /></View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.divider },
  headerTitle: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  section: { fontSize: fsize.sm, fontFamily: font.bold, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.5, marginTop: spacing.lg, marginBottom: spacing.sm },
  label: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary, marginTop: spacing.md, marginBottom: spacing.sm },
  wrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: { paddingVertical: spacing.sm, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  chipOn: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  chipText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface },
  chipTextOn: { color: colors.onBrandTertiary, fontFamily: font.medium },
  input: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface },
  numRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  numLabel: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface, flex: 1 },
  numInputWrap: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md },
  euro: { fontSize: fsize.base, color: colors.muted },
  numInput: { width: 64, paddingVertical: spacing.sm, textAlign: "right", fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  rowOpt: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: spacing.md },
  optText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface, flex: 1 },
  segRow: { flexDirection: "row", gap: spacing.sm },
  seg: { flex: 1, paddingVertical: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, alignItems: "center", backgroundColor: colors.surfaceSecondary },
  segText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  okBox: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.greenBg, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.sm },
  okText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.success },
  pendBox: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: "#FDF0DD", borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.sm },
  pendText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
});
