import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, KeyboardAvoidingView, Platform, ActivityIndicator, Switch, Alert } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize } from "@/src/theme";
import { Button } from "@/src/components/UI";
import { DateField, TimeField } from "@/src/components/DateTimeField";

const STEPS = ["tipo", "route", "when", "class", "people", "extras", "summary"];

export default function DriverConfigura() {
  const { lang, t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ tipo?: string }>();
  const [meta, setMeta] = useState<any>(null);
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);

  const [tipo, setTipo] = useState(params.tipo === "taxi" ? "taxi" : "ncc");
  const [from, setFrom] = useState<any>(null);
  const [to, setTo] = useState<any>(null);
  const [fromQ, setFromQ] = useState("");
  const [toQ, setToQ] = useState("");
  const [searching, setSearching] = useState("");
  const [date, setDate] = useState("2026-07-25");
  const [time, setTime] = useState("09:00");
  const [flight, setFlight] = useState("");
  const [classe, setClasse] = useState("standard");
  const [passengers, setPassengers] = useState(1);
  const [luggage, setLuggage] = useState(0);
  const [whoElse, setWhoElse] = useState(false);
  const [pName, setPName] = useState("");
  const [pPhone, setPPhone] = useState("");
  const [minor, setMinor] = useState(false);
  const [minorConsent, setMinorConsent] = useState(false);
  const [special, setSpecial] = useState<string[]>([]);
  const [withReturn, setWithReturn] = useState(false);
  const [returnTime, setReturnTime] = useState("18:00");
  const [note, setNote] = useState("");
  const [est, setEst] = useState<any>(null);

  useEffect(() => { (async () => { try { setMeta(await api.drvConfig()); } catch {} })(); }, []);

  const geocode = async (which: "from" | "to") => {
    const q = which === "from" ? fromQ : toQ;
    if (!q.trim()) return;
    setSearching(which);
    try {
      const res = await api.drvGeocode(q);
      const wp = { label: res.label || q, lat: res.lat, lng: res.lng };
      if (which === "from") setFrom(wp); else setTo(wp);
    } catch { Alert.alert(t("error")); } finally { setSearching(""); }
  };

  const pickShortcut = (s: any, which: "from" | "to") => {
    const wp = { label: s[lang], lat: s.lat, lng: s.lng };
    if (which === "from") { setFrom(wp); setFromQ(s[lang]); } else { setTo(wp); setToQ(s[lang]); }
  };

  const loadEstimate = useCallback(async () => {
    if (!from || !to) return;
    try {
      setEst(await api.drvEstimate({ tipo, classe, from_lat: from.lat, from_lng: from.lng, to_lat: to.lat, to_lng: to.lng, pickup_at: `${date}T${time}:00`, ritorno: withReturn ? {} : null }));
    } catch {}
  }, [tipo, classe, from, to, date, time, withReturn]);
  useEffect(() => { if (meta && step >= 2 && from && to) loadEstimate(); }, [meta, step, loadEstimate, from, to]);

  const toggleSpecial = (id: string) => setSpecial((p) => p.includes(id) ? p.filter((x) => x !== id) : [...p, id]);

  const submit = async () => {
    if (!from || !to) { setStep(1); return; }
    if (minor && !minorConsent) { Alert.alert(t("drvMinorConsent")); return; }
    setLoading(true);
    try {
      const r = await api.drvCreateRichiesta({
        tipo, classe, partenza: from, destinazione: to, pickup_at: `${date}T${time}:00`,
        flight_number: flight, passeggeri: passengers, bagagli: luggage,
        passeggero_nome: whoElse ? pName : "", passeggero_tel: whoElse ? pPhone : "",
        minore: minor, minore_consenso: minorConsent, special,
        ritorno: withReturn ? { pickup_at: `${date}T${returnTime}:00` } : null, note,
      });
      router.replace(`/driver/${r.richiesta_id}?new=1`);
    } catch { setLoading(false); }
  };

  if (!meta) return <View style={[styles.container, { alignItems: "center", justifyContent: "center" }]}><ActivityIndicator color={colors.brand} /></View>;

  const renderPlace = (which: "from" | "to") => {
    const wp = which === "from" ? from : to;
    const q = which === "from" ? fromQ : toQ;
    return (
      <View style={{ marginBottom: spacing.md }}>
        <Text style={styles.label}>{which === "from" ? t("drvFrom") : t("drvTo")}</Text>
        <View style={styles.searchRow}>
          <TextInput testID={`drv-${which}-input`} style={styles.searchInput} value={q}
            onChangeText={(v) => (which === "from" ? setFromQ(v) : setToQ(v))}
            placeholder={t("drvSearchPlace")} placeholderTextColor={colors.muted} onSubmitEditing={() => geocode(which)} returnKeyType="search" />
          <Pressable testID={`drv-${which}-search`} style={styles.searchBtn} onPress={() => geocode(which)}>
            {searching === which ? <ActivityIndicator size="small" color="#fff" /> : <Ionicons name="search" size={18} color="#fff" />}
          </Pressable>
        </View>
        {wp ? <Text style={styles.wpOk}>📍 {wp.label}</Text> : (q.trim().length > 2 ? <Text style={styles.wpHint}>{t("drvTapSearch")}</Text> : null)}
        <View style={styles.shortcutWrap}>
          {meta.shortcuts.map((s: any) => (
            <Pressable key={s.id} testID={`sc-${which}-${s.id}`} style={styles.shortcut} onPress={() => pickShortcut(s, which)}>
              <Text style={styles.shortcutText}>{s.icon} {s[lang]}</Text></Pressable>))}
        </View>
      </View>
    );
  };

  const renderStep = () => {
    switch (STEPS[step]) {
      case "tipo":
        return (<>
          {[["ncc", t("drvNcc"), t("drvNccDesc"), "🚘"], ["taxi", t("drvTaxi"), t("drvTaxiDesc"), "🚕"]].map(([id, title, desc, emo]) => (
            <Pressable key={id} testID={`drv-tipo-${id}`} style={[styles.bigCard, tipo === id && styles.optOn]} onPress={() => setTipo(id as string)}>
              <Text style={{ fontSize: 32 }}>{emo}</Text>
              <View style={{ flex: 1 }}>
                <Text style={[styles.cardTitle, tipo === id && styles.optTextOn]}>{title}</Text>
                <Text style={styles.cardDesc}>{desc}</Text>
              </View>
              {tipo === id ? <Ionicons name="checkmark-circle" size={22} color={colors.brand} /> : null}
            </Pressable>))}
        </>);
      case "route":
        return (<>{renderPlace("from")}{renderPlace("to")}</>);
      case "when":
        return (<>
          <Text style={styles.label}>{t("drvWhen")}</Text>
          <View style={styles.row2}>
            <View style={{ flex: 1.4 }}><DateField testID="drv-date" value={date} onChange={setDate} lang={lang} /></View>
            <View style={{ flex: 1 }}><TimeField testID="drv-time" value={time} onChange={setTime} /></View>
          </View>
          <Text style={styles.label}>{t("drvFlight")}</Text>
          <TextInput testID="drv-flight" style={styles.input} value={flight} onChangeText={setFlight} autoCapitalize="characters" placeholder="FR1234" placeholderTextColor={colors.muted} />
          {flight ? <Text style={styles.hintMini}>✈️ {t("drvFlightHint")}</Text> : null}
        </>);
      case "class":
        return (<>{meta.vehicle_classes.map((c: any) => (
          <Pressable key={c.id} testID={`drv-class-${c.id}`} style={[styles.rowOpt, classe === c.id && styles.optOn]} onPress={() => setClasse(c.id)}>
            <Text style={[styles.optText, classe === c.id && styles.optTextOn]}>{c.icon} {c[lang]}</Text>
            {classe === c.id ? <Ionicons name="checkmark-circle" size={22} color={colors.brand} /> : null}
          </Pressable>))}</>);
      case "people":
        return (<>
          <Text style={styles.label}>{t("drvPassengers")}</Text>
          <Stepper testID="drv-pax" value={passengers} setValue={setPassengers} min={1} max={8} />
          <Text style={styles.label}>{t("drvLuggage")}</Text>
          <Stepper testID="drv-lug" value={luggage} setValue={setLuggage} min={0} max={12} />
          <Text style={styles.label}>{t("drvWhoTravels")}</Text>
          <View style={styles.segRow}>
            <Pressable testID="drv-who-me" style={[styles.seg, !whoElse && styles.segOn]} onPress={() => setWhoElse(false)}><Text style={[styles.segText, !whoElse && styles.segTextOn]}>{t("drvIAmTraveling")}</Text></Pressable>
            <Pressable testID="drv-who-else" style={[styles.seg, whoElse && styles.segOn]} onPress={() => setWhoElse(true)}><Text style={[styles.segText, whoElse && styles.segTextOn]}>{t("drvSomeoneElse")}</Text></Pressable>
          </View>
          {whoElse ? (<>
            <TextInput testID="drv-pname" style={styles.input} value={pName} onChangeText={setPName} placeholder={t("drvPassengerName")} placeholderTextColor={colors.muted} />
            <TextInput testID="drv-pphone" style={[styles.input, { marginTop: spacing.sm }]} value={pPhone} onChangeText={setPPhone} keyboardType="phone-pad" placeholder={t("drvPassengerPhone")} placeholderTextColor={colors.muted} />
            <View style={styles.rowOpt}><Text style={styles.optText}>🧑 {t("drvMinor")}</Text><Switch testID="drv-minor" value={minor} onValueChange={setMinor} trackColor={{ true: colors.brand, false: colors.borderStrong }} thumbColor="#fff" /></View>
            {minor ? <Pressable testID="drv-minor-consent" style={styles.consentRow} onPress={() => setMinorConsent(!minorConsent)}><Ionicons name={minorConsent ? "checkbox" : "square-outline"} size={22} color={minorConsent ? colors.brand : colors.muted} /><Text style={styles.consentText}>{t("drvMinorConsent")}</Text></Pressable> : null}
          </>) : null}
        </>);
      case "extras":
        return (<>
          <Text style={styles.label}>{t("drvSpecialNeeds")}</Text>
          <View style={styles.wrap}>{meta.special_needs.map((o: any) => (
            <Pressable key={o.id} testID={`drv-sp-${o.id}`} style={[styles.chip, special.includes(o.id) && styles.optOn]} onPress={() => toggleSpecial(o.id)}><Text style={[styles.optText, special.includes(o.id) && styles.optTextOn]}>{o[lang]}</Text></Pressable>))}</View>
          <View style={[styles.rowOpt, { marginTop: spacing.lg }]}><Text style={styles.optText}>🔁 {t("drvReturn")}</Text><Switch testID="drv-return" value={withReturn} onValueChange={setWithReturn} trackColor={{ true: colors.brand, false: colors.borderStrong }} thumbColor="#fff" /></View>
          {withReturn ? (<><Text style={styles.label}>{t("drvReturnWhen")}</Text><TimeField testID="drv-return-time" value={returnTime} onChange={setReturnTime} /></>) : null}
          <Text style={styles.label}>{t("notesOptional")}</Text>
          <TextInput testID="drv-note" style={[styles.input, { minHeight: 56, textAlignVertical: "top" }]} value={note} onChangeText={setNote} multiline placeholderTextColor={colors.muted} />
        </>);
      case "summary":
        return (<>
          <View style={styles.sumCard}>
            <Text style={styles.sumRow}>📍 {from?.label} → {to?.label}</Text>
            <Text style={styles.sumSub}>{date} {time}{flight ? ` · ✈️ ${flight}` : ""}</Text>
            <Text style={styles.sumSub}>{meta.vehicle_classes.find((c: any) => c.id === classe)?.[lang]} · {passengers}👤 · {luggage}🧳{withReturn ? " · 🔁" : ""}</Text>
            {est?.route ? <Text style={styles.sumSub}>{est.route.distance_km} {t("drvKm")} · ~{est.route.duration_min} {t("drvMin")}</Text> : null}
          </View>
          {tipo === "taxi" ? (
            <View style={styles.priceBox}>
              <Text style={styles.priceLabel}>{t("drvTaximeter")}</Text>
              <Text style={styles.priceVal}>~€{est?.estimate?.toFixed(2) || "—"}</Text>
              <Text style={styles.priceNote}>{t("drvTaxiSettleNote")}</Text>
            </View>
          ) : (
            <View style={styles.priceBox}>
              <Text style={styles.priceLabel}>{t("drvPriceRange")}</Text>
              <Text style={styles.priceVal}>{est?.min != null ? `€${est.min.toFixed(2)}${est.max && est.max !== est.min ? ` – €${est.max.toFixed(2)}` : ""}` : t("drvNoDriver")}</Text>
              {est?.providers ? <Text style={styles.priceNote}>{est.providers} driver</Text> : null}
            </View>
          )}
          <Text style={styles.cancelNote}>ℹ️ {t("drvCancelRules")}</Text>
          <Text style={styles.cancelNote}>🔒 {t("drvSharedRideNote")}</Text>
        </>);
    }
  };

  const isLast = step === STEPS.length - 1;
  const canNext = STEPS[step] === "route" ? !!(from && to) : true;
  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="drv-back" onPress={() => (step === 0 ? router.back() : setStep(step - 1))} hitSlop={12}><Ionicons name="arrow-back" size={24} color={colors.onSurface} /></Pressable>
        <Text style={styles.headerTitle}>{tipo === "taxi" ? "🚕" : "🚘"} {t("driver")}</Text>
        <View style={{ width: 24 }} />
      </View>
      <View style={styles.progress}>{STEPS.map((_, i) => (<View key={i} style={[styles.pBar, { backgroundColor: i <= step ? colors.brand : colors.border }]} />))}</View>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 140 }} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
          <Text style={styles.stepTitle}>{STEPS[step] === "tipo" ? t("drvTipoTitle") : STEPS[step] === "route" ? t("drvRoute") : STEPS[step] === "when" ? t("drvWhen") : STEPS[step] === "class" ? t("drvClass") : STEPS[step] === "people" ? t("drvWhoTravels") : STEPS[step] === "extras" ? t("drvSpecialNeeds") : t("drvSummary")}</Text>
          {renderStep()}
        </ScrollView>
        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          <Button testID={isLast ? "drv-publish" : "drv-next"} label={isLast ? t("publishRequest") : t("next")} loading={loading} onPress={() => (isLast ? submit() : (canNext ? setStep(step + 1) : Alert.alert(t("drvSearchPlace"))))} />
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

