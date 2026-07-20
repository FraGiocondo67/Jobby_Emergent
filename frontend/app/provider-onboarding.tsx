import React, { useEffect, useMemo, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, KeyboardAvoidingView, Platform, Alert, Linking } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as ImagePicker from "expo-image-picker";
import * as Location from "expo-location";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Button } from "@/src/components/UI";
import { DateField } from "@/src/components/DateTimeField";

const TREVISO = { lat: 45.6669, lng: 12.2433 };
const PROFILES = [
  { id: "impresa", emoji: "🏢", tKey: "profImpresa", dKey: "profImpresaDesc" },
  { id: "piva", emoji: "🧾", tKey: "profPiva", dKey: "profPivaDesc" },
  { id: "persona_lf", emoji: "🧍", tKey: "profLF", dKey: "profLFDesc" },
];
const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const SLOTS = ["morning", "afternoon", "evening"];

export default function ProviderOnboarding() {
  const { user, setUser } = useAuth();
  const { lang, t } = useLang();
  const router = useRouter();
  const params = useLocalSearchParams<{ role?: string }>();
  const insets = useSafeAreaInsets();

  // Ruolo scelto dall'utente prima di arrivare qui (Professionista vs Attività).
  const intendedRole: "provider" | "business" =
    params.role === "business" ? "business" : params.role === "provider" ? "provider" : (user?.role === "business" ? "business" : "provider");

  const [cfg, setCfg] = useState<any>(null);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [profileType, setProfileType] = useState("");
  const [allCats, setAllCats] = useState<any[]>([]);
  const [activityCats, setActivityCats] = useState<string[]>(user?.services || []);
  const [dob, setDob] = useState("1990-01-01");
  const [email, setEmail] = useState(user?.email || "");
  const [otpSent, setOtpSent] = useState(false);
  const [code, setCode] = useState("");
  const [emailVerified, setEmailVerified] = useState(false);
  const [name, setName] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [vat, setVat] = useState("");
  const [cf, setCf] = useState("");
  const [address, setAddress] = useState("");
  const [coords, setCoords] = useState(TREVISO);
  const [iban, setIban] = useState("");
  const [bio, setBio] = useState("");
  const [condizione, setCondizione] = useState("nessuna");
  const [docs, setDocs] = useState<Record<string, string>>({});
  const [delegaName, setDelegaName] = useState("");
  const [delegaSigned, setDelegaSigned] = useState(false);
  const [avail, setAvail] = useState<Record<string, Record<string, boolean>>>({});

  useEffect(() => { (async () => { try { setCfg(await api.onbConfig()); } catch {} })(); }, []);

  // Categorie selezionabili: Professionista → solo standard; Attività → prossimità + standard.
  useEffect(() => {
    (async () => {
      try {
        const c = await api.categories();
        setAllCats(intendedRole === "business" ? [...(c.proximity || []), ...(c.standard || [])] : (c.standard || []));
      } catch {}
    })();
  }, [intendedRole]);

  const isLF = profileType === "persona_lf";
  const steps = useMemo(() => (
    isLF
      ? ["intro", "email", "lf_edu", "data", "attivita", "docs", "lf_delega", "availability", "fee", "submit"]
      : ["intro", "email", "data", "attivita", "docs", "availability", "fee", "submit"]
  ), [isLF]);
  const cur = steps[step];

  const pickImage = async (useCamera: boolean): Promise<string | null> => {
    const perm = useCamera ? await ImagePicker.requestCameraPermissionsAsync() : await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      Alert.alert(t("permissionNeeded"), "", [{ text: "OK" }, { text: t("openSettings"), onPress: () => Linking.openSettings() }]);
      return null;
    }
    const res = useCamera
      ? await ImagePicker.launchCameraAsync({ quality: 0.35, base64: true })
      : await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, quality: 0.35, base64: true });
    if (res.canceled || !res.assets?.[0]?.base64) return null;
    return `data:image/jpeg;base64,${res.assets[0].base64}`;
  };

  const uploadDoc = async (kind: string, useCamera = true) => {
    const img = await pickImage(useCamera);
    if (!img) return;
    try { await api.uploadProviderDoc(kind, img); setDocs((d) => ({ ...d, [kind]: img })); } catch { Alert.alert(t("error")); }
  };

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

  const isAdult = (() => { try { const d = new Date(dob); const n = new Date(); let a = n.getFullYear() - d.getFullYear(); if (n.getMonth() < d.getMonth() || (n.getMonth() === d.getMonth() && n.getDate() < d.getDate())) a--; return a >= 18; } catch { return false; } })();

  const sendOtp = async () => {
    if (!email.trim() || !email.includes("@")) { Alert.alert(t("invalidEmailMsg")); return; }
    setBusy(true);
    // #3 — verifica email disattivata: l'endpoint auto-verifica subito.
    try {
      const r = await api.sendOtp(email.trim());
      if (r?.auto_verified) { setEmailVerified(true); }
      else { setOtpSent(true); Alert.alert(t("otpSent")); }
    }
    catch { Alert.alert(t("error"), t("otpError")); }
    finally { setBusy(false); }
  };
  const verifyOtp = async () => {
    setBusy(true);
    try { await api.verifyOtp(email.trim(), code.trim()); setEmailVerified(true); }
    catch { Alert.alert(t("otpInvalid")); } finally { setBusy(false); }
  };

  const saveProfile = async () => {
    setBusy(true);
    try {
      const c = await resolveCoords();
      await api.setProviderProfile({
        profile_type: profileType, dob, name: name.trim() || businessName.trim(),
        role: intendedRole,
        business_name: businessName.trim() || undefined, vat_number: vat.trim() || undefined,
        codice_fiscale: cf.trim() || undefined, address: address.trim() || undefined,
        lat: c.lat, lng: c.lng, iban: iban.trim() || undefined, bio: bio.trim() || undefined,
        condizione_soggettiva: isLF ? condizione : undefined,
      });
      return true;
    } catch (e: any) {
      if (String(e?.message).includes("minor")) Alert.alert(t("minorBlocked"));
      else Alert.alert(t("error"));
      return false;
    } finally { setBusy(false); }
  };

  const signDelega = async () => {
    if (!delegaName.trim()) return;
    setBusy(true);
    try { await api.signDelega(delegaName.trim()); await api.setInps(false); setDelegaSigned(true); }
    catch { Alert.alert(t("error")); } finally { setBusy(false); }
  };

  const toggleSlot = (day: string, slot: string) => setAvail((a) => ({ ...a, [day]: { ...(a[day] || {}), [slot]: !(a[day]?.[slot]) } }));

  const saveAvailability = async () => { try { await api.setAvailability(avail); } catch {} };

  const submit = async () => {
    setBusy(true);
    try {
      await saveAvailability();
      const u = await api.submitProvider();
      setUser(u);
      router.replace("/(tabs)");
    } catch (e: any) {
      if (String(e?.message).includes("email_not_verified")) Alert.alert(t("otpInvalid"));
      else Alert.alert(t("error"));
      setBusy(false);
    }
  };

  const toggleActivity = (id: string) => {
    setActivityCats((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };
  const saveActivities = async () => { try { const u = await api.updateProfile({ services: activityCats }); setUser(u); } catch {} };

  const next = async () => {
    if (cur === "intro") { if (!profileType) return; if (!isAdult) { Alert.alert(t("minorBlocked")); return; } }
    if (cur === "email" && !emailVerified) { Alert.alert(t("verifyEmailFirst")); return; }
    if (cur === "data") { const ok = await saveProfile(); if (!ok) return; }
    if (cur === "attivita") { if (activityCats.length === 0) { Alert.alert(t("selectAtLeastOne")); return; } await saveActivities(); }
    if (cur === "lf_delega" && !delegaSigned) { Alert.alert(t("signDelegaFirst")); return; }
    if (cur === "availability") await saveAvailability();
    if (cur === "submit") { await submit(); return; }
    setStep(step + 1);
  };

  if (!cfg) return <View style={styles.container} />;
  const fee = cfg.fee; const ranges = cfg.price_ranges;

  const renderStep = () => {
    switch (cur) {
      case "intro":
        return (<>
          <Text style={styles.h}>{t("howDoYouWork")}</Text>
          {PROFILES.map((p) => (
            <Pressable key={p.id} testID={`prof-${p.id}`} style={[styles.card, profileType === p.id && styles.cardOn]} onPress={() => setProfileType(p.id)}>
              <Text style={{ fontSize: 30 }}>{p.emoji}</Text>
              <View style={{ flex: 1 }}><Text style={styles.cardTitle}>{t(p.tKey as any)}</Text><Text style={styles.cardDesc}>{t(p.dKey as any)}</Text></View>
              {profileType === p.id ? <Ionicons name="checkmark-circle" size={24} color={colors.brand} /> : null}
            </Pressable>))}
          <Text style={styles.label}>{t("dob")}</Text>
          <DateField testID="dob-input" value={dob} onChange={setDob} lang={lang} />
          {!isAdult ? <Text style={styles.warn}>⚠️ {t("minorBlocked")}</Text> : null}
        </>);
      case "email":
        return (<>
          <Text style={styles.h}>{t("verifyEmail")}</Text>
          <Text style={styles.sub}>{t("verifyEmailSub")}</Text>
          <Text style={styles.label}>{t("emailLabel")}</Text>
          <TextInput testID="email-input" style={styles.input} value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" autoCorrect={false} placeholder="nome@esempio.it" placeholderTextColor={colors.muted} editable={!emailVerified} />
          {!emailVerified ? (
            <>
              <Button testID="send-otp" label={otpSent ? t("resendOtp") : t("sendOtp")} variant={otpSent ? "secondary" : "primary"} loading={busy} onPress={sendOtp} style={{ marginTop: spacing.md }} />
              {otpSent ? (<>
                <Text style={styles.label}>{t("enterCode")}</Text>
                <TextInput testID="otp-input" style={styles.input} value={code} onChangeText={setCode} keyboardType="number-pad" maxLength={6} placeholder="123456" placeholderTextColor={colors.muted} />
                <Button testID="verify-otp" label={t("verify")} loading={busy} onPress={verifyOtp} style={{ marginTop: spacing.md }} />
              </>) : null}
            </>
          ) : (<View style={styles.okRow}><Ionicons name="checkmark-circle" size={22} color={colors.success} /><Text style={styles.okText}>{t("emailVerified")}</Text></View>)}
        </>);
      case "lf_edu":
        return (<>
          <Text style={styles.h}>{t("lfEduTitle")}</Text>
          {["lfEdu1", "lfEdu2", "lfEdu3", "lfEdu4"].map((k, i) => (
            <View key={k} style={styles.eduRow}><Text style={styles.eduNum}>{i + 1}</Text><Text style={styles.eduText}>{t(k as any)}</Text></View>))}
          <Text style={styles.highlight}>💶 {t("lfPayTiming")}</Text>
        </>);
      case "data":
        return (<>
          <Text style={styles.h}>{t("yourData")}</Text>
          {profileType === "impresa" ? (<>
            <Text style={styles.label}>{t("businessNameLabel")}</Text>
            <TextInput testID="d-bizname" style={styles.input} value={businessName} onChangeText={setBusinessName} placeholderTextColor={colors.muted} />
          </>) : (<>
            <Text style={styles.label}>{t("nameLabel")}</Text>
            <TextInput testID="d-name" style={styles.input} value={name} onChangeText={setName} placeholderTextColor={colors.muted} />
          </>)}
          {profileType !== "persona_lf" ? (<>
            <Text style={styles.label}>{t("vatNumber")}</Text>
            <TextInput testID="d-vat" style={styles.input} value={vat} onChangeText={setVat} autoCapitalize="characters" placeholder="IT..." placeholderTextColor={colors.muted} />
          </>) : null}
          {profileType !== "impresa" ? (<>
            <Text style={styles.label}>{t("codiceFiscale")}</Text>
            <TextInput testID="d-cf" style={styles.input} value={cf} onChangeText={setCf} autoCapitalize="characters" placeholderTextColor={colors.muted} />
          </>) : null}
          <Text style={styles.label}>{t("addressLabel")}</Text>
          <TextInput testID="d-address" style={styles.input} value={address} onChangeText={setAddress} placeholder="Via Roma 12, Treviso" placeholderTextColor={colors.muted} />
          <Button label={t("useMyLocation")} variant="secondary" icon="navigate" onPress={useMyLocation} style={{ marginTop: spacing.sm, height: 46 }} />
          <Text style={styles.label}>{t("ibanLabel")}</Text>
          <TextInput testID="d-iban" style={styles.input} value={iban} onChangeText={setIban} autoCapitalize="characters" placeholder="IT60 X054 ..." placeholderTextColor={colors.muted} />
          {isLF ? <Text style={styles.note}>{t("ibanLFNote")}</Text> : null}
          {isLF ? (<>
            <Text style={styles.label}>{t("condizione")}</Text>
            {cfg.condizioni.map((o: any) => (
              <Pressable key={o.id} testID={`cond-${o.id}`} style={[styles.rowOpt, condizione === o.id && styles.cardOn]} onPress={() => setCondizione(o.id)}>
                <Text style={styles.optText}>{o[lang]}</Text>
                {condizione === o.id ? <Ionicons name="checkmark-circle" size={20} color={colors.brand} /> : null}
              </Pressable>))}
          </>) : (<>
            <Text style={styles.label}>{t("presentation")}</Text>
            <TextInput testID="d-bio" style={[styles.input, { minHeight: 80, textAlignVertical: "top" }]} value={bio} onChangeText={setBio} placeholder={t("presentationExample")} placeholderTextColor={colors.muted} multiline />
          </>)}
        </>);
      case "attivita":
        return (<>
          <Text style={styles.h}>{t("whichActivities")}</Text>
          <Text style={styles.sub}>{intendedRole === "business" ? t("whichActivitiesBizSub") : t("whichActivitiesProSub")}</Text>
          <View style={styles.actGrid}>
            {allCats.map((c) => {
              const on = activityCats.includes(c.cat_id);
              return (
                <Pressable key={c.cat_id} testID={`onb-activity-${c.cat_id}`} style={[styles.actChip, on && styles.actChipOn]} onPress={() => toggleActivity(c.cat_id)}>
                  <Text style={{ fontSize: 22 }}>{c.emoji}</Text>
                  <Text style={[styles.actChipText, on && { color: "#fff" }]}>{c.label[lang]}</Text>
                  {on ? <Ionicons name="checkmark-circle" size={16} color="#fff" /> : null}
                </Pressable>
              );
            })}
          </View>
        </>);
      case "docs":
        return (<>
          <Text style={styles.h}>{t("documents")}</Text>
          <Text style={styles.sub}>{t("docsSub")}</Text>
          <DocBox testID="doc-id_front" label={t("idFront")} done={!!docs.id_front} onPress={() => uploadDoc("id_front")} />
          <DocBox testID="doc-id_back" label={t("idBack")} done={!!docs.id_back} onPress={() => uploadDoc("id_back")} />
          <DocBox testID="doc-selfie" label={t("selfieDoc")} done={!!docs.selfie} onPress={() => uploadDoc("selfie")} />
          {!isLF ? <DocBox testID="doc-presentation" label={t("logoPhoto")} done={!!docs.presentation} onPress={() => uploadDoc("presentation", false)} /> : null}
        </>);
      case "lf_delega":
        return (<>
          <Text style={styles.h}>{t("delegaTitle")}</Text>
          <Text style={styles.sub}>{t("delegaSub")}</Text>
          <View style={styles.delegaBox}><Text style={styles.delegaText}>{t("delegaText")}</Text></View>
          <Text style={styles.label}>{t("signHere")}</Text>
          <TextInput testID="delega-name" style={styles.input} value={delegaName} onChangeText={setDelegaName} placeholder={t("typeFullName")} placeholderTextColor={colors.muted} editable={!delegaSigned} />
          {!delegaSigned ? (
            <Button testID="sign-delega" label={t("signAccept")} loading={busy} onPress={signDelega} style={{ marginTop: spacing.md }} />
          ) : (<>
            <View style={styles.okRow}><Ionicons name="checkmark-circle" size={20} color={colors.success} /><Text style={styles.okText}>{t("delegaSigned")}</Text></View>
            <View style={styles.inpsBox}>
              <Ionicons name="information-circle" size={22} color={colors.warning} />
              <Text style={styles.inpsText}>{t("inpsGuided")}</Text>
            </View>
          </>)}
        </>);
      case "availability":
        return (<>
          <Text style={styles.h}>{t("availabilityTitle")}</Text>
          <Text style={styles.sub}>{t("availabilitySub")}</Text>
          <View style={styles.availHead}><View style={{ width: 48 }} />{SLOTS.map((s) => <Text key={s} style={styles.availSlotHead}>{t(`slot_${s}` as any)}</Text>)}</View>
          {DAYS.map((d) => (
            <View key={d} style={styles.availRow}>
              <Text style={styles.availDay}>{t(`day_${d}` as any)}</Text>
              {SLOTS.map((s) => (
                <Pressable key={s} testID={`av-${d}-${s}`} style={[styles.availCell, avail[d]?.[s] && styles.availCellOn]} onPress={() => toggleSlot(d, s)}>
                  {avail[d]?.[s] ? <Ionicons name="checkmark" size={16} color="#fff" /> : null}
                </Pressable>))}
            </View>))}
        </>);
      case "fee":
        return (<>
          <Text style={styles.h}>{t("feeTitle")}</Text>
          <View style={[styles.feeCard, shadow.card]}>
            <Text style={styles.feeBig}>€{fee.provider_share.toFixed(2)}</Text>
            <Text style={styles.feeSub}>{t("feePerVisit")}</Text>
            <View style={styles.feeDivider} />
            <FeePoint icon="close-circle-outline" text={t("feeNoSubscription")} />
            <FeePoint icon="close-circle-outline" text={t("feeNoRejectCost")} />
            <FeePoint icon="trending-down-outline" text={`${t("feeRecurring")} €${fee.recurring_total.toFixed(2)}`} />
          </View>
          <View style={styles.rangeBox}>
            <Text style={styles.rangeTitle}>{t("suggestedRanges")}</Text>
            {["ordinaria", "afondo", "posttrasloco"].map((k) => (
              <Text key={k} style={styles.rangeText}>{t(`tipo_${k}` as any)}: €{ranges[k]?.min}–{ranges[k]?.max}/h</Text>))}
          </View>
        </>);
      case "submit":
        return (<>
          <Text style={styles.h}>{t("almostDone")}</Text>
          <Text style={styles.sub}>{t("submitReviewNote")}</Text>
          {isLF ? <Text style={styles.highlight}>💶 {t("lfCeilings")}</Text> : null}
          <View style={styles.summaryBox}>
            <Text style={styles.summaryRow}>✓ {t(PROFILES.find((p) => p.id === profileType)?.tKey as any)}</Text>
            <Text style={styles.summaryRow}>✓ {t("emailVerified")}</Text>
            <Text style={styles.summaryRow}>✓ {t("documents")}</Text>
            {isLF ? <Text style={styles.summaryRow}>✓ {t("delegaSigned")}</Text> : null}
          </View>
        </>);
    }
  };

  return (
    <View style={styles.container} testID="provider-onboarding">
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="onb-back" onPress={() => (step === 0 ? router.back() : setStep(step - 1))} hitSlop={12}><Ionicons name="arrow-back" size={24} color={colors.onSurface} /></Pressable>
        <View style={styles.progressBar}>{steps.map((_, i) => <View key={i} style={[styles.pDot, { backgroundColor: i <= step ? colors.brand : colors.border }]} />)}</View>
        <View style={{ width: 24 }} />
      </View>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 140 }} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>{renderStep()}</ScrollView>
        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          <Button testID="onb-next" label={cur === "submit" ? t("submitForReview") : t("next")} loading={busy} onPress={next} />
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

function DocBox({ label, done, onPress, testID }: { label: string; done: boolean; onPress: () => void; testID: string }) {
  return (
    <Pressable testID={testID} style={[styles.docBox, done && styles.docBoxOn]} onPress={onPress}>
      <Ionicons name={done ? "checkmark-circle" : "camera-outline"} size={22} color={done ? colors.success : colors.brand} />
      <Text style={[styles.docText, done && { color: colors.success }]}>{label}</Text>
    </Pressable>
  );
}
function FeePoint({ icon, text }: { icon: any; text: string }) {
  return <View style={styles.feePoint}><Ionicons name={icon} size={18} color={colors.brand} /><Text style={styles.feePointText}>{text}</Text></View>;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  progressBar: { flex: 1, flexDirection: "row", gap: 4 },
  pDot: { flex: 1, height: 4, borderRadius: 2 },
  h: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface, marginBottom: spacing.sm },
  sub: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginBottom: spacing.md },
  label: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary, marginTop: spacing.lg, marginBottom: spacing.sm },
  input: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  note: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 4, fontStyle: "italic" },
  warn: { fontSize: fsize.base, fontFamily: font.medium, color: colors.error, marginTop: spacing.md },
  card: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1.5, borderColor: colors.border, padding: spacing.lg, marginBottom: spacing.md },
  cardOn: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  cardTitle: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  cardDesc: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 2 },
  rowOpt: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: spacing.md, paddingHorizontal: spacing.lg, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, marginBottom: spacing.sm },
  optText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface },
  okRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.md },
  okText: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.success },
  eduRow: { flexDirection: "row", gap: spacing.md, marginBottom: spacing.md, alignItems: "flex-start" },
  eduNum: { width: 26, height: 26, borderRadius: 13, backgroundColor: colors.brand, color: "#fff", textAlign: "center", lineHeight: 26, fontFamily: font.bold, fontSize: fsize.base },
  eduText: { flex: 1, fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface, lineHeight: 21 },
  highlight: { fontSize: fsize.base, fontFamily: font.bold, color: colors.brand, backgroundColor: colors.brandTertiary, padding: spacing.md, borderRadius: radius.md, marginTop: spacing.md },
  docBox: { flexDirection: "row", alignItems: "center", gap: spacing.md, borderWidth: 1.5, borderStyle: "dashed", borderColor: colors.brand, borderRadius: radius.md, padding: spacing.lg, backgroundColor: colors.brandTertiary, marginBottom: spacing.md },
  docBoxOn: { borderColor: colors.success, backgroundColor: colors.greenBg, borderStyle: "solid" },
  docText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.brand },
  delegaBox: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.lg, borderWidth: 1, borderColor: colors.border },
  delegaText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurfaceTertiary, lineHeight: 20 },
  inpsBox: { flexDirection: "row", gap: spacing.sm, backgroundColor: "#FDF0DD", borderRadius: radius.md, padding: spacing.md, marginTop: spacing.md, alignItems: "flex-start" },
  inpsText: { flex: 1, fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface, lineHeight: 20 },
  availHead: { flexDirection: "row", alignItems: "center", marginBottom: spacing.sm },
  availSlotHead: { flex: 1, textAlign: "center", fontSize: fsize.sm, fontFamily: font.medium, color: colors.muted },
  availRow: { flexDirection: "row", alignItems: "center", marginBottom: spacing.sm },
  availDay: { width: 48, fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  availCell: { flex: 1, height: 40, marginHorizontal: 3, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  availCellOn: { backgroundColor: colors.brand, borderColor: colors.brand },
  feeCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.xl, alignItems: "center" },
  feeBig: { fontSize: 44, fontFamily: font.bold, color: colors.brand },
  feeSub: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted },
  feeDivider: { height: 1, backgroundColor: colors.divider, alignSelf: "stretch", marginVertical: spacing.lg },
  feePoint: { flexDirection: "row", alignItems: "center", gap: spacing.sm, alignSelf: "stretch", marginBottom: spacing.sm },
  feePointText: { flex: 1, fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  rangeBox: { marginTop: spacing.lg, padding: spacing.lg, backgroundColor: colors.brandTertiary, borderRadius: radius.md },
  rangeTitle: { fontSize: fsize.sm, fontFamily: font.bold, color: colors.brand, textTransform: "uppercase", marginBottom: spacing.sm },
  rangeText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface, marginBottom: 2 },
  almostDone: {},
  summaryBox: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.lg, marginTop: spacing.md, gap: spacing.sm },
  summaryRow: { fontSize: fsize.base, fontFamily: font.medium, color: colors.success },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.lg, paddingTop: spacing.md, backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderTopColor: colors.divider },
  actGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.sm },
  actChip: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  actChipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  actChipText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
});
