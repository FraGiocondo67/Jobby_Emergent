import React, { useCallback, useState } from "react";
import { Pressable, View, Text, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useFocusEffect } from "expo-router";
import { api } from "@/src/api";
import { colors, font } from "@/src/theme";

export default function NotifBell({ color = colors.onSurface }: { color?: string }) {
  const router = useRouter();
  const [unread, setUnread] = useState(0);

  const load = useCallback(async () => {
    try { const r = await api.notifUnread(); setUnread(r.unread || 0); } catch {}
  }, []);
  useFocusEffect(useCallback(() => { load(); const iv = setInterval(load, 15000); return () => clearInterval(iv); }, [load]));

  return (
    <Pressable testID="notif-bell" onPress={() => router.push("/notifications")} hitSlop={12} style={styles.wrap}>
      <Ionicons name="notifications-outline" size={24} color={color} />
      {unread > 0 ? (
        <View style={styles.badge}><Text style={styles.badgeText}>{unread > 9 ? "9+" : unread}</Text></View>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  wrap: { width: 32, height: 32, alignItems: "center", justifyContent: "center" },
  badge: { position: "absolute", top: -2, right: -2, minWidth: 18, height: 18, borderRadius: 9, backgroundColor: colors.error, alignItems: "center", justifyContent: "center", paddingHorizontal: 4, borderWidth: 1.5, borderColor: colors.surface },
  badgeText: { color: "#fff", fontSize: 10, fontFamily: font.bold },
});
