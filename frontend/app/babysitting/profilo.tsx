import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, Alert, KeyboardAvoidingView, Platform, Linking } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as ImagePicker from "expo-image-picker";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize } from "@/src/theme";
import { Button } from "@/src/components/UI";

export default function BsProfile() {
  const { lang, t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [meta, setMeta] = useState<any>(null);
  const [p, setP] = useState<any>({ esperienza_anni: 0, fasce_eta: [], lingue: [], certificazioni: [], materie: [], livelli: [], presentazione: {}, disponibilita: [] });
  const [casellario, setCasellario] = useState<any>({ uploaded: false, verified: false });
  const [busy, setBusy] = useState(false);

  useEffect(() => { (async () => {
    try {
      setMeta(await api.bsConfig());
      const r = await api.bsGetProfile();
      if (r.bs_profile && Object.keys(r.bs_profile).length) setP((prev: any) => ({ ...prev, ...r.bs_profile }));
      setCasellario(r.casellario || {});
    } catch {}
  })(); }, []);

  const toggle = (key: string, id: string) => setP((prev: any) => ({ ...prev, [key]: prev[key].includes(id) ? prev[key].filter((x: string) => x !== id) : [...prev[key], id] }));
  const setQ = (q: string, v: string) => setP((prev: any) => ({ ...prev, presentazione: { ...prev.presentazione, [q]: v } }));

  const uploadCasellario = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) { Alert.alert(t("permissionNeeded"), "", [{ text: "OK" }, { text: t("openSettings"), onPress: () => Linking.openSettings() }]); return; }
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, quality: 0.4, base64: true });
    if (res.canceled || !res.assets?.[0]?.base64) return;
    try { await api.bsUploadCasellario(`data:image/jpeg;base64,${res.assets[0].base64}`); setCasellario({ uploaded: true, verified: false }); Alert.alert(t("bsCasellarioUploaded")); }
    catch { Alert.alert(t("error")); }
  };

  const save = async () => {
    setBusy(true);
    try { await api.bsSetProfile(p); Alert.alert(t("saved")); router.back(); }
    catch { Alert.alert(t("error")); } finally { setBusy(false); }
  };

  if (!meta) return <View style={styles.container} />;

  const Chips = ({ list, sel, k }: { list: any[]; sel: string[]; k: string }) => (
    <View style={styles.wrap}>{list.map((o: any) => (
      <Pressable key={o.id} testID={`p-${k}-${o.id}`} style={[styles.chip, sel.includes(o.id) && styles.chipOn]} onPress={() => toggle(k, o.id)}>
        <Text style={[styles.chipText, sel.includes(o.id) && styles.chipTextOn]}>{o[lang]}{o.highlight ? " ⭐" : ""}</Text></Pressable>))}</View>
  );

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="bp-back" onPress={() => router.back()} hitSlop={12}><Ionicons name="arrow-back" size={24} color={colors.onSurface} /></Pressable>
        <Text style={styles.headerTitle}>{t("bsProfileTitle")}</Text>
        <View style={{ width: 24 }} />
      </View>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }} keyboardShouldPersistTaps="handled">
          {/* Casellario */}
          <Text style={styles.section}>{t("bsCasellario")}</Text>
          <Text style={styles.hint}>{t("bsCasellarioSub")}</Text>
          {casellario.verified ? (
            <View style={styles.okBox}><Ionicons name="shield-checkmark" size={22} color={colors.success} /><Text style={styles.okText}>{t("bsCasellarioVerified")}</Text></View>
          ) : casellario.uploaded ? (
            <View style={styles.pendBox}><Ionicons name="time" size={20} color={colors.warning} /><Text style={styles.pendText}>{t("bsPendingVerify")}</Text></View>
          ) : null}
          <Button testID="upload-casellario" label={casellario.uploaded ? t("bsCasellarioUploaded") : t("bsCasellario")} variant="secondary" icon="document-attach" onPress={uploadCasellario} style={{ marginTop: spacing.sm, height: 46 }} />

          <Text style={styles.section}>{t("bsExperience")}</Text>
          <View style={styles.numRow}>
            <Text style={styles.numLabel}>{t("bsYears")}</Text>
            <TextInput testID="p-exp" style={styles.numInput} keyboardType="number-pad" value={String(p.esperienza_anni)} onChangeText={(v) => setP({ ...p, esperienza_anni: Number(v.replace(/[^0-9]/g, "")) || 0 })} />
          </View>
          <Text style={styles.subSec}>{t("bsAgeBands")}</Text>
          <Chips list={meta.age_bands} sel={p.fasce_eta} k="fasce_eta" />

          <Text style={styles.section}>{t("bsLanguages")}</Text>
          <Chips list={meta.languages} sel={p.lingue} k="lingue" />

          <Text style={styles.section}>{t("bsCertifications")}</Text>
          <Chips list={meta.certifications} sel={p.certificazioni} k="certificazioni" />

          <Text style={styles.section}>{t("bsSubjects")} / {t("bsSchoolLevel")}</Text>
          <Chips list={meta.subjects} sel={p.materie} k="materie" />
          <View style={{ height: spacing.sm }} />
          <Chips list={meta.school_levels} sel={p.livelli} k="livelli" />

          <Text style={styles.section}>{t("bsAvailability")}</Text>
          <Chips list={meta.availability_slots} sel={p.disponibilita} k="disponibilita" />

          <Text style={styles.section}>{t("bsGuided")}</Text>
          {meta.guided_questions.map((q: any) => (
            <View key={q.id}>
              <Text style={styles.qLabel}>{q[lang]}</Text>
              <TextInput testID={`p-q-${q.id}`} style={[styles.input, { minHeight: 56, textAlignVertical: "top" }]} value={p.presentazione?.[q.id] || ""} onChangeText={(v) => setQ(q.id, v)} multiline placeholderTextColor={colors.muted} />
            </View>))}

          <Button testID="bp-save" label={t("save")} loading={busy} onPress={save} style={{ marginTop: spacing.xl }} />
          <Button testID="bp-listino" label={t("bsListinoTitle")} variant="secondary" onPress={() => router.push("/babysitting/listino")} style={{ marginTop: spacing.sm }} />
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
  subSec: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary, marginTop: spacing.md, marginBottom: spacing.sm },
  hint: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginBottom: spacing.sm },
  wrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: { paddingVertical: spacing.sm, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  chipOn: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  chipText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface },
  chipTextOn: { color: colors.onBrandTertiary, fontFamily: font.medium },
  numRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: spacing.sm },
  numLabel: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface },
  numInput: { width: 80, paddingVertical: spacing.sm, paddingHorizontal: spacing.md, textAlign: "right", fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  input: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface, marginBottom: spacing.sm },
  qLabel: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary, marginTop: spacing.md, marginBottom: spacing.sm },
  okBox: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.greenBg, borderRadius: radius.md, padding: spacing.md },
  okText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.success },
  pendBox: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: "#FDF0DD", borderRadius: radius.md, padding: spacing.md },
  pendText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
});
