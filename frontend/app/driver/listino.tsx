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

const DEF_CLASS = { base: 8, per_km: 1.4, per_hour: 35, attesa_per_hour: 30 };

export default function DriverListino() {
  const { lang, t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [meta, setMeta] = useState<any>(null);
  const [tipo, setTipo] = useState("ncc");
  const [classi, setClassi] = useState<any>({});
  const [glob, setGlob] = useState<any>({ notturno_pct: 0, festivo_pct: 0, sconto_ar_pct: 0, raggio_km: 30, trasporto_minori: false, animali: false });
  const [vehicles, setVehicles] = useState<any[]>([]);
  const [auth, setAuth] = useState<any>({ numero: "", verified: false, uploaded: false });
  const [authNum, setAuthNum] = useState("");
  const [busy, setBusy] = useState(false);
  // new vehicle
  const [nvClass, setNvClass] = useState("standard");
  const [nvPlate, setNvPlate] = useState("");
  const [nvModel, setNvModel] = useState("");
  const [nvSeats] = useState("4");
  const [nvIns, setNvIns] = useState(false);

  useEffect(() => { (async () => {
    try {
      setMeta(await api.drvConfig());
      const r = await api.drvGetListino();
      if (r.driver_tipo) setTipo(r.driver_tipo);
      if (r.listino) {
        setClassi(r.listino.classi || {});
        setGlob({ notturno_pct: r.listino.notturno_pct || 0, festivo_pct: r.listino.festivo_pct || 0, sconto_ar_pct: r.listino.sconto_ar_pct || 0, raggio_km: r.listino.raggio_km || 30, trasporto_minori: !!r.listino.trasporto_minori, animali: !!r.listino.animali });
      }
      setVehicles(r.vehicles || []);
      if (r.authorization) { setAuth(r.authorization); setAuthNum(r.authorization.numero || ""); }
    } catch {}
  })(); }, []);

  const toggleClass = (cid: string) => setClassi((p: any) => {
    const n = { ...p }; if (n[cid]) delete n[cid]; else n[cid] = { ...DEF_CLASS }; return n;
  });
  const setClassVal = (cid: string, k: string, v: string) => setClassi((p: any) => ({ ...p, [cid]: { ...p[cid], [k]: v === "" ? "" : Number(v) } }));
  const setG = (k: string, v: any) => setGlob((p: any) => ({ ...p, [k]: v }));

  const addVehicle = async () => {
    if (!nvPlate.trim()) { Alert.alert(t("drvPlate")); return; }
    try {
      const v = await api.drvAddVehicle({ classe: nvClass, targa: nvPlate, modello: nvModel, posti: Number(nvSeats) || 4, assicurazione: nvIns });
      setVehicles([...vehicles, v]); setNvPlate(""); setNvModel("");
    } catch { Alert.alert(t("error")); }
  };
  const delVehicle = async (vid: string) => { try { await api.drvDelVehicle(vid); setVehicles(vehicles.filter((v) => v.vehicle_id !== vid)); } catch {} };

  const uploadAuth = async () => {
    if (!authNum.trim()) { Alert.alert(t("drvAuthNumber")); return; }
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) { Alert.alert(t("permissionNeeded"), "", [{ text: "OK" }, { text: t("openSettings"), onPress: () => Linking.openSettings() }]); return; }
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, quality: 0.4, base64: true });
    if (res.canceled || !res.assets?.[0]?.base64) return;
    try { await api.drvUploadAuth({ tipo, numero: authNum, image: `data:image/jpeg;base64,${res.assets[0].base64}` }); setAuth({ ...auth, numero: authNum, uploaded: true, verified: false }); Alert.alert(t("drvUploadAuth")); }
    catch { Alert.alert(t("error")); }
  };

  const save = async () => {
    if (Object.keys(classi).length === 0) { Alert.alert(t("drvClass")); return; }
    setBusy(true);
    try { await api.drvSetListino({ tipo, classi, ...glob }); Alert.alert(t("saved")); router.back(); }
    catch { Alert.alert(t("error")); } finally { setBusy(false); }
  };

  if (!meta) return <View style={styles.container} />;

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="dl-back" onPress={() => router.back()} hitSlop={12}><Ionicons name="arrow-back" size={24} color={colors.onSurface} /></Pressable>
        <Text style={styles.headerTitle}>{t("drvListinoTitle")}</Text>
        <View style={{ width: 24 }} />
      </View>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }} keyboardShouldPersistTaps="handled">
          <Text style={styles.section}>{t("drvServiceType")}</Text>
          <View style={styles.segRow}>
            {[["ncc", t("drvNcc")], ["taxi", t("drvTaxi")]].map(([id, lbl]) => (
              <Pressable key={id} testID={`dl-tipo-${id}`} style={[styles.seg, tipo === id && styles.segOn]} onPress={() => setTipo(id as string)}><Text style={[styles.segText, tipo === id && styles.segTextOn]}>{lbl}</Text></Pressable>))}
          </View>

          {/* Authorization */}
          <Text style={styles.section}>{t("drvAuthTitle")}</Text>
          {auth.verified ? <View style={styles.okBox}><Ionicons name="shield-checkmark" size={20} color={colors.success} /><Text style={styles.okText}>{tipo === "taxi" ? t("drvBadgeTaxi") : t("drvBadgeNcc")}</Text></View>
            : auth.uploaded ? <View style={styles.pendBox}><Ionicons name="time" size={18} color={colors.warning} /><Text style={styles.pendText}>{t("drvAuthPending")}</Text></View> : null}
          <TextInput testID="dl-auth-num" style={styles.input} value={authNum} onChangeText={setAuthNum} placeholder={t("drvAuthNumber")} placeholderTextColor={colors.muted} />
          <Button testID="dl-auth-upload" label={t("drvUploadAuth")} variant="secondary" icon="document-attach" onPress={uploadAuth} style={{ marginTop: spacing.sm, height: 46 }} />

          {/* Classes + listino */}
          <Text style={styles.section}>{t("drvClass")} + {t("drvListinoTitle")}</Text>
          {meta.vehicle_classes.map((c: any) => {
            const on = !!classi[c.id];
            return (
              <View key={c.id} style={styles.classCard}>
                <Pressable testID={`dl-class-${c.id}`} style={styles.classHead} onPress={() => toggleClass(c.id)}>
                  <Text style={styles.className}>{c.icon} {c[lang]}</Text>
                  <Ionicons name={on ? "checkbox" : "square-outline"} size={22} color={on ? colors.brand : colors.muted} />
                </Pressable>
                {on ? (
                  <View style={styles.classBody}>
                    {[["base", t("drvBase")], ["per_km", t("drvPerKm")], ["per_hour", t("drvPerHour")], ["attesa_per_hour", t("drvWaitRate")]].map(([k, lbl]) => (
                      <View key={k} style={styles.numRow}>
                        <Text style={styles.numLabel}>{lbl}</Text>
                        <View style={styles.numInputWrap}><Text style={styles.euro}>€</Text>
                          <TextInput testID={`dl-${c.id}-${k}`} style={styles.numInput} keyboardType="numeric" value={String(classi[c.id][k as string] ?? "")} onChangeText={(v) => setClassVal(c.id, k as string, v)} /></View>
                      </View>))}
                  </View>) : null}
              </View>);
          })}

          <Text style={styles.section}>{t("otherSettings")}</Text>
          {[["notturno_pct", t("drvNightPct")], ["festivo_pct", t("drvHolidayPct")], ["sconto_ar_pct", t("drvArDiscount")], ["raggio_km", `${t("radius")} (km)`]].map(([k, lbl]) => (
            <View key={k} style={styles.numRow}>
              <Text style={styles.numLabel}>{lbl}</Text>
              <TextInput testID={`dl-g-${k}`} style={styles.numInput2} keyboardType="numeric" value={String(glob[k as string])} onChangeText={(v) => setG(k as string, v === "" ? "" : Number(v))} />
            </View>))}
          <View style={styles.rowOpt}><Text style={styles.optText}>🧑 {t("drvMinorTransport")}</Text><Switch testID="dl-minors" value={glob.trasporto_minori} onValueChange={(v) => setG("trasporto_minori", v)} trackColor={{ true: colors.brand, false: colors.borderStrong }} thumbColor="#fff" /></View>
          <View style={styles.rowOpt}><Text style={styles.optText}>🐕 {t("drvAnimals")}</Text><Switch testID="dl-animals" value={glob.animali} onValueChange={(v) => setG("animali", v)} trackColor={{ true: colors.brand, false: colors.borderStrong }} thumbColor="#fff" /></View>

          {/* Vehicles */}
          <Text style={styles.section}>{t("drvVehicles")}</Text>
          {vehicles.map((v) => (
            <View key={v.vehicle_id} style={styles.vehRow}>
              <Text style={styles.vehText}>{v.classe} · {v.targa} {v.modello ? `· ${v.modello}` : ""} · {v.posti}👤 {v.assicurazione ? "· ✓" : ""}</Text>
              <Pressable testID={`dl-veh-del-${v.vehicle_id}`} onPress={() => delVehicle(v.vehicle_id)} hitSlop={8}><Ionicons name="trash-outline" size={20} color={colors.error} /></Pressable>
            </View>))}
          <View style={styles.newVeh}>
            <View style={styles.segRow}>{meta.vehicle_classes.map((c: any) => (
              <Pressable key={c.id} testID={`dl-nv-${c.id}`} style={[styles.seg, nvClass === c.id && styles.segOn]} onPress={() => setNvClass(c.id)}><Text style={[styles.segText, nvClass === c.id && styles.segTextOn]}>{c.icon}</Text></Pressable>))}</View>
            <TextInput testID="dl-nv-plate" style={[styles.input, { marginTop: spacing.sm }]} value={nvPlate} onChangeText={setNvPlate} autoCapitalize="characters" placeholder={t("drvPlate")} placeholderTextColor={colors.muted} />
            <TextInput testID="dl-nv-model" style={[styles.input, { marginTop: spacing.sm }]} value={nvModel} onChangeText={setNvModel} placeholder={t("drvModel")} placeholderTextColor={colors.muted} />
            <View style={styles.rowOpt}><Text style={styles.optText}>{t("drvInsurance")}</Text><Switch testID="dl-nv-ins" value={nvIns} onValueChange={setNvIns} trackColor={{ true: colors.brand, false: colors.borderStrong }} thumbColor="#fff" /></View>
            <Button testID="dl-add-vehicle" label={t("drvAddVehicle")} variant="secondary" icon="add" onPress={addVehicle} style={{ marginTop: spacing.sm, height: 44 }} />
          </View>

          <Button testID="dl-save" label={t("save")} loading={busy} onPress={save} style={{ marginTop: spacing.xl }} />
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
  segRow: { flexDirection: "row", gap: spacing.sm },
  seg: { flex: 1, paddingVertical: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, alignItems: "center", backgroundColor: colors.surfaceSecondary },
  segOn: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  segText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  segTextOn: { color: colors.onBrandTertiary },
  input: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface },
  classCard: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, marginBottom: spacing.sm, overflow: "hidden" },
  classHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: spacing.md, backgroundColor: colors.surfaceSecondary },
  className: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  classBody: { padding: spacing.md, paddingTop: 0 },
  numRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  numLabel: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface, flex: 1 },
  numInputWrap: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md },
  euro: { fontSize: fsize.base, color: colors.muted },
  numInput: { width: 60, paddingVertical: spacing.sm, textAlign: "right", fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  numInput2: { width: 74, paddingVertical: spacing.sm, paddingHorizontal: spacing.md, textAlign: "right", fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  rowOpt: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: spacing.md, marginTop: spacing.xs },
  optText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface, flex: 1 },
  vehRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, marginBottom: spacing.sm },
  vehText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface, flex: 1 },
  newVeh: { borderWidth: 1, borderColor: colors.border, borderStyle: "dashed", borderRadius: radius.md, padding: spacing.md },
  okBox: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.greenBg, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.sm },
  okText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.success },
  pendBox: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: "#FDF0DD", borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.sm },
  pendText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
});
