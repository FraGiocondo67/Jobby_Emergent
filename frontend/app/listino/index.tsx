import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput, Modal, Alert, KeyboardAvoidingView, Platform, Linking,
} from "react-native";
import { Image } from "expo-image";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as ImagePicker from "expo-image-picker";
import * as Haptics from "expo-haptics";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Button } from "@/src/components/UI";

const UNITS = ["pz", "nr", "hr", "kg", "bulk"] as const;

export default function ListinoScreen() {
  const { user } = useAuth();
  const { t, lang } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const services: string[] = user?.services || [];
  const [catLabels, setCatLabels] = useState<Record<string, any>>({});
  const [category, setCategory] = useState<string>(services[0] || "");  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // editor modal
  const [editing, setEditing] = useState<any | null>(null); // product being edited (null = closed)
  const [descrizione, setDescrizione] = useState("");
  const [prezzo, setPrezzo] = useState("");
  const [unita, setUnita] = useState<string>("pz");
  const [foto, setFoto] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const cats = await api.categories();
        const all = [...(cats.standard || []), ...(cats.proximity || []), ...(cats.payment || [])];
        const map: Record<string, any> = {};
        all.forEach((c: any) => { map[c.cat_id] = c.label; });
        setCatLabels(map);
      } catch {}
    })();
  }, []);

  const load = useCallback(async () => {
    if (!category) { setLoading(false); return; }
    setLoading(true);
    try { setItems(await api.myListino(category)); } catch {}
    finally { setLoading(false); }
  }, [category]);
  useEffect(() => { load(); }, [load]);

  // Auto-select first service once AuthContext.user resolves.
  useEffect(() => {
    if (!category && services.length) setCategory(services[0]);
  }, [services, category]);

  const label = (cat: string) => catLabels[cat]?.[lang] || cat;

  const openNew = () => {
    setEditing({ item_id: null });
    setDescrizione(""); setPrezzo(""); setUnita("pz"); setFoto(null);
  };
  const openEdit = (p: any) => {
    setEditing(p);
    setDescrizione(p.descrizione); setPrezzo(String(p.prezzo)); setUnita(p.unita || "pz"); setFoto(p.foto || null);
  };

  const pickImage = async (useCamera: boolean) => {
    const perm = useCamera ? await ImagePicker.requestCameraPermissionsAsync() : await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      Alert.alert(t("permissionNeeded"), "", [{ text: "OK" }, { text: t("openSettings"), onPress: () => Linking.openSettings() }]);
      return;
    }
    const res = useCamera
      ? await ImagePicker.launchCameraAsync({ quality: 0.35, base64: true })
      : await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, quality: 0.35, base64: true });
    if (res.canceled || !res.assets?.[0]?.base64) return;
    setFoto(`data:image/jpeg;base64,${res.assets[0].base64}`);
  };

  const choosePhoto = () => {
    Alert.alert(t("productPhoto"), "", [
      { text: t("takePhoto"), onPress: () => pickImage(true) },
      { text: t("chooseFromGallery"), onPress: () => pickImage(false) },
      { text: t("cancel"), style: "cancel" },
    ]);
  };

  const save = async () => {
    const price = Number(prezzo);
    if (!descrizione.trim() || !price || price <= 0) { Alert.alert(t("error")); return; }
    setBusy(true);
    try {
      const payload = { category, descrizione: descrizione.trim(), unita, prezzo: price, foto };
      if (editing?.item_id) await api.updateProduct(editing.item_id, payload);
      else await api.createProduct(payload);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      setEditing(null);
      load();
    } catch { Alert.alert(t("error")); } finally { setBusy(false); }
  };

  const remove = (p: any) => {
    Alert.alert(t("deleteProductConfirm"), "", [
      { text: t("cancel"), style: "cancel" },
      { text: t("delete") || "Elimina", style: "destructive", onPress: async () => {
        try { await api.deleteProduct(p.item_id); load(); } catch { Alert.alert(t("error")); }
      } },
    ]);
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="listino-back" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.primary} />
          <Text style={styles.backText}>Back</Text>
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 120 }} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>{t("myListino")}</Text>
        <Text style={styles.subtitle}>{t("myListinoSub")}</Text>

        {/* category selector */}
        {services.length > 1 ? (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, paddingVertical: spacing.md }}>
            {services.map((c) => (
              <Pressable key={c} testID={`listino-cat-${c}`} onPress={() => setCategory(c)} style={[styles.catChip, category === c && styles.catChipOn]}>
                <Text style={[styles.catText, category === c && { color: "#fff" }]}>{label(c)}</Text>
              </Pressable>
            ))}
          </ScrollView>
        ) : null}

        {!category ? (
          <Text style={styles.empty}>{t("selectCategoryFirst")}</Text>
        ) : items.length === 0 && !loading ? (
          <View style={styles.emptyWrap} testID="listino-empty">
            <Text style={{ fontSize: 44 }}>🛒</Text>
            <Text style={styles.emptyTitle}>{t("noProductsYet")}</Text>
            <Text style={styles.emptySub}>{t("noProductsHint")}</Text>
          </View>
        ) : (
          <View style={{ marginTop: spacing.md, gap: spacing.md }}>
            {items.map((p) => (
              <View key={p.item_id} style={[styles.card, shadow.card]} testID={`product-${p.item_id}`}>
                {p.foto ? (
                  <Image source={{ uri: p.foto }} style={styles.thumb} contentFit="cover" />
                ) : (
                  <View style={[styles.thumb, styles.thumbFallback]}><Ionicons name="cube-outline" size={26} color={colors.muted} /></View>
                )}
                <View style={{ flex: 1 }}>
                  <Text style={styles.pName}>{p.descrizione}</Text>
                  <Text style={styles.pMeta}>{t(`unit_${p.unita}` as any)}</Text>
                  <Text style={styles.pPrice}>€{Number(p.prezzo).toFixed(2)}</Text>
                </View>
                <View style={{ gap: spacing.sm }}>
                  <Pressable testID={`edit-${p.item_id}`} onPress={() => openEdit(p)} hitSlop={8} style={styles.iconBtn}><Ionicons name="pencil" size={18} color={colors.primary} /></Pressable>
                  <Pressable testID={`del-${p.item_id}`} onPress={() => remove(p)} hitSlop={8} style={styles.iconBtn}><Ionicons name="trash-outline" size={18} color={colors.error} /></Pressable>
                </View>
              </View>
            ))}
          </View>
        )}
      </ScrollView>

      {category ? (
        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          <Button testID="listino-add" label={t("addProduct")} icon="add" onPress={openNew} />
        </View>
      ) : null}

      {/* Editor modal */}
      <Modal visible={!!editing} transparent animationType="slide" onRequestClose={() => setEditing(null)}>
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
          <View style={styles.overlay}>
            <View style={[styles.modalCard, { paddingBottom: insets.bottom + spacing.lg }]}>
              <View style={styles.modalHandle} />
              <Text style={styles.modalTitle}>{editing?.item_id ? t("editProduct") : t("newProduct")}</Text>
              <ScrollView showsVerticalScrollIndicator={false}>
                <Pressable testID="product-photo" onPress={choosePhoto} style={styles.photoBox}>
                  {foto ? (
                    <Image source={{ uri: foto }} style={styles.photoPreview} contentFit="cover" />
                  ) : (
                    <View style={styles.photoPlaceholder}>
                      <Ionicons name="camera" size={28} color={colors.muted} />
                      <Text style={styles.photoHint}>{t("productPhoto")}</Text>
                    </View>
                  )}
                </Pressable>
                {foto ? <Pressable onPress={() => setFoto(null)} style={{ alignSelf: "center", padding: 6 }}><Text style={styles.removePhoto}>{t("removePhoto")}</Text></Pressable> : null}

                <Text style={styles.label}>{t("productDesc")}</Text>
                <TextInput testID="product-desc" style={styles.input} value={descrizione} onChangeText={setDescrizione} placeholderTextColor={colors.muted} />

                <Text style={styles.label}>{t("productUnit")}</Text>
                <View style={styles.unitRow}>
                  {UNITS.map((u) => (
                    <Pressable key={u} testID={`unit-${u}`} onPress={() => setUnita(u)} style={[styles.unitChip, unita === u && styles.unitChipOn]}>
                      <Text style={[styles.unitText, unita === u && { color: "#fff" }]}>{u.toUpperCase()}</Text>
                    </Pressable>
                  ))}
                </View>

                <Text style={styles.label}>{t("productPrice")} (€)</Text>
                <TextInput testID="product-price" style={styles.input} value={prezzo} onChangeText={setPrezzo} keyboardType="decimal-pad" placeholder="0.00" placeholderTextColor={colors.muted} />

                <View style={styles.actionRow}>
                  <Button testID="product-cancel" label={t("cancel")} variant="secondary" onPress={() => setEditing(null)} style={{ flex: 1 }} />
                  <Button testID="product-save" label={t("saveProduct")} loading={busy} onPress={save} style={{ flex: 1 }} />
                </View>
              </ScrollView>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  backBtn: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start" },
  backText: { color: colors.primary, fontSize: fsize.xl, fontFamily: font.medium },
  title: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface },
  subtitle: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 2 },
  catChip: { paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  catChipOn: { backgroundColor: colors.purple, borderColor: colors.purple },
  catText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary },
  empty: { fontSize: fsize.base, color: colors.muted, marginTop: spacing.xl, textAlign: "center" },
  emptyWrap: { alignItems: "center", gap: spacing.sm, paddingVertical: spacing["3xl"] },
  emptyTitle: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.onSurface, marginTop: spacing.sm },
  emptySub: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, textAlign: "center" },
  card: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
  thumb: { width: 60, height: 60, borderRadius: radius.sm },
  thumbFallback: { backgroundColor: colors.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  pName: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  pMeta: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 1 },
  pPrice: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.brand, marginTop: 2 },
  iconBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.lg, paddingTop: spacing.md, backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderTopColor: colors.divider },
  overlay: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  modalCard: { backgroundColor: colors.surface, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, padding: spacing.lg, maxHeight: "90%" },
  modalHandle: { width: 40, height: 4, borderRadius: 2, backgroundColor: colors.borderStrong, alignSelf: "center", marginBottom: spacing.md },
  modalTitle: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.onSurface, marginBottom: spacing.md },
  photoBox: { alignSelf: "center", width: 140, height: 140, borderRadius: radius.md, overflow: "hidden", marginBottom: spacing.sm },
  photoPreview: { width: "100%", height: "100%" },
  photoPlaceholder: { flex: 1, backgroundColor: colors.surfaceTertiary, alignItems: "center", justifyContent: "center", gap: 6, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, borderStyle: "dashed" },
  photoHint: { fontSize: fsize.sm, color: colors.muted, fontFamily: font.medium },
  removePhoto: { fontSize: fsize.sm, color: colors.error, fontFamily: font.medium },
  label: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary, marginTop: spacing.md, marginBottom: spacing.sm },
  input: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  unitRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  unitChip: { paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  unitChipOn: { backgroundColor: colors.purple, borderColor: colors.purple },
  unitText: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.onSurfaceTertiary },
  actionRow: { flexDirection: "row", gap: spacing.md, marginTop: spacing.xl },
});
