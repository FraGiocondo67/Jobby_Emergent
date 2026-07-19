import React, { useEffect, useState } from "react";
import { Pressable, Text, StyleSheet, Linking, Platform } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { spacing, radius, font, fsize, shadow } from "@/src/theme";

export default function WhatsAppFab({ bottomOffset = 96 }: { bottomOffset?: number }) {
  const { t } = useLang();
  const insets = useSafeAreaInsets();
  const [num, setNum] = useState<string>("");

  useEffect(() => {
    (async () => { try { const r = await api.support(); setNum(r.whatsapp || ""); } catch {} })();
  }, []);

  const open = async () => {
    const digits = (num || "").replace(/[^0-9]/g, "");
    if (!digits) return;
    const msg = encodeURIComponent(t("helpWhatsappMsg"));
    const url = `https://wa.me/${digits}?text=${msg}`;
    try { await Linking.openURL(url); } catch {}
  };

  return (
    <Pressable
      testID="whatsapp-fab"
      accessibilityLabel={t("helpWhatsapp")}
      onPress={open}
      style={[styles.fab, shadow.float, { bottom: insets.bottom + bottomOffset }]}
    >
      <Ionicons name="logo-whatsapp" size={22} color="#fff" />
      <Text style={styles.txt}>{t("helpWhatsapp")}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  fab: {
    position: "absolute",
    right: spacing.lg,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "#25D366",
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    borderRadius: radius.pill,
    ...(Platform.OS === "web" ? { position: "fixed" as any } : {}),
  },
  txt: { color: "#fff", fontFamily: font.bold, fontSize: fsize.base },
});
