import React, { useCallback, useEffect, useMemo, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, KeyboardAvoidingView, Platform, ActivityIndicator, Alert, Image, Linking } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as ImagePicker from "expo-image-picker";
import * as Location from "expo-location";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize } from "@/src/theme";
import { Button } from "@/src/components/UI";

const TREVISO = { lat: 45.6669, lng: 12.2433 };

export default function ArtigianiConfigura() {
  const { lang, t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [meta, setMeta] = useState<any>(null);
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);

  const [mestiere, setMestiere] = useState("");
  const [modalita, setModalita] = useState("diagnosi");
  const [interventoId, setInterventoId] = useState("");
  const [descrizione, setDescrizione] = useState("");
  const [foto, setFoto] = useState<string[]>([]);
  const [urgente, setUrgente] = useState(false);
  const [fascia, setFascia] = useState("immediato");
  const [address, setAddress] = useState("Via Roma 12, Treviso");
  const [coords, setCoords] = useState(TREVISO);
  const [accesso, setAccesso] = useState("");
  const [binario, setBinario] = useState("impresa");
  const [routeWarn, setRouteWarn] = useState<string | null>(null);
  const [est, setEst] = useState<any>(null);
  const [params, setParams] = useState<any>({});
  const [dataGiorno, setDataGiorno] = useState("");
  const [fasciaOraria, setFasciaOraria] = useState("");

  useEffect(() => { (async () => { try { setMeta(await api.artConfig()); } catch {} })(); }, []);

  const mObj = useMemo(() => (meta?.mestieri || []).find((m: any) => m.id === mestiere), [meta, mestiere]);
  const paramList = useMemo(() => (meta?.parametri || {})[mestiere] || [], [meta, mestiere]);
  const setParam = (pid: string, val: any) => setParams((p: any) => ({ ...p, [pid]: val }));
  const giorni = useMemo(() => Array.from({ length: 14 }, (_, i) => { const d = new Date(); d.setDate(d.getDate() + i); return d; }), []);

  const paramsValid = () => paramList.every((p: any) => {
    if (!p.required) return true;
    const v = params[p.id];
    if (p.type === "cascade") return !!(v?.categoria && v?.elemento);
    if (p.type === "select") { const o = p.options.find((x: any) => x.id === v?.id); return !!(v?.id && (!o?.needs_text || (v.text || "").trim())); }
    if (p.type === "number") return String(v ?? "").trim() !== "";
    return (v || "").trim().length > 1;
  });

  const buildDesc = () => paramList.map((p: any) => {
    const v = params[p.id];
    if (v == null || v === "") return null;
    if (p.type === "cascade") { const cat = p.options.find((o: any) => o.id === v.categoria); const el = cat?.sub.find((s: any) => s.id === v.elemento); return `${p.label[lang]}: ${cat?.label[lang] || ""}${el ? ` › ${el.label[lang]}` : ""}`; }
    if (p.type === "select") { const o = p.options.find((x: any) => x.id === v.id); return `${p.label[lang]}: ${o?.label[lang] || ""}${v.text ? ` (${v.text})` : ""}`; }
    return `${p.label[lang]}: ${v}`;
  }).filter(Boolean).join(" · ");
  const isTuttofare = mestiere === "tuttofare";
  const STEPS = useMemo(() => isTuttofare ? ["mestiere", "problema", "quando", "dove", "binario", "riepilogo"] : ["mestiere", "problema", "quando", "dove", "riepilogo"], [isTuttofare]);

  const config = useMemo(() => ({ mestiere, modalita, intervento_id: interventoId, binario, urgente, lat: coords.lat, lng: coords.lng }), [mestiere, modalita, interventoId, binario, urgente, coords]);
  const loadEstimate = useCallback(async () => { if (!mestiere) return; try { setEst(await api.artEstimate(config)); } catch {} }, [config, mestiere]);
  useEffect(() => { if (meta && STEPS[step] === "riepilogo") loadEstimate(); }, [meta, step, STEPS, loadEstimate]);

  // route-check tuttofare -> abilitato
  useEffect(() => {
    const txt = String(params.descrizione || "");
    if (isTuttofare && modalita === "diagnosi" && txt.length > 8) {
      const tmo = setTimeout(async () => {
        try { const r = await api.artRouteCheck(txt); setRouteWarn(r.suggested_mestiere ? (r.mestiere_label || r.suggested_mestiere) : null); } catch {}
      }, 600);
      return () => clearTimeout(tmo);
    } else setRouteWarn(null);
  }, [params.descrizione, isTuttofare, modalita]);

  const addPhoto = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) { Alert.alert(t("permissionNeeded"), "", [{ text: "OK" }, { text: t("openSettings"), onPress: () => Linking.openSettings() }]); return; }
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, quality: 0.4, base64: true });
    if (res.canceled || !res.assets?.[0]?.base64) return;
    setFoto([...foto, `data:image/jpeg;base64,${res.assets[0].base64}`]);
  };

  const useMyLocation = async () => {
    try { const { status } = await Location.requestForegroundPermissionsAsync(); if (status !== "granted") return;
      const loc = await Location.getCurrentPositionAsync({}); setCoords({ lat: loc.coords.latitude, lng: loc.coords.longitude });
      setAddress(`${loc.coords.latitude.toFixed(4)}, ${loc.coords.longitude.toFixed(4)} · Treviso`); } catch {}
  };

  const submit = async () => {
    setLoading(true);
    try {
      const descFinal = modalita === "diagnosi" ? [buildDesc(), isTuttofare ? "" : descrizione].filter(Boolean).join(" — ") : descrizione;
      const r = await api.artCreateRichiesta({ mestiere, modalita, intervento_id: interventoId, parametri: params, descrizione: descFinal, foto, binario, urgente, fascia_urgenza: fascia, fascia_oraria: fasciaOraria, data_ora: dataGiorno, indirizzo: address, accesso, lat: coords.lat, lng: coords.lng });
      router.replace(`/artigiani/${r.richiesta_id}?new=1`);
    } catch { setLoading(false); }
  };

  if (!meta) return <View style={[styles.container, { alignItems: "center", justifyContent: "center" }]}><ActivityIndicator color={colors.brand} /></View>;
  const paniere = meta.paniere[mestiere] || [];

  const renderParam = (p: any) => {
    const v = params[p.id];
    if (p.type === "cascade") {
      const catOpt = p.options.find((o: any) => o.id === v?.categoria);
      return (
        <View key={p.id}>
          <Text style={styles.label}>{p.label[lang]}</Text>
          <View style={styles.wrap}>{p.options.map((o: any) => (
            <Pressable key={o.id} testID={`art-param-${p.id}-${o.id}`} style={[styles.chip, v?.categoria === o.id && styles.optOn]} onPress={() => setParam(p.id, { categoria: o.id, elemento: "" })}><Text style={[styles.optText, v?.categoria === o.id && styles.optTextOn]}>{o.label[lang]}</Text></Pressable>))}</View>
          {catOpt ? (<><Text style={styles.label}>{catOpt.label[lang]}</Text>
            <View style={styles.wrap}>{catOpt.sub.map((s: any) => (
              <Pressable key={s.id} testID={`art-param-${p.id}-el-${s.id}`} style={[styles.chip, v?.elemento === s.id && styles.optOn]} onPress={() => setParam(p.id, { ...v, elemento: s.id })}><Text style={[styles.optText, v?.elemento === s.id && styles.optTextOn]}>{s.label[lang]}</Text></Pressable>))}</View></>) : null}
        </View>);
    }
    if (p.type === "select") {
      const sel = p.options.find((o: any) => o.id === v?.id);
      return (
        <View key={p.id}>
          <Text style={styles.label}>{p.label[lang]}</Text>
          {p.options.map((o: any) => (
            <Pressable key={o.id} testID={`art-param-${p.id}-${o.id}`} style={[styles.rowOpt, v?.id === o.id && styles.optOn]} onPress={() => setParam(p.id, o.needs_text ? { id: o.id, text: "" } : { id: o.id })}>
              <Text style={[styles.optText, v?.id === o.id && styles.optTextOn]}>{o.label[lang]}</Text>
              {v?.id === o.id ? <Ionicons name="checkmark-circle" size={20} color={colors.brand} /> : null}
            </Pressable>))}
          {sel?.needs_text ? <TextInput testID={`art-param-${p.id}-text`} style={styles.input} value={v?.text || ""} onChangeText={(tx) => setParam(p.id, { id: sel.id, text: tx })} placeholder={t("artOtherDesc")} placeholderTextColor={colors.muted} /> : null}
        </View>);
    }
    if (p.type === "number") {
      return (<View key={p.id}><Text style={styles.label}>{p.label[lang]}</Text>
        <TextInput testID={`art-param-${p.id}`} style={styles.input} keyboardType="numeric" value={v != null ? String(v) : ""} onChangeText={(tx) => setParam(p.id, tx)} placeholderTextColor={colors.muted} /></View>);
    }
    return (<View key={p.id}><Text style={styles.label}>{p.label[lang]}</Text>
      <TextInput testID={`art-param-${p.id}`} style={[styles.input, { minHeight: 70, textAlignVertical: "top" }]} multiline value={v || ""} onChangeText={(tx) => setParam(p.id, tx)} placeholderTextColor={colors.muted} /></View>);
  };

  const renderStep = () => {
    switch (STEPS[step]) {
      case "mestiere":
        return (<View style={styles.grid}>{meta.mestieri.map((m: any) => (
          <Pressable key={m.id} testID={`art-mest-${m.id}`} style={[styles.mestCard, mestiere === m.id && styles.optOn]} onPress={() => { setMestiere(m.id); setInterventoId(""); if (!m.libretto) setBinario("impresa"); }}>
            <Text style={{ fontSize: 30 }}>{m.icon}</Text>
            <Text style={[styles.mestName, mestiere === m.id && styles.optTextOn]}>{m[lang]}</Text>
            {m.abilitazione ? <Text style={styles.mestBadge}>🛡️ abilitato</Text> : null}
          </Pressable>))}</View>);
      case "problema":
        return (<>
          <View style={styles.segRow}>
            <Pressable testID="art-mod-diagnosi" style={[styles.seg, modalita === "diagnosi" && styles.segOn]} onPress={() => setModalita("diagnosi")}><Text style={[styles.segText, modalita === "diagnosi" && styles.segTextOn]}>{t("artDiagnosi")}</Text></Pressable>
            {paniere.length ? <Pressable testID="art-mod-paniere" style={[styles.seg, modalita === "paniere" && styles.segOn]} onPress={() => setModalita("paniere")}><Text style={[styles.segText, modalita === "paniere" && styles.segTextOn]}>{t("artPaniere")}</Text></Pressable> : null}
          </View>
          {modalita === "paniere" ? (
            paniere.map((p: any) => (
              <Pressable key={p.id} testID={`art-int-${p.id}`} style={[styles.rowOpt, interventoId === p.id && styles.optOn]} onPress={() => setInterventoId(p.id)}>
                <Text style={[styles.optText, interventoId === p.id && styles.optTextOn]}>{p[lang]}</Text>
                <Text style={styles.fixedPrice}>€{p.prezzo}</Text>
              </Pressable>))
          ) : (<>
            <Text style={styles.hint}>{t("artDiagnosiSub")}</Text>
            {paramList.map((p: any) => renderParam(p))}
            {routeWarn ? <View style={styles.warnBox}><Ionicons name="alert-circle" size={18} color={colors.warning} /><Text style={styles.warnText}>{t("artRouteWarn").replace("{m}", routeWarn)}</Text></View> : null}
            {!isTuttofare ? (<>
              <Text style={styles.label}>{t("artOtherDesc")}</Text>
              <TextInput testID="art-note" style={[styles.input, { minHeight: 60, textAlignVertical: "top" }]} value={descrizione} onChangeText={setDescrizione} multiline placeholderTextColor={colors.muted} />
            </>) : null}
            <View style={styles.photoRow}>
              {foto.map((f, i) => <Image key={i} source={{ uri: f }} style={styles.photo} />)}
              <Pressable testID="art-add-photo" style={styles.addPhoto} onPress={addPhoto}><Ionicons name="camera" size={24} color={colors.brand} /><Text style={styles.addPhotoText}>{t("artAddPhoto")}</Text></Pressable>
            </View>
          </>)}
        </>);
      case "quando":
        return (<>
          <View style={styles.segRow}>
            <Pressable testID="art-prog" style={[styles.seg, !urgente && styles.segOn]} onPress={() => setUrgente(false)}><Text style={[styles.segText, !urgente && styles.segTextOn]}>📅 {t("artProgrammato")}</Text></Pressable>
            <Pressable testID="art-urg" style={[styles.seg, urgente && styles.segOn]} onPress={() => setUrgente(true)}><Text style={[styles.segText, urgente && styles.segTextOn]}>⚡ {t("artUrgente")}</Text></Pressable>
          </View>
          {urgente ? (<>
            <Text style={styles.hint}>{t("artUrgenteSub")}</Text>
            <View style={styles.wrap}>{meta.fasce_urgenza.map((fz: any) => (
              <Pressable key={fz.id} testID={`art-fascia-${fz.id}`} style={[styles.chip, fascia === fz.id && styles.optOn]} onPress={() => setFascia(fz.id)}><Text style={[styles.optText, fascia === fz.id && styles.optTextOn]}>{fz[lang]}</Text></Pressable>))}</View>
          </>) : (<>
            <Text style={styles.label}>{t("artSelectDate")}</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, paddingVertical: 4 }}>
              {giorni.map((d) => { const iso = d.toISOString().slice(0, 10); const on = dataGiorno === iso;
                return (<Pressable key={iso} testID={`art-day-${iso}`} style={[styles.dayChip, on && styles.optOn]} onPress={() => setDataGiorno(iso)}>
                  <Text style={[styles.dayDow, on && styles.optTextOn]}>{d.toLocaleDateString(lang === "it" ? "it-IT" : "en-US", { weekday: "short" })}</Text>
                  <Text style={[styles.dayNum, on && styles.optTextOn]}>{d.getDate()}</Text>
                  <Text style={[styles.dayMon, on && styles.optTextOn]}>{d.toLocaleDateString(lang === "it" ? "it-IT" : "en-US", { month: "short" })}</Text>
                </Pressable>); })}
            </ScrollView>
            <Text style={styles.label}>{t("artFasciaOraria")}</Text>
            <View style={styles.wrap}>{(meta.fasce_orarie || []).map((fo: any) => (
              <Pressable key={fo.id} testID={`art-oraria-${fo.id}`} style={[styles.chip, fasciaOraria === fo.id && styles.optOn]} onPress={() => setFasciaOraria(fo.id)}><Text style={[styles.optText, fasciaOraria === fo.id && styles.optTextOn]}>{fo[lang]}</Text></Pressable>))}</View>
          </>)}
        </>);
      case "dove":
        return (<>
          <Text style={styles.label}>{t("address")}</Text>
          <TextInput testID="art-address" style={styles.input} value={address} onChangeText={setAddress} placeholderTextColor={colors.muted} />
          <Button label={t("useMyLocation")} variant="secondary" icon="navigate" onPress={useMyLocation} style={{ marginTop: spacing.md, height: 46 }} />
          <Text style={styles.label}>{t("artAccess")}</Text>
          <TextInput testID="art-access" style={styles.input} value={accesso} onChangeText={setAccesso} placeholderTextColor={colors.muted} />
        </>);
      case "binario":
        return (<>{meta.binari.map((b: any) => (
          <Pressable key={b.id} testID={`art-bin-${b.id}`} style={[styles.rowOpt, binario === b.id && styles.optOn]} onPress={() => setBinario(b.id)}>
            <Text style={[styles.optText, binario === b.id && styles.optTextOn]}>{b[lang]}</Text>
            {binario === b.id ? <Ionicons name="checkmark-circle" size={22} color={colors.brand} /> : null}
          </Pressable>))}</>);
      case "riepilogo":
        return (<>
          <View style={styles.sumCard}>
            <Text style={styles.sumRow}>{mObj?.icon} {mObj?.[lang]}{mObj?.abilitazione ? " 🛡️" : ""}</Text>
            <Text style={styles.sumSub}>{modalita === "paniere" ? (paniere.find((p: any) => p.id === interventoId)?.[lang] || "") : t("artDiagnosi")}{urgente ? " · ⚡" : ""}</Text>
            {modalita === "diagnosi" && buildDesc() ? <Text style={styles.sumSub}>{buildDesc()}</Text> : null}
            <Text style={styles.sumSub}>{urgente ? `⚡ ${(meta.fasce_urgenza.find((x: any) => x.id === fascia) || {})[lang] || ""}` : `📅 ${dataGiorno} · ${(meta.fasce_orarie.find((x: any) => x.id === fasciaOraria) || {})[lang] || ""}`}</Text>
            <Text style={styles.sumSub}>📍 {address}</Text>
          </View>
          <View style={styles.priceBox}>
            <Text style={styles.priceLabel}>{modalita === "paniere" ? t("artFixedPrice") : t("artCallFee")}</Text>
            <Text style={styles.priceVal}>{est?.min != null ? `€${est.min.toFixed(2)}${est.max && est.max !== est.min ? ` – €${est.max.toFixed(2)}` : ""}` : t("artNoProvider")}</Text>
            {est?.providers ? <Text style={styles.priceNote}>{est.providers} artigiani</Text> : null}
          </View>
          {modalita === "diagnosi" ? <Text style={styles.scomputoNote}>💡 {t("artScomputoNote")}</Text> : null}
        </>);
    }
  };

  const isLast = STEPS[step] === "riepilogo";
  const canNext = STEPS[step] === "mestiere" ? !!mestiere
    : STEPS[step] === "problema" ? (modalita === "paniere" ? !!interventoId : paramsValid())
    : STEPS[step] === "quando" ? (urgente ? !!fascia : !!(dataGiorno && fasciaOraria))
    : true;
  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="art-back" onPress={() => (step === 0 ? router.back() : setStep(step - 1))} hitSlop={12}><Ionicons name="arrow-back" size={24} color={colors.onSurface} /></Pressable>
        <Text style={styles.headerTitle}>🛠️ {t("artigiani")}</Text>
        <View style={{ width: 24 }} />
      </View>
      <View style={styles.progress}>{STEPS.map((_, i) => (<View key={i} style={[styles.pBar, { backgroundColor: i <= step ? colors.brand : colors.border }]} />))}</View>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 140 }} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
          <Text style={styles.stepTitle}>{STEPS[step] === "mestiere" ? t("artMestiere") : STEPS[step] === "problema" ? t("artProblem") : STEPS[step] === "quando" ? t("artWhen") : STEPS[step] === "dove" ? t("artWhere") : STEPS[step] === "binario" ? t("artBinario") : t("artSummary")}</Text>
          {renderStep()}
        </ScrollView>
        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          <Button testID={isLast ? "art-publish" : "art-next"} label={isLast ? t("publishRequest") : t("next")} loading={loading} onPress={() => (isLast ? submit() : (canNext ? setStep(step + 1) : null))} />
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  headerTitle: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  progress: { flexDirection: "row", gap: 4, paddingHorizontal: spacing.lg, marginBottom: spacing.md },
  pBar: { flex: 1, height: 4, borderRadius: 2 },
  stepTitle: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface, marginBottom: spacing.lg },
  label: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary, marginTop: spacing.md, marginBottom: spacing.sm },
  hint: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginBottom: spacing.md },
  input: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  mestCard: { width: "47%", padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, alignItems: "center", gap: 6 },
  mestName: { fontSize: fsize.base, fontFamily: font.bold, color: colors.onSurface, textAlign: "center" },
  mestBadge: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted },
  optOn: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  optText: { fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  optTextOn: { color: colors.onBrandTertiary, fontFamily: font.medium },
  segRow: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.md },
  seg: { flex: 1, paddingVertical: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, alignItems: "center", backgroundColor: colors.surfaceSecondary },
  segOn: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  segText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  segTextOn: { color: colors.onBrandTertiary },
  rowOpt: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: spacing.md, paddingHorizontal: spacing.lg, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, marginBottom: spacing.sm },
  fixedPrice: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.brand },
  warnBox: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: "#FDF0DD", borderRadius: radius.md, padding: spacing.md, marginTop: spacing.sm },
  warnText: { flex: 1, fontSize: fsize.sm, fontFamily: font.medium, color: colors.onSurface },
  photoRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.md },
  photo: { width: 72, height: 72, borderRadius: radius.md },
  addPhoto: { width: 72, height: 72, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, borderStyle: "dashed", alignItems: "center", justifyContent: "center" },
  addPhotoText: { fontSize: 9, color: colors.brand, marginTop: 2 },
  wrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  dayChip: { alignItems: "center", paddingVertical: spacing.sm, paddingHorizontal: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, minWidth: 58 },
  dayDow: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, textTransform: "capitalize" },
  dayNum: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.onSurface },
  dayMon: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, textTransform: "capitalize" },
  chip: { paddingVertical: spacing.sm, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  sumCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.md },
  sumRow: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  sumSub: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 4 },
  priceBox: { backgroundColor: colors.brandTertiary, borderRadius: radius.lg, padding: spacing.lg, alignItems: "center", marginBottom: spacing.md },
  priceLabel: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onBrandTertiary },
  priceVal: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.brand, marginTop: 4 },
  priceNote: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.onSurfaceTertiary, marginTop: 6 },
  scomputoNote: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: spacing.sm },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.lg, paddingTop: spacing.md, backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderTopColor: colors.divider },
});
