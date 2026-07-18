import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Button } from "@/src/components/UI";

export default function Activities() {
  const { user, setUser } = useAuth();
  const { lang, t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [all, setAll] = useState<any[]>([]);
  const [selected, setSelected] = useState<string[]>(user?.services || []);
  const [loading, setLoading] = useState(false);

  const business = user?.role === "business";

  useEffect(() => {
    (async () => {
      try {
        const c = await api.categories();
        setAll(business ? c.proximity : c.standard);
      } catch {}
    })();
  }, [business]);

  const toggle = (id: string) => {
    Haptics.selectionAsync().catch(() => {});
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const save = async () => {
    setLoading(true);
    const updated = await api.updateProfile({ services: selected });
    setUser(updated);
    setLoading(false);
    router.back();
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="activities-back" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.primary} />
          <Text style={styles.backText}>Back</Text>
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 120 }} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>{t("myActivities")}</Text>
        <Text style={styles.desc}>{t("selectActivities")}</Text>
        <View style={styles.grid}>
          {all.map((c) => {
            const on = selected.includes(c.cat_id);
            return (
              <Pressable key={c.cat_id} testID={`activity-${c.cat_id}`} style={[styles.chip, on && styles.chipOn]} onPress={() => toggle(c.cat_id)}>
                <Text style={{ fontSize: 22 }}>{c.emoji}</Text>
                <Text style={[styles.chipText, on && { color: "#fff" }]}>{c.label[lang]}</Text>
                {on ? <Ionicons name="checkmark-circle" size={16} color="#fff" /> : null}
              </Pressable>
            );
          })}
        </View>
      </ScrollView>
      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
        <Button testID="save-activities-button" label={t("save")} loading={loading} onPress={save} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  backBtn: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start" },
  backText: { color: colors.primary, fontSize: fsize.xl, fontFamily: font.medium },
  title: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface },
  desc: { fontSize: fsize.lg, fontFamily: font.regular, color: colors.muted, marginTop: spacing.sm, marginBottom: spacing.lg },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, ...shadow.card },
  chipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.lg, paddingTop: spacing.md, backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderTopColor: colors.divider },
});
