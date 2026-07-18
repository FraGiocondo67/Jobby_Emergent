import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import { Image } from "expo-image";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Stars } from "@/src/components/UI";

const ROLES = [
  { id: "client", labelKey: "roleClient", icon: "person" },
  { id: "provider", labelKey: "roleProviderName", icon: "construct" },
  { id: "business", labelKey: "roleBusiness", icon: "storefront" },
] as const;

export default function ProfileTab() {
  const { user, setUser, logout } = useAuth();
  const { t, lang, setLang } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [trust, setTrust] = useState<any>(null);

  const isProvider = user?.role === "provider" || user?.role === "business";
  const vStatus = user?.verification_status || "unverified";

  const loadTrust = useCallback(async () => {
    try { setTrust(await api.trust()); } catch {}
  }, []);
  useFocusEffect(useCallback(() => { loadTrust(); }, [loadTrust]));

  const switchRole = async (roleId: string) => {
    if (roleId === user?.role) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy).catch(() => {});
    const updated = await api.updateProfile({ role: roleId, online: roleId !== "client" });
    setUser(updated);
    router.replace("/(tabs)");
  };

  const onLogout = async () => { await logout(); router.replace("/onboarding"); };

  const score = isProvider ? (trust?.provider_score ?? 0) : (trust?.client_score ?? 0);
  const subs = isProvider ? (trust?.provider_subscores ?? {}) : (trust?.client_subscores ?? {});

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
            <View style={[styles.avatar, styles.avatarFallback]}><Text style={styles.avatarInitial}>{(user?.name || "?")[0]}</Text></View>
          )}
          <Text style={styles.name}>{user?.business_name || user?.name}</Text>
          <Text style={styles.email}>{user?.email}</Text>
          {isProvider && (user?.reviews_count ?? 0) > 0 ? (
            <View style={styles.ratingRow}>
              <Stars rating={user?.rating || 0} size={16} />
              <Text style={styles.ratingText}>{(user?.rating || 0).toFixed(1)} · {user?.reviews_count} {t("reviews")}</Text>
            </View>
          ) : null}
        </View>

        {/* Role selector */}
        <Text style={styles.sectionLabel}>{t("selectRole")}</Text>
        <View style={styles.roleRow}>
          {ROLES.map((r) => {
            const active = user?.role === r.id;
            return (
              <Pressable key={r.id} testID={`role-${r.id}`} style={[styles.roleChip, active && styles.roleChipActive]} onPress={() => switchRole(r.id)}>
                <Ionicons name={r.icon as any} size={22} color={active ? "#fff" : colors.onSurfaceTertiary} />
                <Text style={[styles.roleText, active && { color: "#fff" }]}>{t(r.labelKey as any)}</Text>
              </Pressable>
            );
          })}
        </View>

        {/* Verification */}
        <Pressable testID="verification-row" style={[styles.listRow, shadow.card]} onPress={() => router.push("/verification")}>
          <View style={[styles.rowIcon, { backgroundColor: vStatus === "verified" ? colors.greenBg : "#FEEAE2" }]}>
            <Ionicons name={vStatus === "verified" ? "shield-checkmark" : "shield-outline"} size={22} color={vStatus === "verified" ? colors.green : colors.primary} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.rowTitle}>{t("verifyIdentity")}</Text>
            <Text style={[styles.rowSub, { color: vStatus === "verified" ? colors.green : vStatus === "pending" ? colors.warning : colors.muted }]}>
              {vStatus === "verified" ? t("identityVerified") : vStatus === "pending" ? t("verificationPending") : t("notVerified")}
            </Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color={colors.muted} />
        </Pressable>

        {/* Provider activities */}
        {isProvider ? (
          <Pressable testID="activities-row" style={[styles.listRow, shadow.card]} onPress={() => router.push("/activities")}>
            <View style={[styles.rowIcon, { backgroundColor: colors.purpleBg }]}><Ionicons name="list" size={22} color={colors.purple} /></View>
            <View style={{ flex: 1 }}>
              <Text style={styles.rowTitle}>{t("myActivities")}</Text>
              <Text style={styles.rowSub}>{(user?.services || []).length} {t("selectService").toLowerCase()}</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={colors.muted} />
          </Pressable>
        ) : null}

        {/* Trust score */}
        <View style={[styles.trustCard, shadow.card]} testID="trust-card">
          <View style={styles.trustHead}>
            <Text style={styles.trustLabel}>{isProvider ? t("providerTrust") : t("clientTrust")}</Text>
            <Text style={styles.trustScore}>{score.toFixed(0)}<Text style={styles.trustMax}>/100</Text></Text>
          </View>
          <View style={styles.trustBarBg}><View style={[styles.trustBarFill, { width: `${Math.min(score, 100)}%` }]} /></View>
          <View style={styles.subs}>
            {Object.keys(subs).slice(0, 8).map((k) => (
              <View key={k} style={styles.subRow}>
                <Text style={styles.subKey}>{k}</Text>
                <Text style={styles.subVal}>{subs[k]}</Text>
              </View>
            ))}
          </View>
        </View>

        {/* Wallet */}
        <Pressable testID="profile-wallet" style={[styles.listRow, shadow.card]} onPress={() => router.push("/wallet")}>
          <View style={[styles.rowIcon, { backgroundColor: colors.greenBg }]}><Ionicons name="wallet" size={22} color={colors.green} /></View>
          <View style={{ flex: 1 }}>
            <Text style={styles.rowTitle}>{t("wallet")}</Text>
            <Text style={[styles.rowSub, { color: colors.green, fontFamily: font.bold }]}>€{(user?.wallet_balance ?? 0).toFixed(2)}</Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color={colors.muted} />
        </Pressable>

        {/* Personal details */}
        <Pressable testID="profile-details" style={[styles.listRow, shadow.card]} onPress={() => router.push("/profile-details")}>
          <View style={[styles.rowIcon, { backgroundColor: colors.surfaceTertiary }]}><Ionicons name="person-circle-outline" size={22} color={colors.onSurfaceTertiary} /></View>
          <View style={{ flex: 1 }}>
            <Text style={styles.rowTitle}>{t("personalDetails")}</Text>
            <Text style={styles.rowSub}>{isProvider ? t("detailsSubProvider") : t("detailsSubClient")}</Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color={colors.muted} />
        </Pressable>

        {/* Payments & payout settings */}
        <Pressable testID="profile-payments" style={[styles.listRow, shadow.card]} onPress={() => router.push("/payments-settings")}>
          <View style={[styles.rowIcon, { backgroundColor: colors.blueBg }]}><Ionicons name="card" size={22} color={colors.blue} /></View>
          <View style={{ flex: 1 }}>
            <Text style={styles.rowTitle}>{t("paymentsSettings")}</Text>
            <Text style={styles.rowSub}>{isProvider ? t("payoutSub") : t("paymentSub")}</Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color={colors.muted} />
        </Pressable>

        {/* Language */}
        <View style={styles.section}>
          <Text style={styles.settingLabel}>{t("language")}</Text>
          <View style={styles.langRow}>
            {(["it", "en"] as const).map((l) => (
              <Pressable key={l} testID={`profile-lang-${l}`} onPress={() => setLang(l)} style={[styles.langChip, lang === l && styles.langChipActive]}>
                <Text style={[styles.langText, lang === l && styles.langTextActive]}>{l.toUpperCase()}</Text>
              </Pressable>
            ))}
          </View>
        </View>

        <Pressable testID="admin-row" style={[styles.listRow, shadow.card]} onPress={() => router.push("/admin")}>
          <View style={[styles.rowIcon, { backgroundColor: "#FEEAE2" }]}><Ionicons name="settings" size={22} color={colors.primary} /></View>
          <View style={{ flex: 1 }}>
            <Text style={styles.rowTitle}>{t("adminPanel")}</Text>
            <Text style={styles.rowSub}>{t("manageCatalog")}</Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color={colors.muted} />
        </Pressable>

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
  headerTitle: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface },
  profileCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.xl, alignItems: "center", marginBottom: spacing.lg },
  avatar: { width: 84, height: 84, borderRadius: 42 },
  avatarFallback: { backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" },
  avatarInitial: { color: "#fff", fontSize: 34, fontFamily: font.medium },
  name: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.onSurface, marginTop: spacing.md },
  email: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 2 },
  ratingRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.md },
  ratingText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurfaceTertiary },
  sectionLabel: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: spacing.sm },
  roleRow: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.lg },
  roleChip: { flex: 1, alignItems: "center", gap: 6, paddingVertical: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  roleChipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  roleText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary },
  listRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.md, marginBottom: spacing.md },
  rowIcon: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center" },
  rowTitle: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  rowSub: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 1 },
  trustCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.md },
  trustHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end" },
  trustLabel: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  trustScore: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.brand },
  trustMax: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted },
  trustBarBg: { height: 8, borderRadius: 4, backgroundColor: colors.surfaceTertiary, marginTop: spacing.sm, overflow: "hidden" },
  trustBarFill: { height: 8, borderRadius: 4, backgroundColor: colors.brand },
  subs: { marginTop: spacing.md, gap: 4 },
  subRow: { flexDirection: "row", justifyContent: "space-between" },
  subKey: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, textTransform: "capitalize" },
  subVal: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.onSurfaceTertiary },
  section: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.lg, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  settingLabel: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  langRow: { flexDirection: "row", gap: spacing.sm },
  langChip: { paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill, backgroundColor: colors.surfaceTertiary },
  langChipActive: { backgroundColor: colors.primary },
  langText: { fontFamily: font.medium, fontSize: fsize.sm, color: colors.onSurfaceTertiary },
  langTextActive: { color: "#fff" },
  logoutRow: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, padding: spacing.md },
  logoutText: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.error },
});
