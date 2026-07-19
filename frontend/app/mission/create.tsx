import React, { useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput, KeyboardAvoidingView, Platform,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Location from "expo-location";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize } from "@/src/theme";
import { Button } from "@/src/components/UI";
import { DateField, TimeField } from "@/src/components/DateTimeField";

const TREVISO = { lat: 45.6669, lng: 12.2433 };

export default function CreateMission() {
  const { category } = useLocalSearchParams<{ category: string }>();
  const { lang, t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [step, setStep] = useState(0);
  const [homeType, setHomeType] = useState("apartment");
  const [rooms, setRooms] = useState(3);
  const [duration, setDuration] = useState(2);
  const [recurrence, setRecurrence] = useState("once");
  const [address, setAddress] = useState("Via Roma 12, Treviso");
  const [coords, setCoords] = useState(TREVISO);
  const [date, setDate] = useState("2026-06-15");
  const [time, setTime] = useState("10:00");
  const [loading, setLoading] = useState(false);
  const cat = (category as string) || "cleaning";

  const useMyLocation = async () => {
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== "granted") return;
      const loc = await Location.getCurrentPositionAsync({});
      setCoords({ lat: loc.coords.latitude, lng: loc.coords.longitude });
      setAddress(`${loc.coords.latitude.toFixed(4)}, ${loc.coords.longitude.toFixed(4)} · Treviso`);
    } catch {}
  };

  const submit = async () => {
    setLoading(true);
    try {
      const m = await api.createMission({
        category: cat,
        service_type: cat === "ironing" ? "standard_ironing" : "standard_cleaning",
        config: { homeType, rooms },
        address,
        lat: coords.lat,
        lng: coords.lng,
        date, time,
        duration_hours: duration,
        recurrence,
      });
      router.replace(`/mission/radar?id=${m.mission_id}`);
    } catch {
      setLoading(false);
    }
  };

  const steps = [t("serviceDetails"), t("location"), t("dateTime")];

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="back-button" onPress={() => (step === 0 ? router.back() : setStep(step - 1))} hitSlop={12}>
          <Ionicons name="arrow-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>{t(cat as any)}</Text>
        <View style={{ width: 24 }} />
      </View>

      <View style={styles.progress}>
        {steps.map((_, i) => (
          <View key={i} style={[styles.progressBar, { backgroundColor: i <= step ? colors.brand : colors.border }]} />
        ))}
      </View>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 140 }} keyboardShouldPersistTaps="handled">
          <Text style={styles.stepTitle}>{steps[step]}</Text>

          {step === 0 && (
            <>
              <Text style={styles.label}>{t("homeType")}</Text>
              <View style={styles.optRow}>
                {["apartment", "house"].map((o) => (
                  <Pressable key={o} testID={`hometype-${o}`} style={[styles.opt, homeType === o && styles.optActive]} onPress={() => setHomeType(o)}>
                    <Text style={[styles.optText, homeType === o && styles.optTextActive]}>{t(o as any)}</Text>
                  </Pressable>
                ))}
              </View>
              <Text style={styles.label}>{t("rooms")}</Text>
              <Stepper value={rooms} setValue={setRooms} min={1} max={10} testID="rooms" />
              <Text style={styles.label}>{t("duration")}</Text>
              <Stepper value={duration} setValue={setDuration} min={1} max={8} testID="duration" />
            </>
          )}

          {step === 1 && (
            <>
              <Text style={styles.label}>{t("address")}</Text>
              <TextInput
                testID="address-input"
                style={styles.input}
                value={address}
                onChangeText={setAddress}
                placeholder={t("address")}
                placeholderTextColor={colors.muted}
              />
              <Button label={t("useMyLocation")} variant="secondary" icon="navigate" onPress={useMyLocation} testID="use-location-button" style={{ marginTop: spacing.md }} />
              <Text style={styles.label}>{t("recurrence")}</Text>
              <View style={styles.optCol}>
                {["once", "weekly", "biweekly"].map((o) => (
                  <Pressable key={o} testID={`recurrence-${o}`} style={[styles.optWide, recurrence === o && styles.optActive]} onPress={() => setRecurrence(o)}>
                    <Text style={[styles.optText, recurrence === o && styles.optTextActive]}>{t(o as any)}</Text>
                    {recurrence === o ? <Ionicons name="checkmark-circle" size={20} color={colors.brand} /> : null}
                  </Pressable>
                ))}
              </View>
            </>
          )}

          {step === 2 && (
            <>
              <Text style={styles.label}>{t("date")}</Text>
              <DateField testID="date-input" value={date} onChange={setDate} lang={lang} />
              <Text style={styles.label}>{t("time")}</Text>
              <TimeField testID="time-input" value={time} onChange={setTime} />
              <View style={styles.summary}>
                <Text style={styles.summaryTitle}>{t(cat as any)} · {t(homeType as any)}</Text>
                <Text style={styles.summaryLine}>{rooms} {t("rooms").toLowerCase()} · {duration} {t("hours")}</Text>
                <Text style={styles.summaryLine}>{t(recurrence as any)}</Text>
              </View>
            </>
          )}
        </ScrollView>

        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          <Button
            testID={step === 2 ? "broadcast-button" : "next-button"}
            label={step === 2 ? t("broadcast") : t("next")}
            loading={loading}
            onPress={() => (step === 2 ? submit() : setStep(step + 1))}
          />
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

function Stepper({ value, setValue, min, max, testID }: { value: number; setValue: (n: number) => void; min: number; max: number; testID: string }) {
  return (
    <View style={styles.stepper}>
      <Pressable testID={`${testID}-minus`} style={styles.stepBtn} onPress={() => setValue(Math.max(min, value - 1))}>
        <Ionicons name="remove" size={22} color={colors.onSurface} />
      </Pressable>
      <Text style={styles.stepVal} testID={`${testID}-value`}>{value}</Text>
      <Pressable testID={`${testID}-plus`} style={styles.stepBtn} onPress={() => setValue(Math.min(max, value + 1))}>
        <Ionicons name="add" size={22} color={colors.onSurface} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  headerTitle: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  progress: { flexDirection: "row", gap: 6, paddingHorizontal: spacing.lg, marginBottom: spacing.md },
  progressBar: { flex: 1, height: 4, borderRadius: 2 },
  stepTitle: { fontSize: fsize["2xl"], fontFamily: font.medium, color: colors.onSurface, marginBottom: spacing.lg },
  label: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary, marginTop: spacing.lg, marginBottom: spacing.sm },
  optRow: { flexDirection: "row", gap: spacing.md },
  optCol: { gap: spacing.sm },
  opt: { flex: 1, paddingVertical: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, alignItems: "center", backgroundColor: colors.surfaceSecondary },
  optWide: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: spacing.md, paddingHorizontal: spacing.lg, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  optActive: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  optText: { fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  optTextActive: { color: colors.onBrandTertiary, fontFamily: font.medium },
  stepper: { flexDirection: "row", alignItems: "center", alignSelf: "flex-start", backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  stepBtn: { width: 52, height: 52, alignItems: "center", justifyContent: "center" },
  stepVal: { fontSize: fsize.xl, fontFamily: font.medium, color: colors.onSurface, width: 50, textAlign: "center" },
  input: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  summary: { backgroundColor: colors.brandTertiary, borderRadius: radius.md, padding: spacing.lg, marginTop: spacing.xl },
  summaryTitle: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onBrandTertiary },
  summaryLine: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onBrandTertiary, marginTop: 2 },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.lg, paddingTop: spacing.md, backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderTopColor: colors.divider },
});
