import React, { useCallback, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, ImageBackground, RefreshControl, Switch,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Stars, Button } from "@/src/components/UI";
import MapCanvas from "@/src/components/MapCanvas";

const CAT_IMG: Record<string, string> = {
  cleaning: "https://images.pexels.com/photos/3935315/pexels-photo-3935315.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
  ironing: "https://images.pexels.com/photos/28576633/pexels-photo-28576633.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
};

export default function HomeTab() {
  const { user } = useAuth();
  return user?.role === "provider" ? <ProviderHome /> : <CustomerHome />;
}

function Header({ title, right }: { title: string; right?: React.ReactNode }) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
      <View>
        <Text style={styles.brandSmall}>JOBBY</Text>
        <Text style={styles.headerTitle}>{title}</Text>
      </View>
      {right}
    </View>
  );
}

function CustomerHome() {
  const { user } = useAuth();
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [missions, setMissions] = useState<any[]>([]);
  const [bookings, setBookings] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [m, b] = await Promise.all([api.myMissions(), api.bookings()]);
      setMissions(m);
      setBookings(b);
    } catch {}
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const activeMission = missions.find((m) => m.status === "broadcasting");
  const upcoming = bookings.find((b) => b.status === "confirmed");

  return (
    <View style={styles.container}>
      <Header title={`${t("hello")}, ${(user?.name || "").split(" ")[0]}`} />
      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 100 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
        showsVerticalScrollIndicator={false}
      >
        {activeMission ? (
          <Pressable
            testID="active-mission-card"
            style={[styles.activeCard, shadow.card]}
            onPress={() => router.push(`/mission/radar?id=${activeMission.mission_id}`)}
          >
            <View style={styles.statusDot} />
            <View style={{ flex: 1 }}>
              <Text style={styles.activeLabel}>{t("status_broadcasting")}</Text>
              <Text style={styles.activeTitle}>{t(activeMission.category as any)} · {activeMission.date}</Text>
              <Text style={styles.activeSub}>{activeMission.accepted?.length || 0} {t("accepted")}</Text>
            </View>
            <Ionicons name="chevron-forward" size={22} color={colors.muted} />
          </Pressable>
        ) : upcoming ? (
          <Pressable
            testID="upcoming-booking-card"
            style={[styles.activeCard, shadow.card]}
            onPress={() => router.push(`/booking/${upcoming.booking_id}`)}
          >
            <Ionicons name="checkmark-circle" size={26} color={colors.success} style={{ marginRight: spacing.md }} />
            <View style={{ flex: 1 }}>
              <Text style={styles.activeLabel}>{t("upcoming")}</Text>
              <Text style={styles.activeTitle}>{upcoming.provider_name}</Text>
              <Text style={styles.activeSub}>{upcoming.date} · {upcoming.time}</Text>
            </View>
            <Ionicons name="chevron-forward" size={22} color={colors.muted} />
          </Pressable>
        ) : null}

        <Text style={styles.sectionTitle}>{t("whatDoYouNeed")}</Text>
        <View style={styles.grid}>
          {(["cleaning", "ironing"] as const).map((cat) => (
            <Pressable
              key={cat}
              testID={`category-${cat}`}
              style={styles.catCard}
              onPress={() => {
                Haptics.selectionAsync().catch(() => {});
                router.push(`/mission/create?category=${cat}`);
              }}
            >
              <ImageBackground source={{ uri: CAT_IMG[cat] }} style={styles.catBg} imageStyle={{ borderRadius: radius.lg }}>
                <LinearGradient colors={["transparent", "rgba(28,27,26,0.8)"]} style={styles.catGradient}>
                  <Text style={styles.catText}>{t(cat)}</Text>
                </LinearGradient>
              </ImageBackground>
            </Pressable>
          ))}
        </View>
      </ScrollView>
    </View>
  );
}

