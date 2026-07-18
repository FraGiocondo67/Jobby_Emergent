import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";

const GROUPS: Record<string, { key: string; emoji: string; titleKey: any; subKey: any; accent: "purple" | "green" | "orange"; mode: string }> = {
  prossimita: { key: "proximity", emoji: "🏪", titleKey: "proximity", subKey: "searchNearby", accent: "purple", mode: "proximity" },
  pagamenti: { key: "payment", emoji: "💳", titleKey: "payments", subKey: "selectService", accent: "green", mode: "payment" },
  all: { key: "standard", emoji: "✨", titleKey: "selectService", subKey: "whatDoYouNeed", accent: "orange", mode: "service" },
};

export default function ListScreen() {
  const { group } = useLocalSearchParams<{ group: string }>();
  const { lang, t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const cfg = GROUPS[group as string] || GROUPS.all;
  const [items, setItems] = useState<any[]>([]);

  useEffect(() => {
    (async () => {
      try {
        const c = await api.categories();
        setItems(c[cfg.key] || []);
      } catch {}
    })();
  }, [cfg.key]);

  const arrowColor = cfg.accent === "purple" ? colors.purple : cfg.accent === "green" ? colors.green : colors.primary;

  const onPress = (item: any) => {
    if (cfg.mode === "proximity") {
      router.push(`/businesses/${item.cat_id}?label=${encodeURIComponent(item.label[lang])}&emoji=${encodeURIComponent(item.emoji || "🏪")}`);
    } else {
      router.push(`/request/${item.cat_id}?type=${cfg.mode}`);
    }
  };

  const itemSub = (item: any) => {
    if (cfg.mode === "payment") return `${item.questions?.length || 2} ${t("quickQuestions")}`;
    if (cfg.mode === "proximity") return `${t("searchNearby")} →`;
    return item.subtitle?.[lang] || "";
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="list-back" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.primary} />
          <Text style={styles.backText}>Back</Text>
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }} showsVerticalScrollIndicator={false}>
        <Text style={styles.bigEmoji}>{cfg.emoji}</Text>
        <Text style={styles.title}>{t(cfg.titleKey)}</Text>
        <Text style={styles.subtitle}>{t(cfg.subKey)}</Text>

        <View style={{ marginTop: spacing.xl, gap: spacing.md }}>
          {items.map((item) => (
            <Pressable
              key={item.cat_id}
              testID={`list-item-${item.cat_id}`}
              style={[styles.row, cfg.accent === "purple" && { borderColor: colors.purpleBorder }, cfg.accent === "green" && { borderColor: colors.greenBorder }, shadow.card]}
              onPress={() => onPress(item)}
            >
              <View style={[styles.iconBox, { backgroundColor: cfg.accent === "purple" ? colors.purpleBg : cfg.accent === "green" ? colors.greenBg : colors.surfaceTertiary }]}>
                <Text style={{ fontSize: 26 }}>{item.emoji || "🧩"}</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle}>{item.label[lang]}</Text>
                <Text style={styles.rowSub}>{itemSub(item)}</Text>
              </View>
              <Ionicons name="arrow-forward" size={22} color={arrowColor} />
            </Pressable>
          ))}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  backBtn: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start" },
  backText: { color: colors.primary, fontSize: fsize.xl, fontFamily: font.medium },
  bigEmoji: { fontSize: 46, textAlign: "center", marginTop: spacing.md },
  title: { fontSize: fsize["3xl"], fontFamily: font.bold, color: colors.onSurface, textAlign: "center", marginTop: spacing.md },
  subtitle: { fontSize: fsize.xl, fontFamily: font.regular, color: colors.muted, textAlign: "center", marginTop: spacing.sm },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md },
  iconBox: { width: 52, height: 52, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  rowTitle: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.onSurface },
  rowSub: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 2 },
});