function Stepper({ value, setValue, min, max, testID }: { value: number; setValue: (v: number) => void; min: number; max: number; testID: string }) {
  return (
    <View style={styles.stepper}>
      <Pressable testID={`${testID}-minus`} style={styles.stepBtn} onPress={() => setValue(Math.max(min, value - 1))}><Ionicons name="remove" size={22} color={colors.onSurface} /></Pressable>
      <Text style={styles.stepVal}>{value}</Text>
      <Pressable testID={`${testID}-plus`} style={styles.stepBtn} onPress={() => setValue(Math.min(max, value + 1))}><Ionicons name="add" size={22} color={colors.onSurface} /></Pressable>
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
  hintMini: { fontSize: fsize.sm, color: colors.muted, fontFamily: font.regular, marginTop: 6 },
  input: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  searchRow: { flexDirection: "row", gap: spacing.sm },
  searchInput: { flex: 1, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface },
  searchBtn: { width: 50, borderRadius: radius.md, backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" },
  wpOk: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.success, marginTop: 6 },
  wpHint: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 6 },
  shortcutWrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.sm },
  shortcut: { paddingVertical: 6, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  shortcutText: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.onSurface },
  bigCard: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, marginBottom: spacing.md },
  cardTitle: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  cardDesc: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 2 },
  rowOpt: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: spacing.md, paddingHorizontal: spacing.lg, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, marginBottom: spacing.sm },
  optOn: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  optText: { fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  optTextOn: { color: colors.onBrandTertiary, fontFamily: font.medium },
  wrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: { paddingVertical: spacing.sm, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  row2: { flexDirection: "row", gap: spacing.md },
  segRow: { flexDirection: "row", gap: spacing.sm },
  seg: { flex: 1, paddingVertical: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, alignItems: "center", backgroundColor: colors.surfaceSecondary },
  segOn: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  segText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  segTextOn: { color: colors.onBrandTertiary },
  consentRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, marginTop: spacing.md },
  consentText: { flex: 1, fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface },
  stepper: { flexDirection: "row", alignItems: "center", alignSelf: "flex-start", backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  stepBtn: { width: 52, height: 52, alignItems: "center", justifyContent: "center" },
  stepVal: { fontSize: fsize.xl, fontFamily: font.medium, color: colors.onSurface, minWidth: 50, textAlign: "center" },
  sumCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.md },
  sumRow: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  sumSub: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 4 },
  priceBox: { backgroundColor: colors.brandTertiary, borderRadius: radius.lg, padding: spacing.lg, alignItems: "center", marginBottom: spacing.md },
  priceLabel: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onBrandTertiary },
  priceVal: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.brand, marginTop: 4 },
  priceNote: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.onSurfaceTertiary, marginTop: 6, textAlign: "center" },
  cancelNote: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: spacing.sm },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.lg, paddingTop: spacing.md, backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderTopColor: colors.divider },
});
