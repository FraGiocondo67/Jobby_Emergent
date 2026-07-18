import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, TextInput, Switch } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { storage } from "@/src/utils/storage";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Button } from "@/src/components/UI";

const KEY = "jobby_admin_token";

export default function Admin() {
  const { lang, t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [token, setToken] = useState("");
  const [unlocked, setUnlocked] = useState(false);
  const [cats, setCats] = useState<any[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const loadWith = useCallback(async (tok: string) => {
    const list = await api.adminCategories(tok);
    setCats(list);
    setUnlocked(true);
    await storage.setItem(KEY, tok);
  }, []);

  const boot = useCallback(async () => {
    const saved = await storage.getItem(KEY, "");
    if (saved) {
      try { setToken(saved); await loadWith(saved); } catch {}
    }
  }, [loadWith]);

  React.useEffect(() => { boot(); }, [boot]);

  const unlock = async () => {
    setError(""); setBusy(true);
    try { await loadWith(token.trim()); }
    catch { setError(t("invalidToken")); }
    finally { setBusy(false); }
  };

  const toggle = async (catId: string) => {
    Haptics.selectionAsync().catch(() => {});
    const r = await api.adminToggleCategory(catId, token.trim());
    setCats((prev) => prev.map((c) => (c.cat_id === catId ? { ...c, active: r.active } : c)));
  };

  const recalc = async () => {
    setBusy(true);
    await api.adminRecalcTrust(token.trim());
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    setBusy(false);
  };

  const groups = [
    { key: "standard", title: t("standardServices") },
    { key: "proximity", title: t("proximityBiz") },
    { key: "payment", title: t("paymentServices") },
  ];

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="admin-back" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.primary} />
          <Text style={styles.backText}>Back</Text>
        </Pressable>
      </View>

      {!unlocked ? (
        <ScrollView contentContainerStyle={{ padding: spacing.lg }}>
          <Text style={styles.bigEmoji}>🔐</Text>
          <Text style={styles.title}>{t("adminPanel")}</Text>
          <Text style={styles.desc}>{t("adminTokenPrompt")}</Text>
          <TextInput
            testID="admin-token-input"
            style={styles.input}
            placeholder="X-Admin-Token"
            placeholderTextColor={colors.muted}
            value={token}
            onChangeText={setToken}
            autoCapitalize="none"
            secureTextEntry
          />
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <Button testID="admin-unlock-button" label={t("unlock")} loading={busy} onPress={unlock} style={{ marginTop: spacing.lg }} />
        </ScrollView>
      ) : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }} showsVerticalScrollIndicator={false}>
          <Text style={styles.title}>{t("adminPanel")}</Text>
          <Text style={styles.desc}>{t("manageCatalog")}</Text>

          {groups.map((g) => (
            <View key={g.key}>
              <Text style={styles.section}>{g.title}</Text>
              {cats.filter((c) => c.kind === g.key).map((c) => (
                <View key={c.cat_id} style={[styles.row, shadow.card]} testID={`admin-cat-${c.cat_id}`}>
                  <Text style={{ fontSize: 22 }}>{c.emoji}</Text>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowTitle}>{c.label[lang]}</Text>
                    <Text style={[styles.rowSub, { color: c.active ? colors.success : colors.muted }]}>
                      {c.active ? t("activeLabel") : "—"}
                    </Text>
                  </View>
                  <Switch
                    testID={`admin-toggle-${c.cat_id}`}
                    value={c.active}
                    onValueChange={() => toggle(c.cat_id)}
                    trackColor={{ true: colors.brand, false: colors.borderStrong }}
                    thumbColor="#fff"
                  />
                </View>
              ))}
            </View>
          ))}

          <Button testID="admin-recalc-button" label={t("recalcTrust")} variant="secondary" icon="refresh" loading={busy} onPress={recalc} style={{ marginTop: spacing.xl }} />
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  backBtn: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start" },
  backText: { color: colors.primary, fontSize: fsize.xl, fontFamily: font.medium },
  bigEmoji: { fontSize: 54, textAlign: "center", marginTop: spacing.xl },
  title: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface, textAlign: "center", marginTop: spacing.md },
  desc: { fontSize: fsize.lg, fontFamily: font.regular, color: colors.muted, textAlign: "center", marginTop: spacing.sm },
  input: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface, marginTop: spacing.xl },
  error: { color: colors.error, fontSize: fsize.base, fontFamily: font.medium, marginTop: spacing.sm, textAlign: "center" },
  section: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface, marginTop: spacing.xl, marginBottom: spacing.md },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.sm },
  rowTitle: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  rowSub: { fontSize: fsize.sm, fontFamily: font.regular, marginTop: 1 },
});
