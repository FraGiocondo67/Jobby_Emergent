import React, { useCallback, useEffect, useMemo, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, KeyboardAvoidingView, Platform, ActivityIndicator, Switch } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Location from "expo-location";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Button } from "@/src/components/UI";
import { DateField, TimeField } from "@/src/components/DateTimeField";

const TREVISO = { lat: 45.6669, lng: 12.2433 };
const STEPS = ["home", "type", "extra", "products", "duration", "recurrence", "when", "details", "track"];

export default function PulizieConfigura() {
  const { lang, t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  // BLOCCO 9 (fix "richiesta diretta dalla mappa non arriva al
  // professionista scelto"): app/provider/[id].tsx passa ?provider=<id>
  // quando il cliente sceglie esplicitamente un professionista dalla mappa
  // — prima ignorato qui, il submit finiva sempre nell'auto-match generico.
  const { provider } = useLocalSearchParams<{ provider?: string }>();
  const [cfgMeta, setCfgMeta] = useState<any>(null);
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);

  const [homeType, setHomeType] = useState("appartamento");
  const [mqBand, setMqBand] = useState("80_120");
  const [tipo, setTipo] = useState("ordinaria");
  const [extra, setExtra] = useState<string[]>([]);
  const [stiroOre, setStiroOre] = useState(1);
  const [prodotti, setProdotti] = useState("cliente");
  const [durata, setDurata] = useState(3);
  const [ricorrenza, setRicorrenza] = useState("una_tantum");
  const [flessibilita, setFlessibilita] = useState("fascia");
  const [date, setDate] = useState("2026-07-25");
  const [time, setTime] = useState("10:00");
  const [address, setAddress] = useState("Via Roma 12, Treviso");
  const [coords, setCoords] = useState(TREVISO);
  const [note, setNote] = useState("");
  const [animali, setAnimali] = useState(false);
  const [parcheggio, setParcheggio] = useState("");
  const [binario, setBinario] = useState("impresa");
  const [est, setEst] = useState<any>(null);

  useEffect(() => { (async () => { try { setCfgMeta(await api.pulizieConfig()); } catch {} })(); }, []);

  const config = useMemo(() => ({
    home_type: homeType, mq_band: mqBand, tipo_pulizia: tipo, extra, stiro_ore: extra.includes("stiro") ? stiroOre : 0,
    prodotti, durata_ore: durata, animali,
  }), [homeType, mqBand, tipo, extra, stiroOre, prodotti, durata, animali]);

  // live estimate from step 1 onward
  const loadEstimate = useCallback(async () => {
    try {
      const r = await api.pulizieEstimate({ binario, ricorrenza, lat: coords.lat, lng: coords.lng, config });
      setEst(r);
    } catch {}
  }, [binario, ricorrenza, coords, config]);

  useEffect(() => { if (cfgMeta && step >= 1) loadEstimate(); }, [cfgMeta, step, loadEstimate]);

  // auto-fill recommended hours when band/type change
  useEffect(() => {
    if (cfgMeta?.ore_table) {
      const rec = cfgMeta.ore_table[mqBand]?.[tipo];
      if (rec) setDurata(rec);
    }
  }, [mqBand, tipo, cfgMeta]);

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

  const toggleExtra = (id: string) => setExtra((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);

  const submit = async () => {
    setLoading(true);
    try {
      const c = await resolveCoords();
      const r = await api.createRichiesta({
        binario, config, indirizzo: address, lat: c.lat, lng: c.lng,
        data_ora: `${date} ${time}`, flessibilita, ricorrenza,
        note, parcheggio, publish: true,
        ...(provider ? { provider_id: provider } : {}),
      });
      router.replace(`/pulizie/${r.richiesta_id}?new=1`);
    } catch { setLoading(false); }
  };

  if (!cfgMeta) return <View style={[styles.container, { alignItems: "center", justifyContent: "center" }]}><ActivityIndicator color={colors.brand} /></View>;

  const lbl = (arr: any[], id: string) => { const o = arr.find((x: any) => x.id === id); return o ? o[lang] : id; };
  const range = est?.ranges?.[binario];

  const renderStep = () => {
    switch (STEPS[step]) {
      case "home":
        return (<>
          <Text style={styles.label}>{t("homeType")}</Text>
          <View style={styles.wrap}>{cfgMeta.home_types.map((o: any) => (
            <Pressable key={o.id} testID={`home-${o.id}`} style={[styles.opt, homeType === o.id && styles.optOn]} onPress={() => setHomeType(o.id)}>
              <Text style={[styles.optText, homeType === o.id && styles.optTextOn]}>{o[lang]}</Text>
            </Pressable>))}</View>
          <Text style={styles.label}>{t("surface")}</Text>
          <View style={styles.wrap}>{cfgMeta.mq_bands.map((o: any) => (
            <Pressable key={o.id} testID={`mq-${o.id}`} style={[styles.opt, mqBand === o.id && styles.optOn]} onPress={() => setMqBand(o.id)}>
              <Text style={[styles.optText, mqBand === o.id && styles.optTextOn]}>{o[lang]}</Text>
            </Pressable>))}</View>
        </>);
      case "type":
        return (<>
          {cfgMeta.tipi_pulizia.map((o: any) => (
            <Pressable key={o.id} testID={`tipo-${o.id}`} style={[styles.cardOpt, tipo === o.id && styles.optOn]} onPress={() => setTipo(o.id)}>
              <Text style={[styles.cardTitle, tipo === o.id && styles.optTextOn]}>{o[lang]}</Text>
              <Text style={styles.cardDesc}>{o[`desc_${lang}`]}</Text>
            </Pressable>))}
        </>);
      case "extra":
        return (<>
          <Text style={styles.hint}>{t("extraHint")}</Text>
          {cfgMeta.extra_items.map((o: any) => (
            <Pressable key={o.id} testID={`extra-${o.id}`} style={[styles.rowOpt, extra.includes(o.id) && styles.optOn]} onPress={() => toggleExtra(o.id)}>
              <Text style={[styles.optText, extra.includes(o.id) && styles.optTextOn]}>{o[lang]}</Text>
              <Ionicons name={extra.includes(o.id) ? "checkbox" : "square-outline"} size={22} color={extra.includes(o.id) ? colors.brand : colors.muted} />
            </Pressable>))}
          <Pressable testID="extra-stiro" style={[styles.rowOpt, extra.includes("stiro") && styles.optOn]} onPress={() => toggleExtra("stiro")}>
            <Text style={[styles.optText, extra.includes("stiro") && styles.optTextOn]}>👕 {t("ironing")}</Text>
            <Ionicons name={extra.includes("stiro") ? "checkbox" : "square-outline"} size={22} color={extra.includes("stiro") ? colors.brand : colors.muted} />
          </Pressable>
          {extra.includes("stiro") ? (
            <View style={{ marginTop: spacing.md }}>
              <Text style={styles.label}>{t("ironingHours")}</Text>
              <Stepper value={stiroOre} setValue={setStiroOre} min={1} max={3} testID="stiro" />
            </View>) : null}
        </>);
      case "products":
        return (<>
          {[["cliente", t("productsClient")], ["provider", t("productsProvider")]].map(([id, label]) => (
            <Pressable key={id} testID={`prod-${id}`} style={[styles.cardOpt, prodotti === id && styles.optOn]} onPress={() => setProdotti(id as string)}>
              <Text style={[styles.cardTitle, prodotti === id && styles.optTextOn]}>{label}</Text>
            </Pressable>))}
        </>);
      case "duration":
        return (<>
          <Text style={styles.hint}>{t("durationHint")} {cfgMeta.ore_table[mqBand]?.[tipo] ?? 3}h</Text>
          <Stepper value={durata} setValue={setDurata} min={1} max={10} testID="durata" suffix="h" />
        </>);
      case "recurrence":
        return (<>
          {cfgMeta.ricorrenze.map((o: any) => (
            <Pressable key={o.id} testID={`ric-${o.id}`} style={[styles.rowOpt, ricorrenza === o.id && styles.optOn]} onPress={() => setRicorrenza(o.id)}>
              <View><Text style={[styles.optText, ricorrenza === o.id && styles.optTextOn]}>{o[lang]}</Text>
              {o.sconto ? <Text style={styles.discount}>{t("recurrenceDiscount")}</Text> : null}</View>
              {ricorrenza === o.id ? <Ionicons name="checkmark-circle" size={22} color={colors.brand} /> : null}
            </Pressable>))}
          {cfgMeta.ricorrenze.find((o: any) => o.id === ricorrenza)?.sconto ? (
            <Text style={styles.antiHelpling}>✅ {t("noCommitment")}</Text>) : null}
        </>);
      case "when":
        return (<>
          <Text style={styles.label}>{t("flexibility")}</Text>
          {cfgMeta.flessibilita.map((o: any) => (
            <Pressable key={o.id} testID={`flex-${o.id}`} style={[styles.rowOpt, flessibilita === o.id && styles.optOn]} onPress={() => setFlessibilita(o.id)}>
              <Text style={[styles.optText, flessibilita === o.id && styles.optTextOn]}>{o[lang]}</Text>
              {flessibilita === o.id ? <Ionicons name="checkmark-circle" size={22} color={colors.brand} /> : null}
            </Pressable>))}
          <Text style={styles.flexTip}>💡 {t("flexTip")}</Text>
          <View style={styles.row2}>
            <View style={{ flex: 1 }}><Text style={styles.label}>{t("date")}</Text><DateField testID="date-input" value={date} onChange={setDate} lang={lang} /></View>
            <View style={{ flex: 1 }}><Text style={styles.label}>{t("time")}</Text><TimeField testID="time-input" value={time} onChange={setTime} /></View>
          </View>
        </>);
      case "details":
        return (<>
          <Text style={styles.label}>{t("address")}</Text>
          <TextInput testID="address-input" style={styles.input} value={address} onChangeText={setAddress} placeholderTextColor={colors.muted} />
          <Button label={t("useMyLocation")} variant="secondary" icon="navigate" onPress={useMyLocation} testID="use-location-button" style={{ marginTop: spacing.md, height: 46 }} />
          <Text style={styles.label}>{t("parking")}</Text>
          <TextInput testID="parking-input" style={styles.input} value={parcheggio} onChangeText={setParcheggio} placeholder={t("parkingPh")} placeholderTextColor={colors.muted} />
          <Text style={styles.label}>{t("notesOptional")}</Text>
          <TextInput testID="note-input" style={[styles.input, { minHeight: 70, textAlignVertical: "top" }]} value={note} onChangeText={setNote} placeholder={t("notesPh")} placeholderTextColor={colors.muted} multiline />
          <View style={[styles.rowOpt, { marginTop: spacing.md }]}>
            <Text style={styles.optText}>🐾 {t("pets")}</Text>
            <Switch testID="pets-switch" value={animali} onValueChange={setAnimali} trackColor={{ true: colors.brand, false: colors.borderStrong }} thumbColor="#fff" />
          </View>
        </>);
      case "track":
        return (<>
          <Text style={styles.hint}>{t("chooseTrack")}</Text>
          {cfgMeta.binari.map((o: any) => {
            const r = est?.ranges?.[o.id];
            return (
              <Pressable key={o.id} testID={`track-${o.id}`} style={[styles.trackCard, binario === o.id && styles.optOn]} onPress={() => setBinario(o.id)}>
                <View style={styles.rowBetween}>
                  <Text style={[styles.cardTitle, binario === o.id && styles.optTextOn]}>{o[lang]}</Text>
                  {binario === o.id ? <Ionicons name="checkmark-circle" size={22} color={colors.brand} /> : null}
                </View>
                <Text style={styles.cardDesc}>{o[`desc_${lang}`]}</Text>
                <Text style={styles.trackPrice}>{r?.min != null ? `${t("fromLabel")} €${r.min.toFixed(2)}` : t("noProviderZone")}{r?.providers ? ` · ${r.providers} ${t("providersLabel")}` : ""}</Text>
              </Pressable>);
          })}
        </>);
    }
  };

  const isLast = step === STEPS.length - 1;
  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="pulizie-back" onPress={() => (step === 0 ? router.back() : setStep(step - 1))} hitSlop={12}>
          <Ionicons name="arrow-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>🧹 {t("cleaning")}</Text>
        <View style={{ width: 24 }} />
      </View>
      <View style={styles.progress}>{STEPS.map((_, i) => (<View key={i} style={[styles.pBar, { backgroundColor: i <= step ? colors.brand : colors.border }]} />))}</View>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 160 }} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
          <Text style={styles.stepTitle}>{t(`pStep_${STEPS[step]}` as any)}</Text>
          {renderStep()}
        </ScrollView>

        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          {step >= 1 && range ? (
            <Text style={styles.estLine}>{range.min != null ? `${t("estimate")}: €${range.min.toFixed(2)}${range.max && range.max !== range.min ? `–${range.max.toFixed(2)}` : ""}` : t("noProviderZone")}</Text>
          ) : null}
          <Button testID={isLast ? "publish-button" : "next-button"} label={isLast ? t("publishRequest") : t("next")} loading={loading} onPress={() => (isLast ? submit() : setStep(step + 1))} />
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

