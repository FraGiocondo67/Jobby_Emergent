// BLOCCO 9 (fix "Profilo / verifica identità: ancora non è attivo e non
// salva nulla e non carica nulla"): questa schermata era un mock lasciato
// dalla migrazione Emergent — due semplici toggle locali (setDoc(true)/
// setSelfie(true), MAI un vero upload) e un pulsante che chiamava
// POST /verification/start e /verification/complete, endpoint MAI portati
// su questo backend Postgres (vedi routers/auth.py, docstring: "verification/*
// dipendevano da campi Mongo senza equivalente ancora deciso... da riprendere
// insieme al KYC reale via Sumsub"). Il vero SUMSUB non è ancora integrato
// (richiede credenziali/contratto non disponibili qui) — nel frattempo
// questa schermata usa lo STESSO meccanismo di upload documenti già reale e
// funzionante dell'onboarding (POST /onboarding/provider/document, vedi
// provider-onboarding.tsx uploadDoc()), così chi deve ricaricare/completare
// i documenti d'identità dopo l'onboarding può farlo davvero, invece di
// premere due checkbox finte che non salvano niente.
import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, Alert } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as ImagePicker from "expo-image-picker";
import * as Haptics from "expo-haptics";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";

export default function Verification() {
  const { user, refresh } = useAuth();
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [status, setStatus] = useState<any>(null);
  const [busyKind, setBusyKind] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setStatus(await api.providerStatus()); } catch {}
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  // kyc_status reale (profiles_provider.kyc_status, scritto da
  // submit_provider()/admin_decision() — vedi routers/provider_onboarding.py):
  // null/not_started/pending/approved/rejected. Prima si confrontava
  // verification_status con la stringa "verified", che il backend non
  // produce MAI — restava "non verificato" anche dopo l'approvazione admin.
  const kyc = user?.verification_status;
  const approved = kyc === "approved";
  const pending = kyc === "pending";
  const rejected = kyc === "rejected";

  const pickImage = async (useCamera: boolean) => {
    const perm = useCamera ? await ImagePicker.requestCameraPermissionsAsync() : await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return null;
    const res = useCamera
      ? await ImagePicker.launchCameraAsync({ quality: 0.35, base64: true })
      : await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, quality: 0.35, base64: true });
    if (res.canceled || !res.assets?.[0]?.base64) return null;
    return `data:image/jpeg;base64,${res.assets[0].base64}`;
  };

  const uploadDoc = async (kind: "id_front" | "id_back" | "selfie") => {
    const img = await pickImage(kind === "selfie");
    if (!img) return;
    setBusyKind(kind);
    try {
      await api.uploadProviderDoc(kind, img);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      await load();
      await refresh();
    } catch { Alert.alert(t("error")); }
    finally { setBusyKind(null); }
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="verification-back" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.primary} />
          <Text style={styles.backText}>Back</Text>
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }}>
        <Text style={styles.bigEmoji}>🛡️</Text>
        <Text style={styles.title}>{t("verifyIdentity")}</Text>
        <Text style={styles.desc}>{t("verificationDesc")}</Text>
        <View style={styles.mockBadge}><Text style={styles.mockText}>Sumsub · {t("mockNote")}</Text></View>

        {approved ? (
          <View style={styles.verifiedBox}>
            <Ionicons name="checkmark-circle" size={30} color={colors.success} />
            <Text style={styles.verifiedText}>{t("identityVerified")}</Text>
          </View>
        ) : (
          <View style={{ marginTop: spacing.xl, gap: spacing.md }}>
            {pending ? (
              <View style={styles.pendingBox}><Ionicons name="hourglass-outline" size={20} color={colors.warning} /><Text style={styles.pendingText}>{t("waitingProposals")}</Text></View>
            ) : null}
            {rejected ? (
              <View style={styles.pendingBox}><Ionicons name="close-circle-outline" size={20} color={colors.error} /><Text style={[styles.pendingText, { color: colors.error }]}>{t("error")}</Text></View>
            ) : null}
            <Pressable testID="upload-document" style={[styles.step, status?.has_id && styles.stepDone]} onPress={() => uploadDoc("id_front")} disabled={busyKind === "id_front"}>
              <Ionicons name={status?.has_id ? "checkmark-circle" : "document-text-outline"} size={24} color={status?.has_id ? colors.success : colors.onSurfaceTertiary} />
              <Text style={styles.stepText}>{t("uploadDocument")}</Text>
            </Pressable>
            <Pressable testID="take-selfie" style={[styles.step, status?.has_selfie && styles.stepDone]} onPress={() => uploadDoc("selfie")} disabled={busyKind === "selfie"}>
              <Ionicons name={status?.has_selfie ? "checkmark-circle" : "camera-outline"} size={24} color={status?.has_selfie ? colors.success : colors.onSurfaceTertiary} />
              <Text style={styles.stepText}>{t("takeSelfie")}</Text>
            </Pressable>
          </View>
        )}
      </ScrollView>
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
  pendingBox: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md },
  pendingText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.warning },
  step: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, ...shadow.card },
  stepDone: { borderColor: colors.success, backgroundColor: colors.greenBg },
  stepText: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  verifiedBox: { alignItems: "center", gap: spacing.sm, marginTop: spacing["2xl"] },
  verifiedText: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.success },
});
