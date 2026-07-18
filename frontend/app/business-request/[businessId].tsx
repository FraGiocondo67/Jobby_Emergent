import React, { useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput, KeyboardAvoidingView, Platform,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Location from "expo-location";
import * as Haptics from "expo-haptics";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize } from "@/src/theme";
import { Button } from "@/src/components/UI";

const TREVISO = { lat: 45.6669, lng: 12.2433 };

export default function BusinessRequestScreen() {
  const { businessId, category, name, label } = useLocalSearchParams<{ businessId: string; category: string; name: string; label: string }>();
  const { user } = useAuth();
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [note, setNote] = useState("");
  const [address, setAddress] = useState("Via Roma 12, Treviso");
  const [coords, setCoords] = useState({ lat: user?.lat || TREVISO.lat, lng: user?.lng || TREVISO.lng });
  const [budget, setBudget] = useState("");
  const [detail, setDetail] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  React.useEffect(() => {
    (async () => {
      try { setDetail(await api.getBusinessDetail(businessId as string)); } catch {}
    })();
  }, [businessId]);

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
    if (!note.trim()) return;
    setLoading(true);
    try {
      await api.createBusinessRequest({
        business_id: businessId as string,
        category: category as string,
        note: note.trim(),
        address,
        lat: coords.lat,
        lng: coords.lng,
        budget: budget.trim() ? Number(budget) : null,
      });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      setSuccess(true);
    } catch {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <View style={[styles.container, styles.successWrap]}>
        <Text style={{ fontSize: 64 }}>📨</Text>
        <Text style={styles.successTitle}>{t("requestSent")}</Text>
        <Text style={styles.successSub}>{t("requestSentDesc")} {name}</Text>
        <Button testID="done-button" label={t("done")} onPress={() => router.replace("/(tabs)/richieste")} style={{ marginTop: spacing.xl, minWidth: 200 }} />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="breq-back" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.primary} />
          <Text style={styles.backText}>Back</Text>
        </Pressable>
      </View>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 160 }} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
          <Text style={styles.bizName}>{name}</Text>
          <Text style={styles.bizCat}>{label}</Text>

          {detail?.price_list?.length ? (
            <View style={styles.priceCard}>
              <Text style={styles.priceTitle}>{t("priceListTitle")}</Text>
              {detail.price_list.map((it: any, i: number) => (
                <View key={i} style={styles.priceRow} testID={`biz-price-${i}`}>
                  <Text style={styles.priceName}>{it.name}{it.unit ? ` · ${it.unit}` : ""}</Text>
                  <Text style={styles.priceVal}>€{Number(it.price).toFixed(2)}</Text>
                </View>
              ))}
            </View>
          ) : null}

          <Text style={styles.label}>{t("whatDoYouNeed")}</Text>
          <TextInput
            testID="breq-note"
            style={[styles.input, styles.textarea]}
            value={note}
            onChangeText={setNote}
            placeholder={t("productServicePlaceholder")}
            placeholderTextColor={colors.muted}
            multiline
          />

          <Text style={styles.label}>{t("budgetOptional")}</Text>
          <TextInput testID="breq-budget" style={styles.input} value={budget} onChangeText={setBudget} keyboardType="numeric" placeholder="€ 0.00" placeholderTextColor={colors.muted} />

          <Text style={styles.label}>{t("address")}</Text>
          <TextInput testID="breq-address" style={styles.input} value={address} onChangeText={setAddress} placeholderTextColor={colors.muted} />
          <Button label={t("useMyLocation")} variant="secondary" icon="navigate" onPress={useMyLocation} testID="breq-location" style={{ marginTop: spacing.md, height: 46 }} />

          <Text style={styles.hint}>{t("businessWillConfirm")}</Text>
        </ScrollView>

        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          <Button testID="breq-submit" label={t("sendRequest")} loading={loading} onPress={submit} />
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
  bizName: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface },
  bizCat: { fontSize: fsize.lg, fontFamily: font.regular, color: colors.purple, marginTop: 2 },
  label: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary, marginTop: spacing.lg, marginBottom: spacing.sm },
  input: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  textarea: { minHeight: 100, textAlignVertical: "top" },
  priceCard: { backgroundColor: colors.purpleBg, borderRadius: radius.md, padding: spacing.md, marginTop: spacing.md },
  priceTitle: { fontSize: fsize.base, fontFamily: font.bold, color: colors.purple, marginBottom: spacing.sm },
  priceRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 4 },
  priceName: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface, flex: 1 },
  priceVal: { fontSize: fsize.base, fontFamily: font.bold, color: colors.purple },
  hint: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: spacing.lg, textAlign: "center" },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.lg, paddingTop: spacing.md, backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderTopColor: colors.divider },
  successWrap: { alignItems: "center", justifyContent: "center", padding: spacing.xl },
  successTitle: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface, marginTop: spacing.lg },
  successSub: { fontSize: fsize.lg, fontFamily: font.regular, color: colors.muted, marginTop: spacing.sm, textAlign: "center" },
});
