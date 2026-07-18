import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";

export default function BookingsTab() {
  const { user } = useAuth();
  return user?.role === "provider" ? <Earnings /> : <CustomerBookings />;
}

function StatusPill({ status }: { status: string }) {
  const { t } = useLang();
  const map: Record<string, string> = {
    confirmed: colors.brand, completed: colors.success, broadcasting: colors.warning,
  };
  const c = map[status] || colors.muted;
  return (
    <View style={[styles.pill, { backgroundColor: c + "22" }]}>
      <Text style={[styles.pillText, { color: c }]}>{t(`status_${status}` as any)}</Text>
    </View>
  );
}

function CustomerBookings() {
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [bookings, setBookings] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try { setBookings(await api.bookings()); } catch {}
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Text style={styles.headerTitle}>{t("bookings")}</Text>
      </View>
      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 100 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
      >
        {bookings.length === 0 ? (
          <View style={styles.empty}>
            <Ionicons name="calendar-outline" size={40} color={colors.muted} />
            <Text style={styles.emptyText}>{t("noBookings")}</Text>
          </View>
        ) : (
          bookings.map((b) => (
            <Pressable
              key={b.booking_id}
              testID={`booking-${b.booking_id}`}
              style={[styles.card, shadow.card]}
              onPress={() => router.push(`/booking/${b.booking_id}`)}
            >
              <View style={styles.cardIcon}>
                <Ionicons name={b.category === "ironing" ? "shirt" : "sparkles"} size={20} color={colors.brand} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.cardTitle}>{b.provider_name}</Text>
                <Text style={styles.cardSub}>{t(b.category)} · {b.date} · {b.time}</Text>
                <View style={{ marginTop: 6 }}><StatusPill status={b.status} /></View>
              </View>
              <Text style={styles.cardPrice}>€{b.total.toFixed(2)}</Text>
            </Pressable>
          ))
        )}
      </ScrollView>
    </View>
  );
}

function Earnings() {
  const { t } = useLang();
  const insets = useSafeAreaInsets();
  const [data, setData] = useState<any>(null);
  const [bookings, setBookings] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [e, b] = await Promise.all([api.earnings(), api.bookings()]);
      setData(e); setBookings(b);
    } catch {}
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Text style={styles.headerTitle}>{t("earnings")}</Text>
      </View>
      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 100 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
      >
        <View style={[styles.earnHero, shadow.card]}>
          <Text style={styles.earnLabel}>{t("totalEarned")}</Text>
          <Text style={styles.earnValue}>€{(data?.total_earned || 0).toFixed(2)}</Text>
          <View style={styles.earnStats}>
            <View style={styles.stat}><Text style={styles.statVal}>{data?.jobs_count || 0}</Text><Text style={styles.statLbl}>{t("jobs")}</Text></View>
            <View style={styles.stat}><Text style={styles.statVal}>{data?.completed_count || 0}</Text><Text style={styles.statLbl}>{t("completed")}</Text></View>
            <View style={styles.stat}><Text style={styles.statVal}>€{(data?.pending || 0).toFixed(0)}</Text><Text style={styles.statLbl}>{t("pending")}</Text></View>
          </View>
        </View>
        {bookings.map((b) => (
          <View key={b.booking_id} style={[styles.card, shadow.card]} testID={`job-${b.booking_id}`}>
            <View style={styles.cardIcon}>
              <Ionicons name={b.category === "ironing" ? "shirt" : "sparkles"} size={20} color={colors.brand} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.cardTitle}>{b.customer_name}</Text>
              <Text style={styles.cardSub}>{t(b.category)} · {b.date}</Text>
              <View style={{ marginTop: 6 }}><StatusPill status={b.status} /></View>
            </View>
            <Text style={styles.cardPrice}>€{b.labor_cost.toFixed(2)}</Text>
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.divider },
  headerTitle: { fontSize: fsize["2xl"], fontFamily: font.medium, color: colors.onSurface },
  empty: { alignItems: "center", padding: spacing["3xl"], gap: spacing.md },
  emptyText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted },
  card: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.md, gap: spacing.md },
  cardIcon: { width: 42, height: 42, borderRadius: 21, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  cardTitle: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  cardSub: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 1 },
  cardPrice: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  pill: { alignSelf: "flex-start", paddingHorizontal: spacing.sm, paddingVertical: 3, borderRadius: radius.pill },
  pillText: { fontSize: fsize.sm, fontFamily: font.medium },
  earnHero: { backgroundColor: colors.brand, borderRadius: radius.lg, padding: spacing.xl, marginBottom: spacing.lg },
  earnLabel: { color: "rgba(255,255,255,0.85)", fontSize: fsize.base, fontFamily: font.regular },
  earnValue: { color: "#fff", fontSize: 40, fontFamily: font.bold, marginTop: 4 },
  earnStats: { flexDirection: "row", marginTop: spacing.lg, gap: spacing.lg },
  stat: { flex: 1 },
  statVal: { color: "#fff", fontSize: fsize.xl, fontFamily: font.medium },
  statLbl: { color: "rgba(255,255,255,0.8)", fontSize: fsize.sm, fontFamily: font.regular },
});
