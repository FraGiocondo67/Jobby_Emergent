import React, { useEffect, useState } from "react";
import {
  View, Text, StyleSheet, Pressable, ScrollView, TextInput, KeyboardAvoidingView, Platform, Alert,
} from "react-native";
import { Image } from "expo-image";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as ImagePicker from "expo-image-picker";
import * as Location from "expo-location";
import * as Haptics from "expo-haptics";
import Slider from "@react-native-community/slider";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Button } from "@/src/components/UI";

const TREVISO = { lat: 45.6669, lng: 12.2433 };

const ROLES = [
  { id: "client", emoji: "🙋", titleKey: "roleClient", descKey: "roleClientDesc" },
  { id: "provider", emoji: "🧰", titleKey: "roleProviderName", descKey: "roleProviderDesc" },
  { id: "business", emoji: "🏪", titleKey: "roleBusiness", descKey: "roleBusinessDesc" },
] as const;

export default function OnboardingFlow() {
  const { user, setUser } = useAuth();
  const { lang, t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [step, setStep] = useState(0);
  const [role, setRole] = useState<string>("");
  const [name, setName] = useState(user?.name || "");
  const [phone, setPhone] = useState(user?.phone || "");
  const [address, setAddress] = useState(user?.address || "");
  const [coords, setCoords] = useState({ lat: user?.lat || TREVISO.lat, lng: user?.lng || TREVISO.lng });
  const [businessName, setBusinessName] = useState("");
  const [vat, setVat] = useState("");
  const [services, setServices] = useState<string[]>([]);
  const [radiusKm, setRadiusKm] = useState(10);
  const [cats, setCats] = useState<any[]>([]);
  const [photos, setPhotos] = useState<string[]>([]);
  const [hasLicense, setHasLicense] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const c = await api.categories();
        setCats(role === "business" ? c.proximity : c.standard);
      } catch {}
    })();
  }, [role]);

  const useMyLocation = async () => {
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== "granted") return;
      const loc = await Location.getCurrentPositionAsync({});
      setCoords({ lat: loc.coords.latitude, lng: loc.coords.longitude });
      setAddress(`${loc.coords.latitude.toFixed(4)}, ${loc.coords.longitude.toFixed(4)} · Treviso`);
    } catch {}
  };

  const toggleService = (id: string) => {
    Haptics.selectionAsync().catch(() => {});
    setServices((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const pickImage = async (): Promise<string | null> => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      Alert.alert(t("permissionPhotos"), "", [{ text: "OK" }]);
      return null;
    }
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.35,
      base64: true,
    });
    if (res.canceled || !res.assets?.[0]?.base64) return null;
    return `data:image/jpeg;base64,${res.assets[0].base64}`;
  };

  const addPhoto = async () => {
    if (photos.length >= 4) return;
    const img = await pickImage();
    if (!img) return;
    try {
      const r = await api.addBusinessPhoto(img);
      setPhotos(r.business_photos);
    } catch {}
  };

  const removePhoto = async (i: number) => {
    try {
      const r = await api.deleteBusinessPhoto(i);
      setPhotos(r.business_photos);
    } catch {}
  };

  const uploadLicense = async () => {
    const img = await pickImage();
    if (!img) return;
    try {
      await api.setBusinessDocument(img);
      setHasLicense(true);
    } catch {}
  };

  const canSubmit = () => {
    if (role === "client") return !!address.trim();
    if (role === "provider") return services.length > 0;
    if (role === "business") return !!businessName.trim() && !!vat.trim() && services.length > 0 && hasLicense;
    return false;
  };

  const submit = async () => {
    setBusy(true);
    try {
      const payload: any = { role, name: name.trim() || undefined, phone, address, lat: coords.lat, lng: coords.lng };
      if (role === "provider" || role === "business") {
        payload.services = services;
        payload.radius_km = radiusKm;
      }
      if (role === "business") {
        payload.business_name = businessName.trim();
        payload.vat_number = vat.trim();
        payload.service_mode = "both";
      }
      const updated = await api.completeOnboarding(payload);
      setUser(updated);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      router.replace("/(tabs)");
    } catch {
      setBusy(false);
    }
  };

  // ---- Step 0: role ----
  if (step === 0) {
    return (
      <View style={[styles.container, { paddingTop: insets.top + spacing.xl }]} testID="onboarding-flow">
        <View style={styles.body}>
          <Text style={styles.title}>{t("onboardingRoleTitle")}</Text>
          <Text style={styles.sub}>{t("onboardingRoleSub")}</Text>
          <View style={{ gap: spacing.md, marginTop: spacing.xl }}>
            {ROLES.map((r) => (
              <Pressable key={r.id} testID={`role-${r.id}`} style={[styles.roleCard, role === r.id && styles.roleCardOn, shadow.card]} onPress={() => setRole(r.id)}>
                <Text style={{ fontSize: 34 }}>{r.emoji}</Text>
                <View style={{ flex: 1 }}>
                  <Text style={styles.roleTitle}>{t(r.titleKey as any)}</Text>
                  <Text style={styles.roleDesc}>{t(r.descKey as any)}</Text>
                </View>
                {role === r.id ? <Ionicons name="checkmark-circle" size={24} color={colors.brand} /> : <Ionicons name="ellipse-outline" size={24} color={colors.border} />}
              </Pressable>
            ))}
          </View>
        </View>
        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          <Button testID="role-next" label={t("next")} disabled={!role} onPress={() => setStep(1)} />
        </View>
      </View>
    );
  }

  // ---- Step 1: details ----
  return (
    <View style={styles.container} testID="onboarding-flow">
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="onb-back" onPress={() => setStep(0)} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.primary} />
          <Text style={styles.backText}>{t("backStep")}</Text>
        </Pressable>
      </View>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 160 }} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
          <Text style={styles.title}>{t("yourDetails")}</Text>

          {role === "business" ? (
            <>
              <Text style={styles.label}>{t("businessNameLabel")}</Text>
              <TextInput testID="onb-bizname" style={styles.input} value={businessName} onChangeText={setBusinessName} placeholder={t("businessNamePlaceholder")} placeholderTextColor={colors.muted} />
            </>
          ) : (
            <>
              <Text style={styles.label}>{t("nameLabel")}</Text>
              <TextInput testID="onb-name" style={styles.input} value={name} onChangeText={setName} placeholder={t("nameLabel")} placeholderTextColor={colors.muted} />
            </>
          )}

          <Text style={styles.label}>{t("phoneLabel2")}</Text>
          <TextInput testID="onb-phone" style={styles.input} value={phone} onChangeText={setPhone} keyboardType="phone-pad" placeholder="+39 ..." placeholderTextColor={colors.muted} />

          <Text style={styles.label}>{t("addressLabel")}</Text>
          <TextInput testID="onb-address" style={styles.input} value={address} onChangeText={setAddress} placeholder="Via Roma 12, Treviso" placeholderTextColor={colors.muted} />
          <Button label={t("useMyLocation")} variant="secondary" icon="navigate" onPress={useMyLocation} testID="onb-location" style={{ marginTop: spacing.sm, height: 46 }} />

          {(role === "provider" || role === "business") ? (
            <>
              <Text style={styles.label}>{t("selectYourActivities")}</Text>
              <View style={styles.chipGrid}>
                {cats.map((c) => {
                  const on = services.includes(c.cat_id);
                  return (
                    <Pressable key={c.cat_id} testID={`onb-activity-${c.cat_id}`} style={[styles.chip, on && styles.chipOn]} onPress={() => toggleService(c.cat_id)}>
                      <Text style={{ fontSize: 18 }}>{c.emoji}</Text>
                      <Text style={[styles.chipText, on && { color: "#fff" }]}>{c.label[lang]}</Text>
                    </Pressable>
                  );
                })}
              </View>
              <View style={styles.radiusHead}>
                <Text style={styles.label}>{t("serviceRadius")}</Text>
                <Text style={styles.radiusVal}>{radiusKm} km</Text>
              </View>
              <Slider testID="onb-radius" style={{ width: "100%", height: 40 }} minimumValue={1} maximumValue={50} step={1} value={radiusKm} onValueChange={(v) => setRadiusKm(Math.round(v))} minimumTrackTintColor={colors.brand} maximumTrackTintColor={colors.borderStrong} thumbTintColor={colors.brand} />
            </>
          ) : null}

          {role === "business" ? (
            <>
              <Text style={styles.blockTitle}>{t("fiscalData")}</Text>
              <Text style={styles.label}>{t("vatNumber")}</Text>
              <TextInput testID="onb-vat" style={styles.input} value={vat} onChangeText={setVat} placeholder={t("vatPlaceholder")} placeholderTextColor={colors.muted} autoCapitalize="characters" />

              <Text style={styles.label}>{t("uploadLicense")}</Text>
              <Pressable testID="onb-license" style={[styles.uploadBox, hasLicense && styles.uploadBoxOn]} onPress={uploadLicense}>
                <Ionicons name={hasLicense ? "checkmark-circle" : "document-attach-outline"} size={22} color={hasLicense ? colors.success : colors.brand} />
                <Text style={[styles.uploadText, hasLicense && { color: colors.success }]}>{hasLicense ? t("licenseUploaded") : t("uploadLicense")}</Text>
              </Pressable>

              <Text style={styles.label}>{t("businessPhotos")}</Text>
              <View style={styles.photoRow}>
                {photos.map((p, i) => (
                  <View key={i} style={styles.photoWrap} testID={`onb-photo-${i}`}>
                    <Image source={{ uri: p }} style={styles.photo} contentFit="cover" />
                    <Pressable testID={`onb-photo-del-${i}`} style={styles.photoDel} onPress={() => removePhoto(i)} hitSlop={8}>
                      <Ionicons name="close" size={14} color="#fff" />
                    </Pressable>
                  </View>
                ))}
                {photos.length < 4 ? (
                  <Pressable testID="onb-add-photo" style={styles.addPhoto} onPress={addPhoto}>
                    <Ionicons name="camera-outline" size={26} color={colors.muted} />
                    <Text style={styles.addPhotoText}>{t("addPhoto")}</Text>
                  </Pressable>
                ) : null}
              </View>
              <Text style={styles.note}>{t("pendingApprovalNote")}</Text>
            </>
          ) : null}
        </ScrollView>
        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          <Button testID="onb-submit" label={t("finishOnboarding")} loading={busy} disabled={!canSubmit()} onPress={submit} />
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
  body: { flex: 1, paddingHorizontal: spacing.lg },
  title: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface },
  sub: { fontSize: fsize.lg, fontFamily: font.regular, color: colors.muted, marginTop: spacing.xs },
  roleCard: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1.5, borderColor: colors.border, padding: spacing.lg },
  roleCardOn: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  roleTitle: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.onSurface },
  roleDesc: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 2 },
  label: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary, marginTop: spacing.lg, marginBottom: spacing.sm },
  input: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  chipGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  chipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  radiusHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  radiusVal: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.brand, marginTop: spacing.lg },
  blockTitle: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.onSurface, marginTop: spacing.xl },
  uploadBox: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, borderWidth: 1.5, borderStyle: "dashed", borderColor: colors.brand, borderRadius: radius.md, paddingVertical: spacing.lg, backgroundColor: colors.brandTertiary },
  uploadBoxOn: { borderColor: colors.success, backgroundColor: colors.greenBg, borderStyle: "solid" },
  uploadText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.brand },
  photoRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  photoWrap: { position: "relative" },
  photo: { width: 76, height: 76, borderRadius: radius.md },
  photoDel: { position: "absolute", top: -6, right: -6, width: 22, height: 22, borderRadius: 11, backgroundColor: colors.error, alignItems: "center", justifyContent: "center" },
  addPhoto: { width: 76, height: 76, borderRadius: radius.md, borderWidth: 1, borderStyle: "dashed", borderColor: colors.borderStrong, alignItems: "center", justifyContent: "center", gap: 2 },
  addPhotoText: { fontSize: 10, fontFamily: font.regular, color: colors.muted },
  note: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: spacing.md, fontStyle: "italic" },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.lg, paddingTop: spacing.md, backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderTopColor: colors.divider },
});