function ProviderHome() {
  const { user, setUser } = useAuth();
  const { t } = useLang();
  const insets = useSafeAreaInsets();
  const [incoming, setIncoming] = useState<any[]>([]);
  const [online, setOnline] = useState(!!user?.online);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const m = await api.incomingMissions();
      setIncoming(m);
    } catch {}
  }, []);

  useFocusEffect(useCallback(() => {
    load();
    const iv = setInterval(load, 4000);
    return () => clearInterval(iv);
  }, [load]));

  const toggleOnline = async (v: boolean) => {
    setOnline(v);
    Haptics.selectionAsync().catch(() => {});
    const updated = await api.updateProfile({ online: v });
    setUser(updated);
  };

  const act = async (id: string, accept: boolean) => {
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    if (accept) await api.acceptMission(id);
    else await api.declineMission(id);
    load();
  };

  const pins = incoming.map((m) => ({ lat: m.lat, lng: m.lng, highlight: true }));

  return (
    <View style={styles.container}>
      <Header
        title={t("missions")}
        right={
          <View style={styles.onlineToggle}>
            <Text style={[styles.onlineText, { color: online ? colors.success : colors.muted }]}>
              {online ? t("online") : t("offline")}
            </Text>
            <Switch
              testID="online-toggle"
              value={online}
              onValueChange={toggleOnline}
              trackColor={{ true: colors.brand, false: colors.borderStrong }}
              thumbColor="#fff"
            />
          </View>
        }
      />
      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 100 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
        showsVerticalScrollIndicator={false}
      >
        <MapCanvas center={{ lat: user?.lat || 45.6669, lng: user?.lng || 12.2433 }} pins={pins} height={200} />
        <Text style={styles.sectionTitle}>{t("incomingMissions")}</Text>
        {incoming.length === 0 ? (
          <View style={styles.empty}>
            <Ionicons name="cafe-outline" size={40} color={colors.muted} />
            <Text style={styles.emptyText}>{t("noMissions")}</Text>
          </View>
        ) : (
          incoming.map((m) => (
            <View key={m.mission_id} style={[styles.missionCard, shadow.card]} testID={`incoming-${m.mission_id}`}>
              <View style={styles.missionRow}>
                <View style={styles.missionIcon}>
                  <Ionicons name={m.category === "ironing" ? "shirt" : "sparkles"} size={20} color={colors.brand} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.missionTitle}>{t(m.category)} · {m.duration_hours}{t("hours")}</Text>
                  <Text style={styles.missionSub}>{m.address}</Text>
                  <Text style={styles.missionSub}>{m.date} · {m.time}</Text>
                </View>
                <Text style={styles.missionPrice}>
                  €{((user?.hourly_rate || 13) * m.duration_hours).toFixed(0)}
                </Text>
              </View>
              {m.already_accepted ? (
                <View style={styles.acceptedTag}>
                  <Ionicons name="hourglass-outline" size={14} color={colors.warning} />
                  <Text style={styles.acceptedTagText}>{t("accepted2")}</Text>
                </View>
              ) : (
                <View style={styles.actionRow}>
                  <Button testID={`decline-${m.mission_id}`} label={t("decline")} variant="secondary" onPress={() => act(m.mission_id, false)} style={{ flex: 1, height: 46 }} />
                  <Button testID={`accept-${m.mission_id}`} label={t("accept")} onPress={() => act(m.mission_id, true)} style={{ flex: 1, height: 46 }} />
                </View>
              )}
            </View>
          ))
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: {
    paddingHorizontal: spacing.lg, paddingBottom: spacing.md,
    flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end",
    backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.divider,
  },
  brandSmall: { fontSize: fsize.sm, fontFamily: font.bold, color: colors.brand, letterSpacing: 1 },
  headerTitle: { fontSize: fsize["2xl"], fontFamily: font.medium, color: colors.onSurface },
  activeCard: {
    flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.lg,
  },
  statusDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.brand, marginRight: spacing.md },
  activeLabel: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.brand },
  activeTitle: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface, marginTop: 2 },
  activeSub: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 2 },
  sectionTitle: { fontSize: fsize.xl, fontFamily: font.medium, color: colors.onSurface, marginTop: spacing.md, marginBottom: spacing.md },
  grid: { flexDirection: "row", gap: spacing.md },
  catCard: { flex: 1, height: 180, borderRadius: radius.lg, overflow: "hidden" },
  catBg: { flex: 1, justifyContent: "flex-end" },
  catGradient: { padding: spacing.md, height: "60%", justifyContent: "flex-end", borderBottomLeftRadius: radius.lg, borderBottomRightRadius: radius.lg },
  catText: { color: "#fff", fontSize: fsize.xl, fontFamily: font.medium },
  onlineToggle: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  onlineText: { fontSize: fsize.base, fontFamily: font.medium },
  empty: { alignItems: "center", padding: spacing["2xl"], gap: spacing.md },
  emptyText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, textAlign: "center" },
  missionCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.md },
  missionRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  missionIcon: { width: 42, height: 42, borderRadius: 21, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  missionTitle: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  missionSub: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 1 },
  missionPrice: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.brand },
  actionRow: { flexDirection: "row", gap: spacing.md, marginTop: spacing.md },
  acceptedTag: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: spacing.md, backgroundColor: "#FBF0E2", padding: spacing.sm, borderRadius: radius.sm },
  acceptedTagText: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.warning },
});
