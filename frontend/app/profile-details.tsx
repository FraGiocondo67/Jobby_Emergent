import React, { useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, KeyboardAvoidingView, Platform } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Button } from "@/src/components/UI";

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

export default function ProfileDetails() {
  const { user, refresh } = useAuth();
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [address, setAddress] = useState(user?.address || "");
  const [phone, setPhone] = useState(user?.phone || "");
  const [email, setEmail] = useState(user?.contact_email || user?.email || "");
  const [preferences, setPreferences] = useState(user?.preferences || "");
  const [days, setDays] = useState<string[]>(user?.availability?.days || []);
  const [start, setStart] = useState(user?.availability?.start || "09:00");
  const [end, setEnd] = useState(user?.availability?.end || "18:00");
  const [priceList, setPriceList] = useState<any[]>(user?.price_list || []);
  const [loading, setLoading] = useState(false);

  const isProvider = user?.role === "provider" || user?.role === "business";

  const toggleDay = (d: string) => {
    Haptics.selectionAsync().catch(() => {});
    setDays((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]));
  };
  const addItem = () => setPriceList((p) => [...p, { name: "", price: "", unit: "" }]);
  const updItem = (i: number, k: string, v: string) => setPriceList((p) => p.map((it, idx) => (idx === i ? { ...it, [k]: v } : it)));
  const delItem = (i: number) => setPriceList((p) => p.filter((_, idx) => idx !== i));

  const save = async () => {
    setLoading(true);
    const payload: any = { address, phone, contact_email: email, preferences };
    if (isProvider) {
      payload.availability = { days, start, end };
      payload.price_list = priceList
        .filter((it) => it.name.trim())
        .map((it) => ({ name: it.name.trim(), price: Number(it.price) || 0, unit: (it.unit || "").trim() }));
    }
    try {
      // BLOCCO 9: api.updateProfile() risponde con {"message": "..."}, non
      // con un utente — vedi fix analogo in app/(tabs)/index.tsx
      // (toggleOnline). refresh() richiama GET /auth/me.
      await api.updateProfile(payload);
      await refresh();
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      router.back();
    } catch {} finally { setLoading(false); }
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="details-back" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.primary} />
          <Text style={styles.backText}>Back</Text>
        </Pressable>
      </View>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 220 }} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
          <Text style={styles.title}>{t("personalDetails")}</Text>

          <Text style={styles.label}>{t("addressLabel")}</Text>
          <TextInput testID="detail-address" style={styles.input} value={address} onChangeText={setAddress} placeholder="Via Roma 12, Treviso" placeholderTextColor={colors.muted} />

          <Text style={styles.label}>{t("mobileLabel")}</Text>
          <TextInput testID="detail-phone" style={styles.input} value={phone} onChangeText={setPhone} keyboardType="phone-pad" placeholder="+39 ..." placeholderTextColor={colors.muted} />

          <Text style={styles.label}>{t("mailLabel")}</Text>
          <TextInput testID="detail-email" style={styles.input} value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" placeholder="name@mail.com" placeholderTextColor={colors.muted} />

          <Text style={styles.label}>{t("preferencesLabel")}</Text>
          <TextInput testID="detail-preferences" style={[styles.input, styles.textarea]} value={preferences} onChangeText={setPreferences} multiline placeholder={t("preferencesPlaceholder")} placeholderTextColor={colors.muted} />

          {isProvider ? (
            <>
              <Text style={styles.blockTitle}>{t("availability")}</Text>
              <Text style={styles.label}>{t("workingDays")}</Text>
              <View style={styles.daysRow}>
                {DAYS.map((d) => {
                  const on = days.includes(d);
                  return (
                    <Pressable key={d} testID={`day-${d}`} style={[styles.dayChip, on && styles.dayChipOn]} onPress={() => toggleDay(d)}>
                      <Text style={[styles.dayText, on && { color: "#fff" }]}>{t(`day_${d}` as any)}</Text>
                    </Pressable>
                  );
                })}
              </View>
              <Text style={styles.label}>{t("workingHours")}</Text>
              <View style={styles.row2}>
                <TextInput testID="time-start" style={[styles.input, { flex: 1 }]} value={start} onChangeText={setStart} placeholder="09:00" placeholderTextColor={colors.muted} />
                <Text style={styles.dash}>–</Text>
                <TextInput testID="time-end" style={[styles.input, { flex: 1 }]} value={end} onChangeText={setEnd} placeholder="18:00" placeholderTextColor={colors.muted} />
              </View>

              <View style={styles.priceHead}>
                <Text style={styles.blockTitle}>{t("priceList")}</Text>
                <Pressable testID="add-price-item" style={styles.addLink} onPress={addItem}>
                  <Ionicons name="add" size={18} color={colors.brand} />
                  <Text style={styles.addLinkText}>{t("addItem")}</Text>
                </Pressable>
              </View>
              {priceList.length === 0 ? <Text style={styles.emptyText}>{t("noPriceItems")}</Text> : null}
              {priceList.map((it, i) => (
                <View key={i} style={[styles.priceRow, shadow.card]} testID={`price-item-${i}`}>
                  <TextInput style={[styles.input, { flex: 2 }]} value={it.name} onChangeText={(v) => updItem(i, "name", v)} placeholder={t("itemName")} placeholderTextColor={colors.muted} testID={`price-name-${i}`} />
                  <TextInput style={[styles.input, { flex: 1 }]} value={String(it.price)} onChangeText={(v) => updItem(i, "price", v)} keyboardType="numeric" placeholder="€" placeholderTextColor={colors.muted} testID={`price-value-${i}`} />
                  <Pressable testID={`price-del-${i}`} hitSlop={10} onPress={() => delItem(i)}><Ionicons name="trash-outline" size={20} color={colors.error} /></Pressable>
                </View>
              ))}
            </>
          ) : null}
        </ScrollView>
        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          <Button testID="save-details" label={t("save")} loading={loading} onPress={save} />
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
  title: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface, marginBottom: spacing.sm },
  label: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary, marginTop: spacing.lg, marginBottom: spacing.sm },
  input: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  textarea: { minHeight: 90, textAlignVertical: "top" },
  blockTitle: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.onSurface, marginTop: spacing.xl },
  daysRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  dayChip: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  dayChipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  dayText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary },
  row2: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  dash: { fontSize: fsize.xl, color: colors.muted },
  priceHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  addLink: { flexDirection: "row", alignItems: "center", gap: 2, marginTop: spacing.xl },
  addLinkText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.brand },
  emptyText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: spacing.sm },
  priceRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.sm },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.lg, paddingTop: spacing.md, backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderTopColor: colors.divider },
});
