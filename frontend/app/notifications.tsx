import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";

const ICON: Record<string, string> = {
  dispute_opened: "alert-circle",
  dispute_message: "chatbubble-ellipses",
  dispute_update: "information-circle",
  dispute_resolved: "checkmark-circle",
  chat_message: "chatbubble-ellipses",
  driver_invito: "car", driver_proposta: "pricetag", driver_confermata: "checkmark-circle",
  driver_completata: "flag", driver_in_arrivo: "navigate", driver_annullata: "close-circle",
  babysitting_invito: "happy", babysitting_proposta: "pricetag", babysitting_confermata: "checkmark-circle",
  artigiani_invito: "construct", artigiani_proposta: "pricetag", artigiani_preventivo: "document-text",
  artigiani_confermata: "checkmark-circle", artigiani_completata: "flag",
};

const REF_ROUTE: Record<string, string> = {
  richiesta: "/pulizie", driver: "/driver", babysitting: "/babysitting", artigiani: "/artigiani",
  dispute: "/dispute", booking: "/booking",
};

function timeAgo(iso: string) {
  const diff = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return "adesso";
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}g`;
}

export default function Notifications() {
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try { const r = await api.notifications(); setItems(r.items || []); } catch {}
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const openItem = async (n: any) => {
    if (!n.read) { try { await api.markNotifRead(n.notif_id); } catch {} }
    if (n.ref_type === "chat" && n.ref_id) router.push(`/chat/${n.ref_id}`);
    else if (n.ref_type === "profile") router.push("/(tabs)/profile");
    else if (REF_ROUTE[n.ref_type] && n.ref_id) router.push(`${REF_ROUTE[n.ref_type]}/${n.ref_id}` as any);
    load();
  };

  const markAll = async () => { try { await api.markAllNotifRead(); } catch {} load(); };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="notif-back" onPress={() => router.back()} hitSlop={12}>
          <Ionicons name="arrow-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>{t("notifications")}</Text>
        <Pressable testID="notif-mark-all" onPress={markAll} hitSlop={10}>
          <Ionicons name="checkmark-done" size={22} color={colors.brand} />
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
        showsVerticalScrollIndicator={false}
      >
        {items.length === 0 ? (
          <View style={styles.empty}>
            <Ionicons name="notifications-off-outline" size={48} color={colors.muted} />
            <Text style={styles.emptyText}>{t("noNotifications")}</Text>
          </View>
        ) : (
          items.map((n) => (
            <Pressable key={n.notif_id} testID={`notif-${n.notif_id}`} style={[styles.row, shadow.card, !n.read && styles.rowUnread]} onPress={() => openItem(n)}>
              <View style={[styles.icon, { backgroundColor: n.read ? colors.surfaceTertiary : "#FEF3E0" }]}>
                <Ionicons name={(ICON[n.type] || "notifications") as any} size={22} color={n.read ? colors.muted : colors.warning} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.title}>{n.title}</Text>
                <Text style={styles.body} numberOfLines={2}>{n.body}</Text>
                <Text style={styles.time}>{timeAgo(n.created_at)}</Text>
              </View>
              {!n.read ? <View style={styles.dot} /> : null}
            </Pressable>
          ))
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.divider },
  headerTitle: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  empty: { alignItems: "center", justifyContent: "center", paddingTop: 100, gap: spacing.md },
  emptyText: { fontSize: fsize.lg, fontFamily: font.regular, color: colors.muted },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.md, marginBottom: spacing.sm },
  rowUnread: { borderLeftWidth: 3, borderLeftColor: colors.warning },
  icon: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center" },
  title: { fontSize: fsize.base, fontFamily: font.bold, color: colors.onSurface },
  body: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurfaceTertiary, marginTop: 1 },
  time: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 2 },
  dot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.error },
});
