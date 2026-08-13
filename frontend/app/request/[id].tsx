import React, { useEffect, useMemo, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput, KeyboardAvoidingView, Platform, Alert,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Location from "expo-location";
import * as Haptics from "expo-haptics";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Button } from "@/src/components/UI";
import { DateField, TimeField } from "@/src/components/DateTimeField";

const TREVISO = { lat: 45.6669, lng: 12.2433 };

export default function RequestScreen() {
  const { id, type } = useLocalSearchParams<{ id: string; type: string }>();
  const { lang, t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [cat, setCat] = useState<any>(null);
  const [loadError, setLoadError] = useState(false);
  const [answers, setAnswers] = useState<Record<string, any>>({});
  const [note, setNote] = useState("");
  const [address, setAddress] = useState("");
  const [coords, setCoords] = useState<typeof TREVISO | null>(null);
  // BLOCCO 9: prima era hardcoded a "2026-06-20" — una data ormai fissa nel
  // codice, mai realmente inviata da nessun submit funzionante (vedi sotto).
  // Ora che il submit salva davvero, va calcolata al mount.
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [time, setTime] = useState("10:00");
  const [budget, setBudget] = useState("");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const mode = (type as string) || "service";
  const isPayment = mode === "payment";

  useEffect(() => {
    (async () => {
      try {
        const c = await api.getCategory(id as string);
        setCat(c);
      } catch {
        // BLOCCO 9 (fix "pagina bianca"): prima l'errore veniva ingoiato e
        // `cat` restava null per sempre (return <View /> vuota, sotto).
        // Ora c'è uno stato di errore visibile con un modo per uscire.
        setLoadError(true);
      }
    })();
  }, [id]);

  const useMyLocation = async () => {
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== "granted") return;
      const loc = await Location.getCurrentPositionAsync({});
      setCoords({ lat: loc.coords.latitude, lng: loc.coords.longitude });
      setAddress(`${loc.coords.latitude.toFixed(4)}, ${loc.coords.longitude.toFixed(4)} · Treviso`);
    } catch {}
  };

  const amount = useMemo(() => Number(answers.amount || 0), [answers]);
  const duration = Number(answers.duration || 2);

  const submit = async () => {
    setLoading(true);
    try {
      if (isPayment) {
        await api.pay({ service_id: id as string, label: cat.label[lang], amount, answers });
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
        setSuccess(true);
      } else {
        // BLOCCO 9 (fix "il servizio non viene salvato"): api.createMission()
        // chiamava POST /missions, mai montato su questo backend (motore
        // generico ritirato nel Blocco 5) — falliva sempre in silenzio.
        // Ora usa il flusso "a preventivo" dedicato (generic_requests.py).
        await api.createGenericRequest({
          cat_id: id as string,
          answers,
          note: note.trim() || budget.trim() ? `${note.trim()}${budget.trim() ? ` (budget indicativo: €${budget.trim()})` : ""}`.trim() : "",
          address: address.trim(),
          lat: coords?.lat, lng: coords?.lng,
          scheduled_at: date && time ? `${date}T${time}:00` : undefined,
        });
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
        setSuccess(true);
      }
    } catch (e: any) {
      setLoading(false);
      Alert.alert(t("error"));
    }
  };

  if (loadError) {
    return (
      <View style={[styles.container, styles.successWrap]}>
        <Text style={{ fontSize: 48 }}>⚠️</Text>
        <Text style={styles.successTitle}>{t("error")}</Text>
        <Button testID="request-error-back" label={t("done")} onPress={() => router.back()} style={{ marginTop: spacing.xl, minWidth: 200 }} />
      </View>
    );
  }

  if (!cat) return <View style={styles.container} />;

  if (success) {
    return (
      <View style={[styles.container, styles.successWrap]}>
        <Text style={{ fontSize: 64 }}>✅</Text>
        <Text style={styles.successTitle}>{t("paymentDone")}</Text>
        <Text style={styles.successSub}>{cat.label[lang]} · €{amount.toFixed(2)}</Text>
        <Button testID="done-button" label={t("done")} onPress={() => router.replace("/(tabs)/richieste")} style={{ marginTop: spacing.xl, minWidth: 200 }} />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="request-back" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.primary} />
          <Text style={styles.backText}>Back</Text>
        </Pressable>
      </View>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 160 }} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
          <Text style={styles.bigEmoji}>{cat.emoji}</Text>
          <Text style={styles.title}>{cat.label[lang]}</Text>

          {/* BLOCCO 9 (fix "pagina bianca"): il rendering qui sotto
              assumeva una forma delle domande mai realmente prodotta da
              nessun backend (q.label[lang], q.options[i].label[lang],
              tipi "select"/"number"/"date"/"time") — la vera colonna
              service_categories.questions (vedi routers/categories.py) ha
              {id, text, type: "choice"|"multi", options: string[]}, tutta
              in italiano. Riscritto per la forma reale. */}
          {(cat.questions || []).map((q: any) => {
            const isMulti = q.type === "multi";
            const selected: string[] = isMulti ? (answers[q.id] || []) : [];
            return (
              <View key={q.id} style={{ marginTop: spacing.lg }}>
                <Text style={styles.label}>{q.text}</Text>
                <View style={styles.optWrap}>
                  {(q.options || []).map((o: string) => {
                    const isOn = isMulti ? selected.includes(o) : answers[q.id] === o;
                    return (
                      <Pressable
                        key={o}
                        testID={`opt-${q.id}-${o}`}
                        style={[styles.opt, isOn && styles.optActive]}
                        onPress={() => {
                          if (isMulti) {
                            const next = selected.includes(o) ? selected.filter((x) => x !== o) : [...selected, o];
                            setAnswers({ ...answers, [q.id]: next });
                          } else {
                            setAnswers({ ...answers, [q.id]: o });
                          }
                        }}
                      >
                        <Text style={[styles.optText, isOn && styles.optTextActive]}>{o}</Text>
                      </Pressable>
                    );
                  })}
                </View>
              </View>
            );
          })}

          <Text style={styles.label}>{t("presentation")}</Text>
          <TextInput
            testID="request-note"
            style={[styles.input, { minHeight: 80, textAlignVertical: "top" }]}
            value={note}
            onChangeText={setNote}
            placeholder=""
            placeholderTextColor={colors.muted}
            multiline
          />

          {!isPayment && (
            <>
              <Text style={styles.label}>{t("address")}</Text>
              <TextInput testID="address-input" style={styles.input} value={address} onChangeText={setAddress} placeholderTextColor={colors.muted} />
              <Button label={t("useMyLocation")} variant="secondary" icon="navigate" onPress={useMyLocation} testID="use-location-button" style={{ marginTop: spacing.md, height: 46 }} />
              <View style={styles.row2}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.label}>{t("date")}</Text>
                  <DateField testID="date-input" value={date} onChange={setDate} lang={lang} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.label}>{t("time")}</Text>
                  <TimeField testID="time-input" value={time} onChange={setTime} />
                </View>
              </View>
              <Text style={styles.label}>{t("budgetOptional")}</Text>
              <TextInput testID="budget-input" style={styles.input} value={budget} onChangeText={setBudget} keyboardType="numeric" placeholder="€ 0.00" placeholderTextColor={colors.muted} />
              <Text style={styles.budgetHint}>{t("budgetHint")}</Text>
            </>
          )}
        </ScrollView>

        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          {isPayment ? (
            <Button testID="pay-button" label={`${t("payNow")} · €${amount.toFixed(2)}`} loading={loading} onPress={submit} />
          ) : (
            <Button testID="request-submit-button" label={t("requestService")} loading={loading} onPress={submit} />
          )}
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  backBtn: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start" },
  backText: { color: colors.primary, fontSize: fsize.xl, fontFamily: font.medium },
  bigEmoji: { fontSize: 46, textAlign: "center" },
  title: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface, textAlign: "center", marginTop: spacing.sm },
  label: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary, marginTop: spacing.md, marginBottom: spacing.sm },
  optWrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  opt: { paddingVertical: spacing.md, paddingHorizontal: spacing.lg, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  optActive: { borderColor: colors.primary, backgroundColor: "#FEEAE2" },
  optText: { fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  optTextActive: { color: colors.primary, fontFamily: font.medium },
  stepper: { flexDirection: "row", alignItems: "center", alignSelf: "flex-start", backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  stepBtn: { width: 52, height: 52, alignItems: "center", justifyContent: "center" },
  stepVal: { fontSize: fsize.xl, fontFamily: font.medium, color: colors.onSurface, width: 54, textAlign: "center" },
  input: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  row2: { flexDirection: "row", gap: spacing.md },
  budgetHint: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: spacing.sm },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.lg, paddingTop: spacing.md, backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderTopColor: colors.divider },
  successWrap: { alignItems: "center", justifyContent: "center", padding: spacing.xl },
  successTitle: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface, marginTop: spacing.lg },
  successSub: { fontSize: fsize.lg, fontFamily: font.regular, color: colors.muted, marginTop: spacing.sm },
});
