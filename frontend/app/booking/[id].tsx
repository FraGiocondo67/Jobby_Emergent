import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput } from "react-native";
import { Image } from "expo-image";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Button } from "@/src/components/UI";

export default function BookingDetail() {
  const { id, new: isNew } = useLocalSearchParams<{ id: string; new?: string }>();
  const { user } = useAuth();
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [b, setB] = useState<any>(null);
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setB(await api.getBooking(id as string)); } catch {}
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const complete = async () => {
    setBusy(true);
    await api.completeBooking(id as string);
    await load();
    setBusy(false);
  };

  const submitReview = async () => {
    setBusy(true);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    await api.reviewBooking(id as string, rating, comment);
    await load();
    setBusy(false);
  };

  if (!b) return <View style={styles.container} />;

  const isProvider = user?.role === "provider";
  const partnerName = isProvider ? b.customer_name : b.provider_name;

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="booking-back" onPress={() => router.replace("/(tabs)")} hitSlop={12}>
          <Ionicons name={isNew ? "close" : "arrow-back"} size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>{t("bookingConfirmed")}</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }} showsVerticalScrollIndicator={false}>
        {isNew ? (
          <View style={styles.successBanner}>
            <Ionicons name="checkmark-circle" size={30} color={colors.success} />
            <Text style={styles.successText}>{t("bookingConfirmed")}</Text>
          </View>
        ) : null}

        <View style={[styles.card, shadow.card]}>
          <Text style={styles.sectionLabel}>{isProvider ? t("hello") : t("yourProvider")}</Text>
          <View style={styles.providerRow}>
            {b.provider_picture && !isProvider ? (
              <Image source={{ uri: b.provider_picture }} style={styles.avatar} contentFit="cover" />
            ) : (
              <View style={[styles.avatar, styles.avatarFallback]}><Text style={styles.avatarInitial}>{partnerName[0]}</Text></View>
            )}
            <View>
              <Text style={styles.providerName}>{partnerName}</Text>
              <Text style={styles.providerSub}>{t(b.category)} · {b.duration_hours} {t("hours")}</Text>
            </View>
          </View>
          <View style={styles.detailRow}><Ionicons name="calendar-outline" size={18} color={colors.muted} /><Text style={styles.detailText}>{b.date} · {b.time}</Text></View>
          <View style={styles.detailRow}><Ionicons name="location-outline" size={18} color={colors.muted} /><Text style={styles.detailText}>{b.address}</Text></View>
        </View>

        <View style={[styles.card, shadow.card]}>
          <Text style={styles.sectionLabel}>{t("priceBreakdown")}</Text>
          <View style={styles.priceLine}><Text style={styles.priceLabel}>{t("labor")}</Text><Text style={styles.priceVal}>€{b.labor_cost.toFixed(2)}</Text></View>
          <View style={styles.priceLine}><Text style={styles.priceLabel}>{t("jobbyFee")}</Text><Text style={styles.priceVal}>€{b.jobby_fee.toFixed(2)}</Text></View>
          <View style={[styles.priceLine, styles.totalLine]}>
            <Text style={styles.totalLabel}>{isProvider ? t("yourEarning") : t("total")}</Text>
            <Text style={styles.totalVal}>€{(isProvider ? b.labor_cost : b.total).toFixed(2)}</Text>
          </View>
        </View>

        {b.status === "confirmed" ? (
          <Button testID="complete-button" label={t("complete")} loading={busy} onPress={complete} />
        ) : null}

        {!isProvider && b.status === "completed" && !b.reviewed ? (
          <View style={[styles.card, shadow.card]}>
            <Text style={styles.sectionLabel}>{t("leaveReview")}</Text>
            <View style={styles.starRow}>
              {[1, 2, 3, 4, 5].map((i) => (
                <Pressable key={i} testID={`star-${i}`} onPress={() => setRating(i)} hitSlop={6}>
                  <Ionicons name={i <= rating ? "star" : "star-outline"} size={34} color={colors.warning} />
                </Pressable>
              ))}
            </View>
            <TextInput
              testID="review-input"
              style={styles.input}
              value={comment}
              onChangeText={setComment}
              placeholder="..."
              placeholderTextColor={colors.muted}
              multiline
            />
            <Button testID="submit-review-button" label={t("submitReview")} loading={busy} onPress={submitReview} />
          </View>
        ) : null}

        {b.reviewed ? (
          <View style={styles.reviewedBanner}>
            <Ionicons name="checkmark-done" size={18} color={colors.success} />
            <Text style={styles.reviewedText}>{t("done")}</Text>
          </View>
        ) : null}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.divider },
  headerTitle: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  successBanner: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: "#E8F0EA", borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.lg },
  successText: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.success },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.lg, gap: spacing.sm },
  sectionLabel: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.5 },
  providerRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, marginVertical: spacing.sm },
  avatar: { width: 52, height: 52, borderRadius: 26 },
  avatarFallback: { backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" },
  avatarInitial: { color: "#fff", fontSize: 20, fontFamily: font.medium },
  providerName: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  providerSub: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 1 },
  detailRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  detailText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurfaceTertiary },
  priceLine: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 3 },
  priceLabel: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurfaceTertiary },
  priceVal: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  totalLine: { borderTopWidth: 1, borderTopColor: colors.divider, marginTop: 4, paddingTop: 8 },
  totalLabel: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  totalVal: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.brand },
  starRow: { flexDirection: "row", justifyContent: "center", gap: spacing.sm, marginVertical: spacing.md },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, minHeight: 80, fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface, textAlignVertical: "top", marginBottom: spacing.md },
  reviewedBanner: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, padding: spacing.md },
  reviewedText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.success },
});
