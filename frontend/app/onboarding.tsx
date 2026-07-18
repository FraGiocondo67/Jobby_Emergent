import React, { useState } from "react";
import { View, Text, StyleSheet, Pressable, ImageBackground } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { colors, spacing, radius, font, fsize } from "@/src/theme";
import { Button } from "@/src/components/UI";

const BG = "https://images.pexels.com/photos/8112186/pexels-photo-8112186.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940";

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
    } catch (e) {
      setLoading(false);
    }
  };

  return (
    <View style={styles.container} testID="onboarding-screen">
      <ImageBackground source={{ uri: BG }} style={styles.bg}>
        <LinearGradient
          colors={["rgba(28,27,26,0.15)", "rgba(28,27,26,0.55)", "rgba(28,27,26,0.92)"]}
          style={StyleSheet.absoluteFill}
        />
        <View style={[styles.langRow, { top: insets.top + spacing.md }]}>
          {(["it", "en"] as const).map((l) => (
            <Pressable
              key={l}
              testID={`lang-${l}`}
              onPress={() => setLang(l)}
              style={[styles.langChip, lang === l && styles.langChipActive]}
            >
              <Text style={[styles.langText, lang === l && styles.langTextActive]}>{l.toUpperCase()}</Text>
            </Pressable>
          ))}
        </View>

        <View style={[styles.content, { paddingBottom: insets.bottom + spacing.xl }]}>
          <View style={styles.brandRow}>
            <Ionicons name="time" size={34} color="#fff" />
            <Text style={styles.brand}>JOBBY</Text>
          </View>
          <Text style={styles.tagline}>{t("appTagline")}</Text>
          <View style={{ height: spacing.xl }} />
          <Button
            testID="google-login-button"
            label={loading ? t("signingIn") : t("continueGoogle")}
            onPress={onLogin}
            loading={loading}
            variant="secondary"
            icon="logo-google"
          />
        </View>
      </ImageBackground>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surfaceInverse },
  bg: { flex: 1, justifyContent: "flex-end" },
  langRow: { position: "absolute", right: spacing.lg, flexDirection: "row", gap: spacing.xs },
  langChip: {
    paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill,
    backgroundColor: "rgba(255,255,255,0.2)",
  },
  langChipActive: { backgroundColor: "#fff" },
  langText: { color: "#fff", fontFamily: font.medium, fontSize: fsize.sm },
  langTextActive: { color: colors.onSurface },
  content: { paddingHorizontal: spacing.xl, paddingTop: spacing["3xl"] },
  brandRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  brand: { color: "#fff", fontSize: 40, fontFamily: font.bold, letterSpacing: 1 },
  tagline: { color: "rgba(255,255,255,0.9)", fontSize: fsize.xl, fontFamily: font.regular, marginTop: spacing.md, lineHeight: 28 },
});
