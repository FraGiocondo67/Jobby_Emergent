import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, Alert, Modal, KeyboardAvoidingView, Platform, Switch } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Button } from "@/src/components/UI";

const EMPTY = { nome: "", eta_mesi: "36", sesso: "", abitudini: "", allergie: "", note: "", consenso: false };

export default function ChildrenScreen() {
  const { t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [cards, setCards] = useState<any[]>([]);
  const [modal, setModal] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [f, setF] = useState<any>(EMPTY);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => { try { setCards(await api.bsChildren()); } catch {} }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const openNew = () => { setEditing(null); setF(EMPTY); setModal(true); };
  const openEdit = (c: any) => { setEditing(c.card_id); setF({ ...c, eta_mesi: String(c.eta_mesi) }); setModal(true); };

  const save = async () => {
    if (!f.nome.trim()) { Alert.alert(t("bsChildName")); return; }
    if (!f.consenso) { Alert.alert(t("bsConsentRequired")); return; }
    setBusy(true);
    try {
      const payload = { ...f, eta_mesi: Number(f.eta_mesi) || 0 };
      if (editing) await api.bsUpdateChild(editing, payload); else await api.bsCreateChild(payload);
      setModal(false); await load();
    } catch { Alert.alert(t("error")); } finally { setBusy(false); }
  };

  const del = (c: any) => Alert.alert(c.nome, "", [
    { text: t("cancel"), style: "cancel" },
    { text: t("delete"), style: "destructive", onPress: async () => { try { await api.bsDeleteChild(c.card_id); load(); } catch {} } },
  ]);

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="children-back" onPress={() => router.back()} hitSlop={12}><Ionicons name="arrow-back" size={24} color={colors.onSurface} /></Pressable>
        <Text style={styles.headerTitle}>{t("bsChildren")}</Text>
        <View style={{ width: 24 }} />
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 100 }}>
        {cards.length === 0 ? <Text style={styles.empty}>{t("bsNoChildren")}</Text> : null}
        {cards.map((c) => (
          <View key={c.card_id} style={[styles.card, shadow.card]}>
            <View style={styles.avatar}><Text style={{ fontSize: 24 }}>{c.sesso === "f" ? "👧" : c.sesso === "m" ? "👦" : "🧒"}</Text></View>
            <Pressable style={{ flex: 1 }} testID={`child-${c.card_id}`} onPress={() => openEdit(c)}>
              <Text style={styles.cardName}>{c.nome}</Text>
              <Text style={styles.cardSub}>{Math.floor(c.eta_mesi / 12)} anni {c.eta_mesi % 12 ? `${c.eta_mesi % 12}m` : ""}{c.allergie ? ` · ⚠️ ${c.allergie}` : ""}</Text>
            </Pressable>
            <Pressable testID={`child-del-${c.card_id}`} onPress={() => del(c)} hitSlop={10}><Ionicons name="trash-outline" size={22} color={colors.error} /></Pressable>
          </View>
        ))}
        <Button testID="add-child-btn" label={t("bsAddChild")} icon="add" variant="secondary" onPress={openNew} style={{ marginTop: spacing.md }} />
      </ScrollView>

      <Modal visible={modal} animationType="slide" transparent onRequestClose={() => setModal(false)}>
        <KeyboardAvoidingView style={styles.modalWrap} behavior={Platform.OS === "ios" ? "padding" : undefined}>
          <View style={styles.modalCard}>
            <View style={styles.modalHead}>
              <Text style={styles.modalTitle}>{editing ? t("edit") : t("bsAddChild")}</Text>
              <Pressable testID="child-modal-close" onPress={() => setModal(false)} hitSlop={10}><Ionicons name="close" size={24} color={colors.onSurface} /></Pressable>
            </View>
            <ScrollView keyboardShouldPersistTaps="handled">
              <Text style={styles.label}>{t("bsChildName")}</Text>
              <TextInput testID="child-name" style={styles.input} value={f.nome} onChangeText={(v) => setF({ ...f, nome: v })} placeholderTextColor={colors.muted} />
              <Text style={styles.label}>{t("bsChildAge")}</Text>
              <TextInput testID="child-age" style={styles.input} value={f.eta_mesi} onChangeText={(v) => setF({ ...f, eta_mesi: v.replace(/[^0-9]/g, "") })} keyboardType="number-pad" placeholderTextColor={colors.muted} />
              <Text style={styles.label}>{t("bsChildSex")}</Text>
              <View style={styles.sexRow}>
                {[["m", "👦"], ["f", "👧"], ["", "🧒"]].map(([id, emo]) => (
                  <Pressable key={id} testID={`child-sex-${id || "none"}`} style={[styles.sexBtn, f.sesso === id && styles.sexOn]} onPress={() => setF({ ...f, sesso: id })}><Text style={{ fontSize: 22 }}>{emo}</Text></Pressable>))}
              </View>
              <Text style={styles.label}>{t("bsHabits")}</Text>
              <TextInput testID="child-habits" style={styles.input} value={f.abitudini} onChangeText={(v) => setF({ ...f, abitudini: v })} placeholderTextColor={colors.muted} />
              <Text style={styles.label}>{t("bsAllergies")}</Text>
              <TextInput testID="child-allergies" style={styles.input} value={f.allergie} onChangeText={(v) => setF({ ...f, allergie: v })} placeholderTextColor={colors.muted} />
              <Text style={styles.label}>{t("bsChildNotes")}</Text>
              <TextInput testID="child-notes" style={[styles.input, { minHeight: 60, textAlignVertical: "top" }]} value={f.note} onChangeText={(v) => setF({ ...f, note: v })} multiline placeholderTextColor={colors.muted} />
              <View style={styles.consentRow}>
                <Switch testID="child-consent" value={f.consenso} onValueChange={(v) => setF({ ...f, consenso: v })} trackColor={{ true: colors.brand, false: colors.borderStrong }} thumbColor="#fff" />
                <Text style={styles.consentText}>{t("bsConsent")}</Text>
              </View>
              <Button testID="child-save" label={t("save")} loading={busy} onPress={save} style={{ marginTop: spacing.md, marginBottom: spacing.xl }} />
            </ScrollView>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.divider },
  headerTitle: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  empty: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, textAlign: "center", marginVertical: spacing.xl },
  card: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.md },
  avatar: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  cardName: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  cardSub: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 2 },
  modalWrap: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(0,0,0,0.4)" },
  modalCard: { backgroundColor: colors.surface, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, padding: spacing.lg, maxHeight: "90%" },
  modalHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  modalTitle: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.onSurface },
  label: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurfaceTertiary, marginTop: spacing.md, marginBottom: spacing.sm },
  input: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  sexRow: { flexDirection: "row", gap: spacing.sm },
  sexBtn: { width: 56, height: 56, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceSecondary },
  sexOn: { borderColor: colors.brand, backgroundColor: colors.brandTertiary },
  consentRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, marginTop: spacing.lg },
  consentText: { flex: 1, fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface },
});
