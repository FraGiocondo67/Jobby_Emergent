import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, KeyboardAvoidingView, Platform, Alert } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useLocalSearchParams, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Button } from "@/src/components/UI";

export default function Beneficiaries() {
  const { type } = useLocalSearchParams<{ type?: string }>();
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [items, setItems] = useState<any[]>([]);
  const [benType, setBenType] = useState<"abroad" | "local">((type as any) === "local" ? "local" : "abroad");
  const [name, setName] = useState("");
  const [iban, setIban] = useState("");
  const [swift, setSwift] = useState("");
  const [bankName, setBankName] = useState("");
  const [country, setCountry] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setItems(await api.beneficiaries()); } catch {}
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const add = async () => {
    if (!name.trim() || !iban.trim()) { Alert.alert(t("beneficiaryNameLabel"), t("ibanLabel")); return; }
    setBusy(true);
    try {
      await api.createBeneficiary({ name: name.trim(), type: benType, iban: iban.trim(), swift: swift.trim(), bank_name: bankName.trim(), country: country.trim() });
      setName(""); setIban(""); setSwift(""); setBankName(""); setCountry("");
      load();
    } catch { Alert.alert(t("error")); } finally { setBusy(false); }
  };

  const remove = async (id: string) => {
    try { await api.deleteBeneficiary(id); load(); } catch {}
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="ben-back" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.primary} />
          <Text style={styles.backText}>{t("backStep")}</Text>
        </Pressable>
      </View>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
          <Text style={styles.title}>{t("beneficiariesTitle")}</Text>

          {items.length === 0 ? <Text style={styles.empty}>{t("noBeneficiaries")}</Text> : items.map((b) => (
            <View key={b.ben_id} style={[styles.row, shadow.card]} testID={`ben-${b.ben_id}`}>
              <View style={[styles.badge, { backgroundColor: b.type === "abroad" ? "#8B5CF622" : "#10B98122" }]}>
                <Text style={{ fontSize: 18 }}>{b.type === "abroad" ? "🌍" : "💶"}</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowName}>{b.name}</Text>
                <Text style={styles.rowSub}>{b.iban}{b.bank_name ? ` · ${b.bank_name}` : ""}</Text>
              </View>
              <Pressable testID={`ben-del-${b.ben_id}`} onPress={() => remove(b.ben_id)} hitSlop={10}>
                <Ionicons name="trash-outline" size={20} color={colors.error} />
              </Pressable>
            </View>
          ))}

          <Text style={styles.section}>{t("addBeneficiary")}</Text>
          <View style={styles.typeRow}>
            {(["abroad", "local"] as const).map((tp) => (
              <Pressable key={tp} testID={`ben-type-${tp}`} style={[styles.typeBtn, benType === tp && styles.typeOn]} onPress={() => setBenType(tp)}>
                <Text style={[styles.typeText, benType === tp && { color: "#fff" }]}>{tp === "abroad" ? t("filterAbroad") : t("filterLocal")}</Text>
              </Pressable>
            ))}
          </View>
          <TextInput testID="ben-name" style={styles.input} value={name} onChangeText={setName} placeholder={t("beneficiaryNameLabel")} placeholderTextColor={colors.muted} />
          <TextInput testID="ben-iban" style={styles.input} value={iban} onChangeText={setIban} placeholder={t("ibanLabel")} placeholderTextColor={colors.muted} autoCapitalize="characters" />
          <TextInput testID="ben-swift" style={styles.input} value={swift} onChangeText={setSwift} placeholder={t("swiftLabel")} placeholderTextColor={colors.muted} autoCapitalize="characters" />
          <TextInput testID="ben-bank" style={styles.input} value={bankName} onChangeText={setBankName} placeholder={t("bankNameLabel")} placeholderTextColor={colors.muted} />
          <TextInput testID="ben-country" style={styles.input} value={country} onChangeText={setCountry} placeholder={t("countryLabel")} placeholderTextColor={colors.muted} />
          <Button testID="ben-save" label={t("saveBtn")} loading={busy} onPress={add} style={{ marginTop: spacing.md }} />
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  backBtn: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start" },
  backText: { color: colors.primary, fontSize: fsize.xl, fontFamily: font.medium },
  title: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface, marginBottom: spacing.md },
  empty: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.sm, borderWidth: 1, borderColor: colors.border },
  badge: { width: 40, height: 40, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  rowName: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  rowSub: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 1 },
  section: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface, marginTop: spacing.xl, marginBottom: spacing.md },
  typeRow: { flexDirection: "row", gap: spacing.md, marginBottom: spacing.sm },
  typeBtn: { flex: 1, paddingVertical: spacing.sm, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, alignItems: "center" },
  typeOn: { backgroundColor: colors.brand, borderColor: colors.brand },
  typeText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  input: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface, marginBottom: spacing.sm },
});
