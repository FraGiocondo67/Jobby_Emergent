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
const SLOTS = ["morning", "afternoon", "evening"];

export default function ProfileDetails() {
  const { user, refresh } = useAuth();
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [address, setAddress] = useState(user?.address || "");
  const [phone, setPhone] = useState(user?.phone || "");
  const [email, setEmail] = useState(user?.contact_email || user?.email || "");
  const [preferences, setPreferences] = useState(user?.preferences || "");
  // BLOCCO 9 (fix "la disponibilità impostata in onboarding non si vede/
  // salva più dal profilo"): questa schermata usava una forma
  // {days[], start, end} (fascia oraria unica) mai esistita lato backend —
  // ProfilePatchIn (routers/profile.py) non ha né un campo `availability`
  // né legge/scrive user.availability da nessuna parte: il PUT veniva
  // accettato (pydantic ignora campi sconosciuti) ma non salvava nulla, e
  // la lettura iniziale (user?.availability?.days) era sempre vuota. La
  // disponibilità VERA, impostata durante l'onboarding provider, vive in
  // profiles_provider.time_slots — {giorno: {morning/afternoon/evening:
  // bool}} — già esposta in GET /auth/me come user.provider_profile.
  // time_slots e già salvata con PUT /onboarding/availability (stesso
  // endpoint/schermata di app/provider-onboarding.tsx). Riallineato qui a
  // quello, invece di reinventare un formato incompatibile.
  const [timeSlots, setTimeSlots] = useState<Record<string, Record<string, boolean>>>(user?.provider_profile?.time_slots || {});
  const [priceList, setPriceList] = useState<any[]>(user?.provider_profile?.price_list || user?.price_list || []);
  const [loading, setLoading] = useState(false);

  const isProvider = user?.role === "provider" || user?.role === "business";

  const toggleSlot = (d: string, s: string) => {
    Haptics.selectionAsync().catch(() => {});
    setTimeSlots((prev) => ({ ...prev, [d]: { ...(prev[d] || {}), [s]: !(prev[d]?.[s]) } }));
  };
  const addItem = () => setPriceList((p) => [...p, { name: "", price: "", unit: "" }]);
  const updItem = (i: number, k: string, v: string) => setPriceList((p) => p.map((it, idx) => (idx === i ? { ...it, [k]: v } : it)));
  const delItem = (i: number) => setPriceList((p) => p.filter((_, idx) => idx !== i));

  const save = async () => {
    setLoading(true);
    const payload: any = { address, phone };
    if (isProvider) {
      payload.price_list = priceList
        .filter((it) => it.name.trim())
        .map((it) => ({ name: it.name.trim(), price: Number(it.price) || 0, unit: (it.unit || "").trim() }));
    }
    try {
      // BLOCCO 9: api.updateProfile() risponde con {"message": "..."}, non
      // con un utente — vedi fix analogo in app/(tabs)/index.tsx
      // (toggleOnline). refresh() richiama GET /auth/me.
      await api.updateProfile(payload);
      if (isProvider) await api.setAvailability(timeSlots);
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
              <View style={styles.availHead}>
                <View style={{ width: 48 }} />
                {SLOTS.map((s) => <Text key={s} style={styles.availSlotHead}>{t(`slot_${s}` as any)}</Text>)}
              </View>
              {DAYS.map((d) => (
                <View key={d} style={styles.availRow}>
                  <Text style={styles.availDay}>{t(`day_${d}` as any)}</Text>
                  {SLOTS.map((s) => (
                    <Pressable key={s} testID={`av-${d}-${s}`} style={[styles.availCell, timeSlots[d]?.[s] && styles.availCellOn]} onPress={() => toggleSlot(d, s)}>
                      {timeSlots[d]?.[s] ? <Ionicons name="checkmark" size={16} color="#fff" /> : null}
                    </Pressable>
                  ))}
                </View>
              ))}

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
  availHead: { flexDirection: "row", alignItems: "center", marginBottom: spacing.sm },
  availSlotHead: { flex: 1, textAlign: "center", fontSize: fsize.sm, fontFamily: font.medium, color: colors.muted },
  availRow: { flexDirection: "row", alignItems: "center", marginBottom: spacing.sm },
  availDay: { width: 48, fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  availCell: { flex: 1, height: 40, marginHorizontal: 3, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  availCellOn: { backgroundColor: colors.brand, borderColor: colors.brand },
  row2: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  dash: { fontSize: fsize.xl, color: colors.muted },
  priceHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  addLink: { flexDirection: "row", alignItems: "center", gap: 2, marginTop: spacing.xl },
  addLinkText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.brand },
  emptyText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: spacing.sm },
  priceRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.sm },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.lg, paddingTop: spacing.md, backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderTopColor: colors.divider },
});
