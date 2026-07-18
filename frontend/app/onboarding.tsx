import React, { useState } from "react";
import { View, Text, StyleSheet, Pressable } from "react-native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { spacing, radius, font, fsize } from "@/src/theme";
import { Button } from "@/src/components/UI";

const NAVY = "#0E1F3D";

export default function Onboarding() {
  const { login } = useAuth();
  const { lang, setLang, t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [loading, setLoading] = useState(false);

  const onLogin = async () => {
    setLoading(true);
    try {
      await login();
      router.replace("/(tabs)");
    } catch {
      setLoading(false);
    }
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top, paddingBottom: insets.bottom }]} testID="onboarding-screen">
      <View style={[styles.langRow, { top: insets.top + spacing.md }]}>
        {(["it", "en"] as const).map((l) => (
          <Pressable key={l} testID={`lang-${l}`} onPress={() => setLang(l)} style={[styles.langChip, lang === l && styles.langChipActive]}>
            <Text style={[styles.langText, lang === l && styles.langTextActive]}>{l.toUpperCase()}</Text>
          </Pressable>
        ))}
      </View>

      <View style={styles.center}>
        <Image source={require("@/assets/images/jobby-logo.png")} style={styles.logo} contentFit="contain" />
      </View>

      <View style={styles.bottom}>
        <Text style={styles.tagline}>{t("appTagline")}</Text>
        <View style={{ height: spacing.xl }} />
        <Button testID="google-login-button" label={loading ? t("signingIn") : t("continueGoogle")} onPress={onLogin} loading={loading} variant="secondary" icon="logo-google" />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: NAVY, paddingHorizontal: spacing.xl },
  langRow: { position: "absolute", right: spacing.lg, flexDirection: "row", gap: spacing.xs, zIndex: 2 },
  langChip: { paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill, backgroundColor: "rgba(255,255,255,0.15)" },
  langChipActive: { backgroundColor: "#fff" },
  langText: { color: "#fff", fontFamily: font.medium, fontSize: fsize.sm },
  langTextActive: { color: NAVY },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  logo: { width: 300, height: 300 },
  bottom: { paddingBottom: spacing.xl },
  tagline: { color: "rgba(255,255,255,0.9)", fontSize: fsize.xl, fontFamily: font.regular, textAlign: "center", lineHeight: 28 },
});