function Stepper({ value, setValue, min, max, testID, suffix = "" }: { value: number; setValue: (n: number) => void; min: number; max: number; testID: string; suffix?: string }) {
  return (
    <View style={styles.stepper}>
      <Pressable testID={`${testID}-minus`} style={styles.stepBtn} onPress={() => setValue(Math.max(min, value - 1))}><Ionicons name="remove" size={22} color={colors.onSurface} /></Pressable>
      <Text style={styles.stepVal} testID={`${testID}-value`}>{value}{suffix}</Text>
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
  label: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary, marginTop: spacing.lg, marginBottom: spacing.sm },
  hint: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginBottom: spacing.md },
  wrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  opt: { paddingVertical: spacing.md, paddingHorizontal: spacing.lg, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  optOn: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  optText: { fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  optTextOn: { color: colors.onBrandTertiary, fontFamily: font.medium },
  cardOpt: { padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, marginBottom: spacing.md },
  cardTitle: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  cardDesc: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 4 },
  rowOpt: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: spacing.md, paddingHorizontal: spacing.lg, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, marginBottom: spacing.sm },
  rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  discount: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.success, marginTop: 2 },
  antiHelpling: { fontSize: fsize.base, fontFamily: font.medium, color: colors.success, marginTop: spacing.md },
  flexTip: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: spacing.sm },
  trackCard: { padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, marginBottom: spacing.md, gap: 4 },
  trackPrice: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.brand, marginTop: spacing.sm },
  input: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  row2: { flexDirection: "row", gap: spacing.md },
  stepper: { flexDirection: "row", alignItems: "center", alignSelf: "flex-start", backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  stepBtn: { width: 52, height: 52, alignItems: "center", justifyContent: "center" },
  stepVal: { fontSize: fsize.xl, fontFamily: font.medium, color: colors.onSurface, minWidth: 60, textAlign: "center" },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.lg, paddingTop: spacing.md, backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderTopColor: colors.divider },
  estLine: { fontSize: fsize.base, fontFamily: font.bold, color: colors.brand, textAlign: "center", marginBottom: spacing.sm },
});
