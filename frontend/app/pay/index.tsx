import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";

const SERVICES = [
  { kind: "topup", emoji: "📱", titleKey: "topupTitle", descKey: "topupDesc", color: "#3B82F6" },
  { kind: "bill", emoji: "🧾", titleKey: "billTitle", descKey: "billDesc", color: "#F59E0B" },
  { kind: "abroad", emoji: "🌍", titleKey: "abroadTitle", descKey: "abroadDesc", color: "#8B5CF6" },
  { kind: "local", emoji: "💶", titleKey: "localTitle", descKey: "localDesc", color: "#10B981" },
] as const;

export default function PayHub() {
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [balance, setBalance] = useState(0);

  const load = useCallback(async () => {
    try { const w = await api.wallet(); setBalance(w.balance); } catch {}
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="pay-back" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.primary} />
          <Text style={styles.backText}>{t("backStep")}</Text>
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>{t("payHub")}</Text>

        <View style={styles.balanceCard}>
          <Text style={styles.balanceLabel}>{t("balance")}</Text>
          <Text style={styles.balanceValue}>€{balance.toFixed(2)}</Text>
        </View>

        <View style={{ gap: spacing.md, marginTop: spacing.lg }}>
          {SERVICES.map((s) => (
            <Pressable key={s.kind} testID={`pay-${s.kind}`} style={[styles.card, shadow.card]} onPress={() => router.push(`/pay/${s.kind}`)}>
              <View style={[styles.iconBox, { backgroundColor: s.color + "22" }]}><Text style={{ fontSize: 26 }}>{s.emoji}</Text></View>
              <View style={{ flex: 1 }}>
                <Text style={styles.cardTitle}>{t(s.titleKey as any)}</Text>
                <Text style={styles.cardDesc}>{t(s.descKey as any)}</Text>
              </View>
              <Ionicons name="chevron-forward" size={20} color={colors.muted} />
            </Pressable>
          ))}
        </View>

        <View style={styles.linksRow}>
          <Pressable testID="pay-history" style={[styles.linkBtn, shadow.card]} onPress={() => router.push("/pay/history")}>
            <Ionicons name="time-outline" size={20} color={colors.brand} />
            <Text style={styles.linkText}>{t("txHistory")}</Text>
          </Pressable>
          <Pressable testID="pay-beneficiaries" style={[styles.linkBtn, shadow.card]} onPress={() => router.push("/pay/beneficiaries")}>
            <Ionicons name="people-outline" size={20} color={colors.brand} />
            <Text style={styles.linkText}>{t("beneficiariesTitle")}</Text>
          </Pressable>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  backBtn: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start" },
  backText: { color: colors.primary, fontSize: fsize.xl, fontFamily: font.medium },
  title: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface, marginBottom: spacing.md },
  balanceCard: { backgroundColor: colors.brand, borderRadius: radius.lg, padding: spacing.lg, alignItems: "center" },
  balanceLabel: { color: "rgba(255,255,255,0.85)", fontSize: fsize.base, fontFamily: font.regular },
  balanceValue: { color: "#fff", fontSize: 36, fontFamily: font.bold, marginTop: 2 },
  card: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
  iconBox: { width: 48, height: 48, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  cardTitle: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  cardDesc: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 2 },
  linksRow: { flexDirection: "row", gap: spacing.md, marginTop: spacing.lg },
  linkBtn: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, paddingVertical: spacing.md, borderWidth: 1, borderColor: colors.border },
  linkText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
});
