import React, { useEffect, useMemo, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput, KeyboardAvoidingView, Platform,
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

const TREVISO = { lat: 45.6669, lng: 12.2433 };

export default function RequestScreen() {
  const { id, type } = useLocalSearchParams<{ id: string; type: string }>();
  const { lang, t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [cat, setCat] = useState<any>(null);
  const [answers, setAnswers] = useState<Record<string, any>>({});
  const [address, setAddress] = useState("Via Roma 12, Treviso");
  const [coords, setCoords] = useState(TREVISO);
  const [date, setDate] = useState("2026-06-20");
  const [time, setTime] = useState("10:00");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const mode = (type as string) || "service";
  const isPayment = mode === "payment";

  useEffect(() => {
    (async () => {
      try {
        const c = await api.getCategory(id as string);
        setCat(c);
        const init: Record<string, any> = {};
        (c.questions || []).forEach((q: any) => { if (q.default !== undefined) init[q.id] = q.default; });
        setAnswers(init);
      } catch {}
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
        const m = await api.createMission({
          category: id as string,
          service_type: id as string,
          config: answers,
          address, lat: coords.lat, lng: coords.lng,
          date, time,
          duration_hours: duration,
          recurrence: "once",
        });
        router.replace(`/mission/radar?id=${m.mission_id}`);
      }
    } catch (e: any) {
      setLoading(false);
    }
  };

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

          {(cat.questions || []).map((q: any) => (
            <View key={q.id} style={{ marginTop: spacing.lg }}>
              <Text style={styles.label}>{q.label[lang]}</Text>
              {q.type === "select" && (
                <View style={styles.optWrap}>
                  {q.options.map((o: any) => (
                    <Pressable
                      key={o.id}
                      testID={`opt-${q.id}-${o.id}`}
                      style={[styles.opt, answers[q.id] === o.id && styles.optActive]}
                      onPress={() => setAnswers({ ...answers, [q.id]: o.id })}
                    >
                      <Text style={[styles.optText, answers[q.id] === o.id && styles.optTextActive]}>{o.label[lang]}</Text>
                    </Pressable>
                  ))}
                </View>
              )}
              {q.type === "number" && (
                <View style={styles.stepper}>
                  <Pressable testID={`${q.id}-minus`} style={styles.stepBtn} onPress={() => setAnswers({ ...answers, [q.id]: Math.max(q.min, (answers[q.id] ?? q.default) - 1) })}>
                    <Ionicons name="remove" size={22} color={colors.onSurface} />
                  </Pressable>
                  <Text style={styles.stepVal} testID={`${q.id}-value`}>{answers[q.id] ?? q.default}</Text>
                  <Pressable testID={`${q.id}-plus`} style={styles.stepBtn} onPress={() => setAnswers({ ...answers, [q.id]: Math.min(q.max, (answers[q.id] ?? q.default) + 1) })}>
                    <Ionicons name="add" size={22} color={colors.onSurface} />
                  </Pressable>
                </View>
              )}
              {q.type === "text" && (
                <TextInput
                  testID={`input-${q.id}`}
                  style={styles.input}
                  value={answers[q.id] || ""}
                  onChangeText={(v) => setAnswers({ ...answers, [q.id]: v })}
                  placeholder={q.placeholder?.[lang] || ""}
                  placeholderTextColor={colors.muted}
                />
              )}
            </View>
          ))}

          {!isPayment && (
            <>
              <Text style={styles.label}>{t("address")}</Text>
              <TextInput testID="address-input" style={styles.input} value={address} onChangeText={setAddress} placeholderTextColor={colors.muted} />
              <Button label={t("useMyLocation")} variant="secondary" icon="navigate" onPress={useMyLocation} testID="use-location-button" style={{ marginTop: spacing.md, height: 46 }} />
              <View style={styles.row2}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.label}>{t("date")}</Text>
                  <TextInput testID="date-input" style={styles.input} value={date} onChangeText={setDate} placeholder="YYYY-MM-DD" placeholderTextColor={colors.muted} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.label}>{t("time")}</Text>
                  <TextInput testID="time-input" style={styles.input} value={time} onChangeText={setTime} placeholder="HH:MM" placeholderTextColor={colors.muted} />
                </View>
              </View>
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
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.lg, paddingTop: spacing.md, backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderTopColor: colors.divider },
  successWrap: { alignItems: "center", justifyContent: "center", padding: spacing.xl },
  successTitle: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface, marginTop: spacing.lg },
  successSub: { fontSize: fsize.lg, fontFamily: font.regular, color: colors.muted, marginTop: spacing.sm },
});
