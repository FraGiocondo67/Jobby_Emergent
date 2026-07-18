import React, { useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Button } from "@/src/components/UI";

export default function Verification() {
  const { user, setUser, refresh } = useAuth();
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [doc, setDoc] = useState(false);
  const [selfie, setSelfie] = useState(false);
  const [loading, setLoading] = useState(false);
  const verified = user?.verification_status === "verified";

  const run = async () => {
    setLoading(true);
    try {
      await api.startVerification();
      await new Promise((r) => setTimeout(r, 900));
      await api.completeVerification();
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      await refresh();
      router.back();
    } catch { setLoading(false); }
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="verification-back" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.primary} />
          <Text style={styles.backText}>Back</Text>
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 120 }}>
        <Text style={styles.bigEmoji}>🛡️</Text>
        <Text style={styles.title}>{t("verifyIdentity")}</Text>
        <Text style={styles.desc}>{t("verificationDesc")}</Text>
        <View style={styles.mockBadge}><Text style={styles.mockText}>Sumsub · {t("mockNote")}</Text></View>

        {verified ? (
          <View style={styles.verifiedBox}>
            <Ionicons name="checkmark-circle" size={30} color={colors.success} />
            <Text style={styles.verifiedText}>{t("identityVerified")}</Text>
          </View>
        ) : (
          <View style={{ marginTop: spacing.xl, gap: spacing.md }}>
            <Pressable testID="upload-document" style={[styles.step, doc && styles.stepDone]} onPress={() => setDoc(true)}>
              <Ionicons name={doc ? "checkmark-circle" : "document-text-outline"} size={24} color={doc ? colors.success : colors.onSurfaceTertiary} />
              <Text style={styles.stepText}>{t("uploadDocument")}</Text>
            </Pressable>
            <Pressable testID="take-selfie" style={[styles.step, selfie && styles.stepDone]} onPress={() => setSelfie(true)}>
              <Ionicons name={selfie ? "checkmark-circle" : "camera-outline"} size={24} color={selfie ? colors.success : colors.onSurfaceTertiary} />
              <Text style={styles.stepText}>{t("takeSelfie")}</Text>
            </Pressable>
          </View>
        )}
      </ScrollView>

      {!verified ? (
        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          <Button testID="start-verification-button" label={loading ? t("verifying") : t("startVerification")} loading={loading} disabled={!doc || !selfie} onPress={run} />
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  backBtn: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start" },
  backText: { color: colors.primary, fontSize: fsize.xl, fontFamily: font.medium },
  bigEmoji: { fontSize: 54, textAlign: "center", marginTop: spacing.md },
  title: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface, textAlign: "center", marginTop: spacing.md },
  desc: { fontSize: fsize.lg, fontFamily: font.regular, color: colors.muted, textAlign: "center", marginTop: spacing.sm },
  mockBadge: { alignSelf: "center", marginTop: spacing.md, backgroundColor: "#FBF0E2", paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill },
  mockText: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.warning },
  step: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, ...shadow.card },
  stepDone: { borderColor: colors.success, backgroundColor: colors.greenBg },
  stepText: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  verifiedBox: { alignItems: "center", gap: spacing.sm, marginTop: spacing["2xl"] },
  verifiedText: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.success },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.lg, paddingTop: spacing.md, backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderTopColor: colors.divider },
});
