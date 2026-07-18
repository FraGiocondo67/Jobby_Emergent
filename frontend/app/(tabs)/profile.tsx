import React, { useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import { Image } from "expo-image";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Stars, Badge } from "@/src/components/UI";

export default function ProfileTab() {
  const { user, setUser, logout } = useAuth();
  const { t, lang, setLang } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [busy, setBusy] = useState(false);

  const isProvider = user?.role === "provider";

  const switchRole = async () => {
    setBusy(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy).catch(() => {});
    const newRole = isProvider ? "customer" : "provider";
    const updated = await api.updateProfile({ role: newRole, online: newRole === "provider" });
    setUser(updated);
    setBusy(false);
    router.replace("/(tabs)");
  };

  const onLogout = async () => {
    await logout();
    router.replace("/onboarding");
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Text style={styles.headerTitle}>{t("profile")}</Text>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 100 }} showsVerticalScrollIndicator={false}>
        <View style={[styles.profileCard, shadow.card]}>
          {user?.picture ? (
            <Image source={{ uri: user.picture }} style={styles.avatar} contentFit="cover" />
          ) : (
            <View style={[styles.avatar, styles.avatarFallback]}>
              <Text style={styles.avatarInitial}>{(user?.name || "?")[0]}</Text>
            </View>
          )}
          <Text style={styles.name}>{user?.name}</Text>
          <Text style={styles.email}>{user?.email}</Text>
          {isProvider ? (
            <View style={styles.ratingRow}>
              <Stars rating={user?.rating || 0} size={16} />
              <Text style={styles.ratingText}>{(user?.rating || 0).toFixed(1)} · {user?.reviews_count || 0} {t("reviews")}</Text>
            </View>
          ) : null}
          {isProvider ? (
            <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.md }}>
              <Badge label={t("verified")} icon="shield-checkmark" />
              <Badge label={t("insurance")} icon="umbrella" />
            </View>
          ) : null}
        </View>

        <Pressable testID="switch-role-card" style={styles.switchCard} onPress={switchRole} disabled={busy}>
          <View style={styles.switchIcon}>
            <Ionicons name={isProvider ? "person" : "briefcase"} size={22} color={colors.onBrandTertiary} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.switchLabel}>{isProvider ? t("roleProvider") : t("roleCustomer")}</Text>
            <Text style={styles.switchAction}>{isProvider ? t("switchToCustomer") : t("switchToProvider")}</Text>
          </View>
          <Ionicons name="swap-horizontal" size={22} color={colors.onBrandTertiary} />
        </Pressable>

        <Pressable testID="profile-wallet" style={styles.walletRow} onPress={() => router.push("/wallet")}>
          <View style={styles.walletIcon}><Ionicons name="wallet" size={22} color={colors.green} /></View>
          <View style={{ flex: 1 }}>
            <Text style={styles.settingLabel}>{t("wallet")}</Text>
            <Text style={styles.walletBalance}>€{(user?.wallet_balance ?? 0).toFixed(2)}</Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color={colors.muted} />
        </Pressable>

        <View style={styles.section}>
          <Text style={styles.settingLabel}>{t("language")}</Text>
          <View style={styles.langRow}>
            {(["it", "en"] as const).map((l) => (
              <Pressable
                key={l}
                testID={`profile-lang-${l}`}
                onPress={() => setLang(l)}
                style={[styles.langChip, lang === l && styles.langChipActive]}
              >
                <Text style={[styles.langText, lang === l && styles.langTextActive]}>{l.toUpperCase()}</Text>
              </Pressable>
            ))}
          </View>
        </View>

        <Pressable testID="logout-button" style={styles.logoutRow} onPress={onLogout}>
          <Ionicons name="log-out-outline" size={20} color={colors.error} />
          <Text style={styles.logoutText}>{t("logout")}</Text>
        </Pressable>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.divider },
  headerTitle: { fontSize: fsize["2xl"], fontFamily: font.medium, color: colors.onSurface },
  profileCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.xl, alignItems: "center", marginBottom: spacing.lg },
  avatar: { width: 84, height: 84, borderRadius: 42 },
  avatarFallback: { backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" },
  avatarInitial: { color: "#fff", fontSize: 34, fontFamily: font.medium },
  name: { fontSize: fsize.xl, fontFamily: font.medium, color: colors.onSurface, marginTop: spacing.md },
  email: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 2 },
  ratingRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.md },
  ratingText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurfaceTertiary },
  switchCard: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.brandTertiary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.lg },
  switchIcon: { width: 44, height: 44, borderRadius: 22, backgroundColor: "rgba(46,80,57,0.12)", alignItems: "center", justifyContent: "center" },
  switchLabel: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.onBrandTertiary },
  switchAction: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onBrandTertiary, marginTop: 1 },
  section: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.lg, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  walletRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.lg },
  walletIcon: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.greenBg, alignItems: "center", justifyContent: "center" },
  walletBalance: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.green, marginTop: 1 },
  settingLabel: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  langRow: { flexDirection: "row", gap: spacing.sm },
  langChip: { paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill, backgroundColor: colors.surfaceTertiary },
  langChipActive: { backgroundColor: colors.brand },
  langText: { fontFamily: font.medium, fontSize: fsize.sm, color: colors.onSurfaceTertiary },
  langTextActive: { color: "#fff" },
  logoutRow: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, padding: spacing.md },
  logoutText: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.error },
});
