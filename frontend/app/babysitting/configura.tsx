import React, { useCallback, useEffect, useMemo, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, KeyboardAvoidingView, Platform, ActivityIndicator, Switch } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Location from "expo-location";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize } from "@/src/theme";
import { Button } from "@/src/components/UI";
import { DateField, TimeField } from "@/src/components/DateTimeField";

const TREVISO = { lat: 45.6669, lng: 12.2433 };
const STEPS = ["children", "when", "where", "ripetizioni", "recurrence", "summary"];

export default function BabysittingConfigura() {
  const { lang, t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [meta, setMeta] = useState<any>(null);
  const [children, setChildren] = useState<any[]>([]);
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);

  const [selected, setSelected] = useState<string[]>([]);
  const [date, setDate] = useState("2026-07-25");
  const [startT, setStartT] = useState("20:00");
  const [endT, setEndT] = useState("23:00");
  const [urgente, setUrgente] = useState(false);
  const [address, setAddress] = useState("Via Roma 12, Treviso");
  const [coords, setCoords] = useState(TREVISO);
  const [accesso, setAccesso] = useState("");
  const [ripOn, setRipOn] = useState(false);
  const [ripMaterie, setRipMaterie] = useState<string[]>([]);
  const [ripOre, setRipOre] = useState(1);
  const [ripLivello, setRipLivello] = useState("medie");
  const [serale, setSerale] = useState(true);
  const [festivo, setFestivo] = useState(false);
  const [ricorrenza, setRicorrenza] = useState("una_tantum");
  const [note, setNote] = useState("");
  const [binario, setBinario] = useState("persona_lf");
  const [est, setEst] = useState<any>(null);

  useEffect(() => { (async () => { try { setMeta(await api.bsConfig()); } catch {} })(); }, []);
  useFocusEffect(useCallback(() => { (async () => { try { setChildren(await api.bsChildren()); } catch {} })(); }, []));

  const durata = useMemo(() => {
    try {
      const [sh, sm] = startT.split(":").map(Number); const [eh, em] = endT.split(":").map(Number);
      let d = (eh * 60 + em) - (sh * 60 + sm); if (d <= 0) d += 24 * 60; return Math.round(d / 15) * 15 / 60;
    } catch { return 3; }
  }, [startT, endT]);

  const config = useMemo(() => ({
    n_bambini: selected.length || 1, durata_ore: durata,
    ripetizioni_attiva: ripOn, ripetizioni_materie: ripMaterie, ripetizioni_ore: ripOn ? ripOre : 0,
    ripetizioni_livello: ripLivello, serale, festivo,
  }), [selected, durata, ripOn, ripMaterie, ripOre, ripLivello, serale, festivo]);

  const loadEstimate = useCallback(async () => {
    try { setEst(await api.bsEstimate({ binario, lat: coords.lat, lng: coords.lng, config })); } catch {}
  }, [binario, coords, config]);
  useEffect(() => { if (meta && step >= 1) loadEstimate(); }, [meta, step, loadEstimate]);

  const useMyLocation = async () => {
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== "granted") return;
      const loc = await Location.getCurrentPositionAsync({});
      const c = { lat: loc.coords.latitude, lng: loc.coords.longitude };
      setCoords(c);
      try { const g = await api.reverseGeocode(c.lat, c.lng); if (g?.label) setAddress(g.label); } catch {}
    } catch {}
  };

  const resolveCoords = async () => {
    try { const g = await api.geocode(address); if (g && !g.fallback) { const c = { lat: g.lat, lng: g.lng }; setCoords(c); return c; } } catch {}
    return coords;
  };

  const toggle = (arr: string[], set: (v: string[]) => void, id: string) =>
    set(arr.includes(id) ? arr.filter((x) => x !== id) : [...arr, id]);

  const submit = async () => {
    if (selected.length === 0) { setStep(0); return; }
    setLoading(true);
    try {
      const c = await resolveCoords();
      const r = await api.bsCreateRichiesta({
        binario, bambini: selected, config, indirizzo: address, lat: c.lat, lng: c.lng,
        data_ora: `${date}T${startT}:00`, ora_fine: `${date}T${endT}:00`, urgente,
        ricorrenza, note, accesso, publish: true,
      });
      router.replace(`/babysitting/${r.richiesta_id}?new=1`);
    } catch { setLoading(false); }
  };

  if (!meta) return <View style={[styles.container, { alignItems: "center", justifyContent: "center" }]}><ActivityIndicator color={colors.brand} /></View>;
  const range = est?.ranges?.[binario];

  const renderStep = () => {
    switch (STEPS[step]) {
      case "children":
        return (<>
          <Text style={styles.hint}>{t("bsSelectChildren")}</Text>
          {children.length === 0 ? <Text style={styles.empty}>{t("bsNoChildren")}</Text> : null}
          {children.map((c) => (
            <Pressable key={c.card_id} testID={`sel-child-${c.card_id}`} style={[styles.rowOpt, selected.includes(c.card_id) && styles.optOn]} onPress={() => toggle(selected, setSelected, c.card_id)}>
              <Text style={styles.optText}>{c.sesso === "f" ? "👧" : c.sesso === "m" ? "👦" : "🧒"} {c.nome} · {Math.floor(c.eta_mesi / 12)}a</Text>
              <Ionicons name={selected.includes(c.card_id) ? "checkbox" : "square-outline"} size={22} color={selected.includes(c.card_id) ? colors.brand : colors.muted} />
            </Pressable>))}
          <Button testID="manage-children" label={t("bsAddChild")} variant="secondary" icon="add" onPress={() => router.push("/babysitting/children")} style={{ marginTop: spacing.sm, height: 46 }} />
        </>);
      case "when":
        return (<>
          <View style={styles.row2}>
            <View style={{ flex: 1 }}><Text style={styles.label}>{t("date")}</Text><DateField testID="bs-date" value={date} onChange={setDate} lang={lang} /></View>
          </View>
          <View style={styles.row2}>
            <View style={{ flex: 1 }}><Text style={styles.label}>{t("bsStart")}</Text><TimeField testID="bs-start" value={startT} onChange={setStartT} /></View>
            <View style={{ flex: 1 }}><Text style={styles.label}>{t("bsEnd")}</Text><TimeField testID="bs-end" value={endT} onChange={setEndT} /></View>
          </View>
          <Text style={styles.dur}>{durata}h</Text>
          <Text style={styles.guaranteeNote}>💡 {t("bsMinGuaranteed")}</Text>
          <View style={[styles.rowOpt, { marginTop: spacing.md }]}>
            <View style={{ flex: 1 }}><Text style={styles.optText}>⚡ {t("bsUrgent")}</Text><Text style={styles.subMini}>{t("bsUrgentHint")}</Text></View>
            <Switch testID="bs-urgent" value={urgente} onValueChange={setUrgente} trackColor={{ true: colors.brand, false: colors.borderStrong }} thumbColor="#fff" />
          </View>
        </>);
      case "where":
        return (<>
          <Text style={styles.label}>{t("address")}</Text>
          <TextInput testID="bs-address" style={styles.input} value={address} onChangeText={setAddress} placeholderTextColor={colors.muted} />
          <Button label={t("useMyLocation")} variant="secondary" icon="navigate" onPress={useMyLocation} style={{ marginTop: spacing.md, height: 46 }} />
          <Text style={styles.label}>{t("bsAccess")}</Text>
          <TextInput testID="bs-access" style={styles.input} value={accesso} onChangeText={setAccesso} placeholderTextColor={colors.muted} />
        </>);
      case "ripetizioni":
        return (<>
          <View style={styles.rowOpt}>
            <Text style={styles.optText}>📚 {t("bsRipetizioniOn")}</Text>
            <Switch testID="bs-rip-on" value={ripOn} onValueChange={setRipOn} trackColor={{ true: colors.brand, false: colors.borderStrong }} thumbColor="#fff" />
          </View>
          {ripOn ? (<>
            <Text style={styles.label}>{t("bsSchoolLevel")}</Text>
            <View style={styles.wrap}>{meta.school_levels.map((o: any) => (
              <Pressable key={o.id} testID={`rip-lvl-${o.id}`} style={[styles.opt, ripLivello === o.id && styles.optOn]} onPress={() => setRipLivello(o.id)}><Text style={[styles.optText, ripLivello === o.id && styles.optTextOn]}>{o[lang]}</Text></Pressable>))}</View>
            <Text style={styles.label}>{t("bsSubjects")}</Text>
            <View style={styles.wrap}>{meta.subjects.map((o: any) => (
              <Pressable key={o.id} testID={`rip-mat-${o.id}`} style={[styles.opt, ripMaterie.includes(o.id) && styles.optOn]} onPress={() => toggle(ripMaterie, setRipMaterie, o.id)}><Text style={[styles.optText, ripMaterie.includes(o.id) && styles.optTextOn]}>{o[lang]}</Text></Pressable>))}</View>
            <Text style={styles.label}>{t("bsRipHours")}</Text>
            <View style={styles.stepper}>
              <Pressable testID="rip-ore-minus" style={styles.stepBtn} onPress={() => setRipOre(Math.max(1, ripOre - 1))}><Ionicons name="remove" size={22} color={colors.onSurface} /></Pressable>
              <Text style={styles.stepVal}>{ripOre}h</Text>
              <Pressable testID="rip-ore-plus" style={styles.stepBtn} onPress={() => setRipOre(Math.min(Math.floor(durata), ripOre + 1))}><Ionicons name="add" size={22} color={colors.onSurface} /></Pressable>
            </View>
          </>) : null}
        </>);
      case "recurrence":
        return (<>
          {meta.ricorrenze.map((o: any) => (
            <Pressable key={o.id} testID={`bs-ric-${o.id}`} style={[styles.rowOpt, ricorrenza === o.id && styles.optOn]} onPress={() => setRicorrenza(o.id)}>
              <Text style={[styles.optText, ricorrenza === o.id && styles.optTextOn]}>{o[lang]}</Text>
              {ricorrenza === o.id ? <Ionicons name="checkmark-circle" size={22} color={colors.brand} /> : null}
            </Pressable>))}
          <View style={[styles.rowOpt, { marginTop: spacing.md }]}>
            <Text style={styles.optText}>🌙 {t("bsEvening")}</Text>
            <Switch testID="bs-serale" value={serale} onValueChange={setSerale} trackColor={{ true: colors.brand, false: colors.borderStrong }} thumbColor="#fff" />
          </View>
          <View style={styles.rowOpt}>
            <Text style={styles.optText}>🎉 {t("bsHoliday")}</Text>
            <Switch testID="bs-festivo" value={festivo} onValueChange={setFestivo} trackColor={{ true: colors.brand, false: colors.borderStrong }} thumbColor="#fff" />
          </View>
        </>);
      case "summary":
        return (<>
          <Text style={styles.hint}>{t("bsBinario")}</Text>
          {meta.binari.map((o: any) => {
            const r = est?.ranges?.[o.id];
            return (
              <Pressable key={o.id} testID={`bs-track-${o.id}`} style={[styles.trackCard, binario === o.id && styles.optOn]} onPress={() => setBinario(o.id)}>
                <View style={styles.rowBetween}>
                  <Text style={[styles.cardTitle, binario === o.id && styles.optTextOn]}>{o[lang]}</Text>
                  {binario === o.id ? <Ionicons name="checkmark-circle" size={22} color={colors.brand} /> : null}
                </View>
                <Text style={styles.cardDesc}>{o[`desc_${lang}`]}</Text>
                <Text style={styles.trackPrice}>{r?.min != null ? `${t("fromLabel")} €${r.min.toFixed(2)}` : t("bsNoBabysitter")}{r?.providers ? ` · ${r.providers}` : ""}</Text>
              </Pressable>);
          })}
          <Text style={styles.label}>{t("notesOptional")}</Text>
          <TextInput testID="bs-note" style={[styles.input, { minHeight: 60, textAlignVertical: "top" }]} value={note} onChangeText={setNote} multiline placeholderTextColor={colors.muted} />
        </>);
    }
  };

  const isLast = step === STEPS.length - 1;
  const canNext = STEPS[step] === "children" ? selected.length > 0 : true;
  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="bs-back" onPress={() => (step === 0 ? router.back() : setStep(step - 1))} hitSlop={12}><Ionicons name="arrow-back" size={24} color={colors.onSurface} /></Pressable>
        <Text style={styles.headerTitle}>🧸 {t("babysitting")}</Text>
        <View style={{ width: 24 }} />
      </View>
      <View style={styles.progress}>{STEPS.map((_, i) => (<View key={i} style={[styles.pBar, { backgroundColor: i <= step ? colors.brand : colors.border }]} />))}</View>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 160 }} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
          <Text style={styles.stepTitle}>{t(`bsStep_${STEPS[step]}` as any)}</Text>
          {renderStep()}
        </ScrollView>
        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          {step >= 1 && range ? (
            <Text style={styles.estLine}>{range.min != null ? `${t("estimate")}: €${range.min.toFixed(2)}${range.max && range.max !== range.min ? `–${range.max.toFixed(2)}` : ""}` : t("bsNoBabysitter")}</Text>
          ) : null}
          <Button testID={isLast ? "bs-publish" : "bs-next"} label={isLast ? t("publishRequest") : t("next")} loading={loading} onPress={() => (isLast ? submit() : (canNext && setStep(step + 1)))} />
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
  label: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary, marginTop: spacing.lg, marginBottom: spacing.sm },
  hint: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginBottom: spacing.md },
  empty: { fontSize: fsize.base, color: colors.muted, textAlign: "center", marginVertical: spacing.lg },
  wrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  opt: { paddingVertical: spacing.md, paddingHorizontal: spacing.lg, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  optOn: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  optText: { fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  optTextOn: { color: colors.onBrandTertiary, fontFamily: font.medium },
  subMini: { fontSize: fsize.sm, color: colors.muted, fontFamily: font.regular, marginTop: 2 },
  rowOpt: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: spacing.md, paddingHorizontal: spacing.lg, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, marginBottom: spacing.sm },
  rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  cardTitle: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  cardDesc: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 4 },
  trackCard: { padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, marginBottom: spacing.md, gap: 4 },
  trackPrice: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.brand, marginTop: spacing.sm },
  input: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  row2: { flexDirection: "row", gap: spacing.md },
  dur: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.brand, marginTop: spacing.md },
  guaranteeNote: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: spacing.sm },
  stepper: { flexDirection: "row", alignItems: "center", alignSelf: "flex-start", backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  stepBtn: { width: 52, height: 52, alignItems: "center", justifyContent: "center" },
  stepVal: { fontSize: fsize.xl, fontFamily: font.medium, color: colors.onSurface, minWidth: 60, textAlign: "center" },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.lg, paddingTop: spacing.md, backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderTopColor: colors.divider },
  estLine: { fontSize: fsize.base, fontFamily: font.bold, color: colors.brand, textAlign: "center", marginBottom: spacing.sm },
});
