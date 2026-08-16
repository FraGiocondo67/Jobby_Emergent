import React, { useEffect, useState } from "react";
import {
  View, Text, StyleSheet, Pressable, TextInput, ScrollView, KeyboardAvoidingView, Platform,
} from "react-native";
import { Image } from "expo-image";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as AppleAuthentication from "expo-apple-authentication";
import { useAuth } from "@/src/context/AuthContext";
import { useLang, SUPPORTED_LANGS } from "@/src/context/LanguageContext";
import { colors, spacing, radius, font, fsize } from "@/src/theme";
import { Button } from "@/src/components/UI";

const NAVY = "#0E1F3D";

export default function Onboarding() {
  const { login, loginEmail, register, loginApple, loginDemo } = useAuth();
  const { lang, setLang, t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [appleAvailable, setAppleAvailable] = useState(false);

  useEffect(() => {
    AppleAuthentication.isAvailableAsync().then(setAppleAvailable).catch(() => setAppleAvailable(false));
  }, []);

  const mapError = (msg: string) => {
    if (msg.includes("email_exists")) return t("emailExistsMsg");
    if (msg.includes("weak_password")) return t("weakPasswordMsg");
    if (msg.includes("invalid_email")) return t("invalidEmailMsg");
    if (msg.includes("invalid_credentials")) return t("authError");
    if (msg.includes("not_registered")) return t("notRegisteredMsg");
    return t("authError");
  };

  const onEmailAuth = async () => {
    setError("");
    if (!email.trim() || !password) { setError(t("authError")); return; }
    setLoading("email");
    try {
      if (mode === "signup") await register(email.trim(), password, name.trim());
      else await loginEmail(email.trim(), password);
      router.replace("/");
    } catch (e: any) {
      setError(mapError(String(e?.message || "")));
      setLoading(null);
    }
  };

  const onGoogle = async () => {
    setError(""); setLoading("google");
    try { await login(mode); router.replace("/"); }
    catch (e: any) {
      setError(mapError(String(e?.message || "")));
      setLoading(null);
    }
  };

  const onApple = async () => {
    setError("");
    try {
      const cred = await AppleAuthentication.signInAsync({
        requestedScopes: [
          AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
          AppleAuthentication.AppleAuthenticationScope.EMAIL,
        ],
      });
      if (!cred.identityToken) return;
      const fullName = cred.fullName ? [cred.fullName.givenName, cred.fullName.familyName].filter(Boolean).join(" ") : null;
      setLoading("apple");
      await loginApple(cred.identityToken, fullName, cred.email);
      router.replace("/");
    } catch (e: any) {
      if (e?.code === "ERR_REQUEST_CANCELED") return;
      setError(t("authError"));
      setLoading(null);
    }
  };

  const onDemo = async () => {
    setError(""); setLoading("demo");
    try { await loginDemo(); router.replace("/(tabs)"); } catch { setLoading(null); }
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top }]} testID="onboarding-screen">
      {/* BLOCCO 9 (richiesta utente: aggiungere Cinese/Russo/Tedesco/
          Spagnolo/Francese): con 7 lingue la riga fissa in alto a destra
          non ci stava più su schermo — ora scorre orizzontalmente invece
          di traboccare fuori dallo schermo. */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={[styles.langRow, { top: insets.top + spacing.sm }]} contentContainerStyle={{ gap: spacing.xs }}>
        {SUPPORTED_LANGS.map((l) => (
          <Pressable key={l} testID={`lang-${l}`} onPress={() => setLang(l)} style={[styles.langChip, lang === l && styles.langChipActive]}>
            <Text style={[styles.langText, lang === l && styles.langTextActive]}>{l.toUpperCase()}</Text>
          </Pressable>
        ))}
      </ScrollView>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
          <Image source={require("@/assets/images/jobby-logo.png")} style={styles.logo} contentFit="contain" />
          <Text style={styles.tagline}>{t("appTagline")}</Text>

          {/* segmented signin/signup */}
          <View style={styles.segment}>
            {(["signin", "signup"] as const).map((m) => (
              <Pressable key={m} testID={`seg-${m}`} style={[styles.segBtn, mode === m && styles.segBtnOn]} onPress={() => { setMode(m); setError(""); }}>
                <Text style={[styles.segText, mode === m && styles.segTextOn]}>{m === "signin" ? t("signIn") : t("signUp")}</Text>
              </Pressable>
            ))}
          </View>

          <Text style={styles.formTitle}>{mode === "signin" ? t("welcomeBack") : t("createAccount")}</Text>

          {mode === "signup" ? (
            <TextInput testID="auth-name" style={styles.input} value={name} onChangeText={setName} placeholder={t("nameLabel")} placeholderTextColor="rgba(255,255,255,0.4)" />
          ) : null}
          <TextInput testID="auth-email" style={styles.input} value={email} onChangeText={setEmail} placeholder={t("emailLabel")} placeholderTextColor="rgba(255,255,255,0.4)" keyboardType="email-address" autoCapitalize="none" />
          <TextInput testID="auth-password" style={styles.input} value={password} onChangeText={setPassword} placeholder={t("passwordLabel")} placeholderTextColor="rgba(255,255,255,0.4)" secureTextEntry />

          {error ? <Text style={styles.error} testID="auth-error">{error}</Text> : null}

          <Button testID="auth-submit" label={mode === "signin" ? t("signIn") : t("signUp")} loading={loading === "email"} onPress={onEmailAuth} style={{ marginTop: spacing.md }} />

          <View style={styles.divider}><View style={styles.line} /><Text style={styles.orText}>{t("orDivider")}</Text><View style={styles.line} /></View>

          <Button testID="google-login-button" label={t("continueGoogle")} onPress={onGoogle} loading={loading === "google"} variant="secondary" icon="logo-google" />

          {appleAvailable ? (
            <AppleAuthentication.AppleAuthenticationButton
              testID="apple-login-button"
              buttonType={AppleAuthentication.AppleAuthenticationButtonType.CONTINUE}
              buttonStyle={AppleAuthentication.AppleAuthenticationButtonStyle.WHITE}
              cornerRadius={12}
              style={styles.appleBtn}
              onPress={onApple}
            />
          ) : null}

          <Pressable testID="demo-button" style={styles.demoBtn} onPress={onDemo}>
            <Ionicons name="eye-outline" size={18} color="rgba(255,255,255,0.85)" />
            <Text style={styles.demoText}>{loading === "demo" ? t("signingIn") : t("tryDemo")}</Text>
          </Pressable>
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: NAVY },
  scroll: { paddingHorizontal: spacing.xl, paddingBottom: spacing["2xl"], alignItems: "stretch" },
  langRow: { position: "absolute", right: spacing.lg, flexDirection: "row", gap: spacing.xs, zIndex: 2 },
  langChip: { paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill, backgroundColor: "rgba(255,255,255,0.15)" },
  langChipActive: { backgroundColor: "#fff" },
  langText: { color: "#fff", fontFamily: font.medium, fontSize: fsize.sm },
  langTextActive: { color: NAVY },
  logo: { width: 150, height: 150, alignSelf: "center", marginTop: spacing.xl },
  tagline: { color: "rgba(255,255,255,0.85)", fontSize: fsize.base, fontFamily: font.regular, textAlign: "center", marginBottom: spacing.lg },
  segment: { flexDirection: "row", backgroundColor: "rgba(255,255,255,0.12)", borderRadius: radius.pill, padding: 4, marginBottom: spacing.lg },
  segBtn: { flex: 1, paddingVertical: 10, borderRadius: radius.pill, alignItems: "center" },
  segBtnOn: { backgroundColor: "#fff" },
  segText: { color: "rgba(255,255,255,0.85)", fontFamily: font.medium, fontSize: fsize.base },
  segTextOn: { color: NAVY, fontFamily: font.bold },
  formTitle: { color: "#fff", fontSize: fsize.xl, fontFamily: font.bold, marginBottom: spacing.md },
  input: { backgroundColor: "rgba(255,255,255,0.10)", borderRadius: radius.md, paddingHorizontal: spacing.md, height: 52, color: "#fff", fontSize: fsize.lg, fontFamily: font.regular, marginBottom: spacing.sm, borderWidth: 1, borderColor: "rgba(255,255,255,0.15)" },
  error: { color: "#FF9B8A", fontSize: fsize.base, fontFamily: font.medium, marginTop: 4 },
  divider: { flexDirection: "row", alignItems: "center", gap: spacing.md, marginVertical: spacing.lg },
  line: { flex: 1, height: 1, backgroundColor: "rgba(255,255,255,0.2)" },
  orText: { color: "rgba(255,255,255,0.6)", fontSize: fsize.sm, fontFamily: font.regular },
  appleBtn: { height: 50, marginTop: spacing.md },
  demoBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, marginTop: spacing.lg, paddingVertical: spacing.md },
  demoText: { color: "rgba(255,255,255,0.85)", fontSize: fsize.base, fontFamily: font.medium, textDecorationLine: "underline" },
});
