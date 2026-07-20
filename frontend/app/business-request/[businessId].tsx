import React, { useEffect, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput, KeyboardAvoidingView, Platform, Alert,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Location from "expo-location";
import * as Haptics from "expo-haptics";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Button } from "@/src/components/UI";

const TREVISO = { lat: 45.6669, lng: 12.2433 };

export default function BusinessRequestScreen() {
  const { businessId, category, name, label } = useLocalSearchParams<{ businessId: string; category: string; name: string; label: string }>();
  const { user, setUser } = useAuth();
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [products, setProducts] = useState<any[]>([]);
  const [qty, setQty] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [note, setNote] = useState("");
  const [address, setAddress] = useState("Via Roma 12, Treviso");
  const [coords, setCoords] = useState({ lat: user?.lat || TREVISO.lat, lng: user?.lng || TREVISO.lng });
  const [budget, setBudget] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  const available = Number(user?.wallet_balance || 0) + Number(user?.bonus_credit || 0);

  useEffect(() => {
    (async () => {
      try { setProducts(await api.businessListino(businessId as string, category as string)); } catch {}
      finally { setLoading(false); }
    })();
  }, [businessId, category]);

  const hasCatalog = products.length > 0;
  const total = products.reduce((s, p) => s + (qty[p.item_id] || 0) * Number(p.prezzo), 0);
  const itemCount = Object.values(qty).reduce((s, n) => s + (n > 0 ? 1 : 0), 0);

  const setQ = (id: string, delta: number) => {
    Haptics.selectionAsync().catch(() => {});
    setQty((prev) => {
      const next = Math.max(0, (prev[id] || 0) + delta);
      return { ...prev, [id]: next };
    });
  };

  const useMyLocation = async () => {
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== "granted") return;
      const loc = await Location.getCurrentPositionAsync({});
      const c = { lat: loc.coords.latitude, lng: loc.coords.longitude };
      setCoords(c);
      try { const r = await api.reverseGeocode(c.lat, c.lng); if (r?.label) setAddress(r.label); } catch {}
    } catch {}
  };

  // Converte l'indirizzo digitato in coordinate reali; ritorna le coord da usare.
  const resolveCoords = async () => {
    try {
      const g = await api.geocode(address);
      if (g && !g.fallback) { const c = { lat: g.lat, lng: g.lng }; setCoords(c); return c; }
    } catch {}
    return coords;
  };

  const placeOrder = async () => {
    if (total <= 0) return;
    if (total > available) { Alert.alert(t("insufficientWallet")); return; }
    setSubmitting(true);
    try {
      const c = await resolveCoords();
      const items = products.filter((p) => (qty[p.item_id] || 0) > 0).map((p) => ({ item_id: p.item_id, qty: qty[p.item_id] }));
      await api.createOrder({
        business_id: businessId as string, category: category as string, items,
        address, lat: c.lat, lng: c.lng, note: note.trim(),
      });
      try { setUser(await api.me()); } catch {}
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      setSuccess(true);
    } catch (e: any) {
      if (String(e?.message).includes("insufficient_wallet")) Alert.alert(t("insufficientWallet"));
      setSubmitting(false);
    }
  };

  const sendFreeRequest = async () => {
    if (!note.trim()) return;
    setSubmitting(true);
    try {
      const c = await resolveCoords();
      await api.createBusinessRequest({
        business_id: businessId as string, category: category as string, note: note.trim(),
        address, lat: c.lat, lng: c.lng, budget: budget.trim() ? Number(budget) : null,
      });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      setSuccess(true);
    } catch { setSubmitting(false); }
  };

  if (success) {
    return (
      <View style={[styles.container, styles.successWrap]}>
        <Text style={{ fontSize: 64 }}>📨</Text>
        <Text style={styles.successTitle}>{hasCatalog ? t("orderPlaced") : t("requestSent")}</Text>
        <Text style={styles.successSub}>{hasCatalog ? t("orderPlacedDesc") : t("requestSentDesc")} {name}</Text>
        <Button testID="done-button" label={t("done")} onPress={() => router.replace("/(tabs)/richieste")} style={{ marginTop: spacing.xl, minWidth: 200 }} />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="breq-back" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.primary} />
          <Text style={styles.backText}>Back</Text>
        </Pressable>
      </View>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 220 }} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
          <Text style={styles.bizName}>{name}</Text>
          <Text style={styles.bizCat}>{label}</Text>

          {hasCatalog ? (
            <>
              <Text style={styles.sectionLabel}>{t("chooseProducts")}</Text>
              <View style={{ gap: spacing.md }}>
                {products.map((p) => {
                  const q = qty[p.item_id] || 0;
                  return (
                    <View key={p.item_id} style={[styles.prodCard, q > 0 && styles.prodCardActive]} testID={`prod-${p.item_id}`}>
                      {p.foto ? (
                        <Image source={{ uri: p.foto }} style={styles.prodThumb} contentFit="cover" />
                      ) : (
                        <View style={[styles.prodThumb, styles.prodThumbFallback]}><Ionicons name="cube-outline" size={26} color={colors.muted} /></View>
                      )}
                      <View style={{ flex: 1 }}>
                        <Text style={styles.prodName}>{p.descrizione}</Text>
                        <Text style={styles.prodMeta}>{t(`unit_${p.unita}` as any)}</Text>
                        <Text style={styles.prodPrice}>€{Number(p.prezzo).toFixed(2)}</Text>
                      </View>
                      <View style={styles.stepper}>
                        <Pressable testID={`minus-${p.item_id}`} onPress={() => setQ(p.item_id, -1)} hitSlop={8} style={[styles.stepBtn, q === 0 && { opacity: 0.35 }]}>
                          <Ionicons name="remove" size={18} color={colors.purple} />
                        </Pressable>
                        <Text style={styles.qtyText}>{q}</Text>
                        <Pressable testID={`plus-${p.item_id}`} onPress={() => setQ(p.item_id, 1)} hitSlop={8} style={styles.stepBtn}>
                          <Ionicons name="add" size={18} color={colors.purple} />
                        </Pressable>
                      </View>
                    </View>
                  );
                })}
              </View>

              <Text style={styles.label}>{t("orderNote")}</Text>
              <TextInput testID="order-note" style={[styles.input, styles.textarea]} value={note} onChangeText={setNote} placeholder={t("productServicePlaceholder")} placeholderTextColor={colors.muted} multiline />
            </>
          ) : (
            <>
              {!loading ? <Text style={styles.noCatalog}>{t("noListinoBusiness")}</Text> : null}
              <Text style={styles.label}>{t("whatDoYouNeed")}</Text>
              <TextInput testID="breq-note" style={[styles.input, styles.textarea]} value={note} onChangeText={setNote} placeholder={t("productServicePlaceholder")} placeholderTextColor={colors.muted} multiline />
              <Text style={styles.label}>{t("budgetOptional")}</Text>
              <TextInput testID="breq-budget" style={styles.input} value={budget} onChangeText={setBudget} keyboardType="numeric" placeholder="€ 0.00" placeholderTextColor={colors.muted} />
            </>
          )}

          <Text style={styles.label}>{t("deliveryAddress")}</Text>
          <TextInput testID="breq-address" style={styles.input} value={address} onChangeText={setAddress} placeholderTextColor={colors.muted} />
          <Button label={t("useMyLocation")} variant="secondary" icon="navigate" onPress={useMyLocation} testID="breq-location" style={{ marginTop: spacing.md, height: 46 }} />

          <Text style={styles.hint}>{t("businessWillConfirm")}</Text>
        </ScrollView>

        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          {hasCatalog ? (
            <>
              <View style={styles.totalRow}>
                <View>
                  <Text style={styles.totalLabel}>{t("orderTotal")} · {itemCount} {t("cart").toLowerCase()}</Text>
                  <Text style={styles.availLabel}>{t("availableBalance")}: €{available.toFixed(2)}</Text>
                </View>
                <Text style={styles.totalValue}>€{total.toFixed(2)}</Text>
              </View>
              <Button testID="place-order" label={total > 0 ? `${t("placeOrder")} · €${total.toFixed(2)}` : t("emptyCartHint")} loading={submitting} disabled={total <= 0} onPress={placeOrder} />
            </>
          ) : (
            <Button testID="breq-submit" label={t("sendRequest")} loading={submitting} disabled={!note.trim()} onPress={sendFreeRequest} />
          )}
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
  bizName: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface },
  bizCat: { fontSize: fsize.lg, fontFamily: font.regular, color: colors.purple, marginTop: 2 },
  sectionLabel: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface, marginTop: spacing.xl, marginBottom: spacing.md },
  label: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary, marginTop: spacing.lg, marginBottom: spacing.sm },
  input: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  textarea: { minHeight: 90, textAlignVertical: "top" },
  noCatalog: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: spacing.lg, fontStyle: "italic" },
  prodCard: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
  prodCardActive: { borderColor: colors.purpleBorder, backgroundColor: colors.purpleBg },
  prodThumb: { width: 58, height: 58, borderRadius: radius.sm },
  prodThumbFallback: { backgroundColor: colors.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  prodName: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  prodMeta: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 1 },
  prodPrice: { fontSize: fsize.base, fontFamily: font.bold, color: colors.brand, marginTop: 2 },
  stepper: { alignItems: "center", flexDirection: "row", gap: spacing.sm },
  stepBtn: { width: 34, height: 34, borderRadius: 17, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.purpleBorder, alignItems: "center", justifyContent: "center" },
  qtyText: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface, minWidth: 22, textAlign: "center" },
  hint: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: spacing.lg, textAlign: "center" },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.lg, paddingTop: spacing.md, backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderTopColor: colors.divider },
  totalRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.md },
  totalLabel: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary },
  availLabel: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 1 },
  totalValue: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.brand },
  successWrap: { alignItems: "center", justifyContent: "center", padding: spacing.xl },
  successTitle: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface, marginTop: spacing.lg },
  successSub: { fontSize: fsize.lg, fontFamily: font.regular, color: colors.muted, marginTop: spacing.sm, textAlign: "center" },
});
