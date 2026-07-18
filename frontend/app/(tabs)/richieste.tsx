import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";

export default function RichiesteTab() {
  const { user } = useAuth();
  return user?.role === "provider" ? <ProviderJobs /> : <CustomerRequests />;
}

function StatusPill({ status }: { status: string }) {
  const { t } = useLang();
  const map: Record<string, string> = { pending: colors.warning, matched: "#E07B39", confirmed: colors.blue, in_progress: colors.brand, completed: colors.success, booked: colors.brand, disputed: colors.error };
  const c = map[status] || colors.muted;
  const label = (t as any)(`status_${status}`) || status;
  return <View style={[styles.pill, { backgroundColor: c + "22" }]}><Text style={[styles.pillText, { color: c }]}>{label}</Text></View>;
}

function CustomerRequests() {
  const { lang, t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [missions, setMissions] = useState<any[]>([]);
  const [payments, setPayments] = useState<any[]>([]);
  const [bookings, setBookings] = useState<any[]>([]);
  const [bizReqs, setBizReqs] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [r, b, br] = await Promise.all([api.requests(), api.bookings(), api.businessRequests()]);
      setMissions(r.missions.filter((m: any) => m.status !== "booked"));
      setPayments(r.payments);
      setBookings(b);
      setBizReqs(br);
    } catch {}
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const empty = missions.length === 0 && payments.length === 0 && bookings.length === 0 && bizReqs.length === 0;

  const openChat = async (otherId: string) => {
    try {
      const convos = await api.conversations();
      const c = convos.find((x: any) => x.other_id === otherId);
      if (c) router.push(`/chat/${c.conversation_id}`);
      else router.push("/(tabs)/chat");
    } catch {
      router.push("/(tabs)/chat");
    }
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}><Text style={styles.headerTitle}>{t("richieste")}</Text></View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 100 }} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />} showsVerticalScrollIndicator={false}>
        {empty ? (
          <View style={styles.empty}><Text style={{ fontSize: 40 }}>📋</Text><Text style={styles.emptyText}>{t("noRequests")}</Text></View>
        ) : null}

        {missions.map((m) => (
          <Pressable key={m.mission_id} testID={`req-mission-${m.mission_id}`} style={[styles.card, shadow.card]} onPress={() => router.push(`/mission/radar?id=${m.mission_id}`)}>
            <Text style={{ fontSize: 26 }}>🔎</Text>
            <View style={{ flex: 1 }}>
              <Text style={styles.cardTitle}>{m.category}</Text>
              <Text style={styles.cardSub}>{m.date} · {m.time} · {m.accepted?.length || 0} {t("accepted")}</Text>
              <View style={{ marginTop: 6 }}><StatusPill status={m.status} /></View>
            </View>
          </Pressable>
        ))}

        {bizReqs.map((r) => (
          <View key={r.request_id} testID={`req-biz-${r.request_id}`} style={[styles.card, { flexDirection: "column", alignItems: "stretch" }, shadow.card]}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
              <Text style={{ fontSize: 26 }}>🏪</Text>
              <View style={{ flex: 1 }}>
                <Text style={styles.cardTitle}>{r.business_name}</Text>
                <Text style={styles.cardSub}>{r.category_label?.[lang] || r.category} · {r.note}</Text>
                <View style={{ marginTop: 6 }}><StatusPill status={r.status} /></View>
              </View>
            </View>
            {r.status === "confirmed" && r.response ? (
              <>
                <Text style={styles.bizInfo}>
                  {r.response.mode === "delivery" ? t("mode_delivery") : t("mode_pickup")} · {r.response.eta || "—"} · €{(r.response.price || 0).toFixed(2)}
                  {r.response.delivery_cost ? ` + €${r.response.delivery_cost.toFixed(2)}` : ""}
                </Text>
                <Pressable testID={`biz-chat-${r.request_id}`} style={styles.chatBtn} onPress={() => openChat(r.business_id)}>
                  <Text style={styles.chatBtnText}>💬 {t("chat")}</Text>
                </Pressable>
              </>
            ) : null}
          </View>
        ))}

        {bookings.map((b) => (
          <Pressable key={b.booking_id} testID={`req-booking-${b.booking_id}`} style={[styles.card, shadow.card]} onPress={() => router.push(`/booking/${b.booking_id}`)}>
            <Text style={{ fontSize: 26 }}>🧾</Text>
            <View style={{ flex: 1 }}>
              <Text style={styles.cardTitle}>{b.provider_name}</Text>
              <Text style={styles.cardSub}>{b.category} · {b.date} · {b.time}</Text>
              <View style={{ marginTop: 6 }}><StatusPill status={b.status} /></View>
            </View>
            <Text style={styles.cardPrice}>€{b.total.toFixed(2)}</Text>
          </Pressable>
        ))}

        {payments.map((p) => (
          <View key={p.request_id} style={[styles.card, shadow.card]} testID={`req-payment-${p.request_id}`}>
            <Text style={{ fontSize: 26 }}>💳</Text>
            <View style={{ flex: 1 }}>
              <Text style={styles.cardTitle}>{p.label}</Text>
              <Text style={styles.cardSub}>{new Date(p.created_at).toLocaleDateString()}</Text>
              <View style={{ marginTop: 6 }}><StatusPill status="completed" /></View>
            </View>
            <Text style={styles.cardPrice}>€{p.amount.toFixed(2)}</Text>
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

function ProviderJobs() {
  const { t } = useLang();
  const insets = useSafeAreaInsets();
  const [data, setData] = useState<any>(null);
  const [bookings, setBookings] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try { const [e, b] = await Promise.all([api.earnings(), api.bookings()]); setData(e); setBookings(b); } catch {}
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}><Text style={styles.headerTitle}>{t("earnings")}</Text></View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 100 }} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />} showsVerticalScrollIndicator={false}>
        <View style={styles.earnHero}>
          <Text style={styles.earnLabel}>{t("totalEarned")}</Text>
          <Text style={styles.earnValue}>€{(data?.total_earned || 0).toFixed(2)}</Text>
          <View style={styles.earnStats}>
            <View style={styles.stat}><Text style={styles.statVal}>{data?.jobs_count || 0}</Text><Text style={styles.statLbl}>{t("jobs")}</Text></View>
            <View style={styles.stat}><Text style={styles.statVal}>{data?.completed_count || 0}</Text><Text style={styles.statLbl}>{t("completed")}</Text></View>
            <View style={styles.stat}><Text style={styles.statVal}>€{(data?.pending || 0).toFixed(0)}</Text><Text style={styles.statLbl}>{t("pending")}</Text></View>
          </View>
        </View>
        {bookings.map((b) => (
          <View key={b.booking_id} style={[styles.card, shadow.card]}>
            <Text style={{ fontSize: 26 }}>🧾</Text>
            <View style={{ flex: 1 }}>
              <Text style={styles.cardTitle}>{b.customer_name}</Text>
              <Text style={styles.cardSub}>{b.category} · {b.date}</Text>
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
  headerTitle: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface },
  empty: { alignItems: "center", padding: spacing["3xl"], gap: spacing.md },
  emptyText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted },
  card: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.lg, marginBottom: spacing.md, gap: spacing.md },
  cardTitle: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface, textTransform: "capitalize" },
  cardSub: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 1 },
  cardPrice: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  bizInfo: { fontSize: fsize.base, fontFamily: font.medium, color: colors.success, marginTop: spacing.md },
  chatBtn: { marginTop: spacing.md, alignSelf: "flex-start", backgroundColor: colors.purpleBg, paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, borderRadius: radius.pill },
  chatBtnText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.purple },
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
