import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl } from "react-native";
import { Image } from "expo-image";
import { useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";

export default function ChatTab() {
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [convos, setConvos] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try { setConvos(await api.conversations()); } catch {}
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}><Text style={styles.headerTitle}>{t("chat")}</Text></View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 100 }} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />} showsVerticalScrollIndicator={false}>
        {convos.length === 0 ? (
          <View style={styles.empty}><Text style={{ fontSize: 40 }}>💬</Text><Text style={styles.emptyText}>{t("noChats")}</Text></View>
        ) : (
          convos.map((c) => (
            <Pressable key={c.conversation_id} testID={`chat-${c.conversation_id}`} style={styles.row} onPress={() => router.push(`/chat/${c.conversation_id}`)}>
              {c.other_picture ? (
                <Image source={{ uri: c.other_picture }} style={styles.avatar} contentFit="cover" />
              ) : (
                <View style={[styles.avatar, styles.avatarFallback]}><Text style={styles.avatarInitial}>{c.other_name?.[0] || "?"}</Text></View>
              )}
              <View style={{ flex: 1 }}>
                <Text style={styles.name}>{c.other_name}</Text>
                <Text style={styles.last} numberOfLines={1}>{c.last_message || "…"}</Text>
              </View>
            </Pressable>
          ))
        )}
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
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.sm, ...shadow.card },
  avatar: { width: 50, height: 50, borderRadius: 25 },
  avatarFallback: { backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" },
  avatarInitial: { color: "#fff", fontSize: 20, fontFamily: font.medium },
  name: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  last: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 2 },
});
