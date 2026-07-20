import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useLang } from "@/src/context/LanguageContext";
import { colors, spacing, radius, font, fsize } from "@/src/theme";

type Props = {
  stato: string;
  paid?: boolean;
  reviewed?: boolean;
};

const OPEN_STATES = ["pubblicata", "in_matching", "con_proposte", "preventivo", "bozza"];

/**
 * Visual lifecycle tracker shared by all request categories.
 * Confermata → In esecuzione → Completata → Pagata → Recensita
 */
export default function StatusTimeline({ stato, paid, reviewed }: Props) {
  const { t } = useLang();
  const steps = [
    { key: "confirmed", label: t("tlConfirmed"), icon: "checkmark-circle" as const },
    { key: "inprogress", label: t("tlInProgress"), icon: "time" as const },
    { key: "completed", label: t("tlCompleted"), icon: "flag" as const },
    { key: "paid", label: t("tlPaid"), icon: "card" as const },
    { key: "reviewed", label: t("tlReviewed"), icon: "star" as const },
  ];

  // index of the highest reached step (0-based); -1 = not confirmed yet
  let reached = -1;
  if (stato === "confermata") reached = 0;
  else if (stato === "in_corso") reached = 1;
  else if (stato === "completata") reached = 2;
  else if (stato === "recensita") reached = 4;
  if (reached >= 2 && paid) reached = Math.max(reached, 3);
  if (reviewed) reached = 4;

  const notConfirmed = OPEN_STATES.includes(stato);

  return (
    <View style={styles.wrap}>
      <Text style={styles.title}>{t("tlTitle")}</Text>
      {notConfirmed ? <Text style={styles.waiting}>⏳ {t("tlWaitingConfirm")}</Text> : null}
      <View style={styles.row}>
        {steps.map((s, i) => {
          const done = i <= reached;
          const active = i === reached;
          return (
            <View key={s.key} style={styles.stepWrap}>
              {i > 0 ? <View style={[styles.line, { backgroundColor: i <= reached ? colors.brand : colors.border }]} /> : <View style={styles.line} />}
              <View style={[styles.dot, done && styles.dotDone, active && styles.dotActive]}>
                <Ionicons name={s.icon} size={14} color={done ? "#fff" : colors.muted} />
              </View>
              <Text style={[styles.stepLabel, done && styles.stepLabelDone]} numberOfLines={2}>{s.label}</Text>
            </View>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.md, marginBottom: spacing.md },
  title: { fontSize: fsize.sm, fontFamily: font.bold, color: colors.onSurfaceTertiary, marginBottom: spacing.sm },
  waiting: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.warning, marginBottom: spacing.sm },
  row: { flexDirection: "row", alignItems: "flex-start" },
  stepWrap: { flex: 1, alignItems: "center" },
  line: { position: "absolute", top: 13, right: "50%", left: -50, height: 2, backgroundColor: colors.border },
  dot: { width: 28, height: 28, borderRadius: 14, backgroundColor: colors.surface, borderWidth: 1.5, borderColor: colors.border, alignItems: "center", justifyContent: "center", zIndex: 1 },
  dotDone: { backgroundColor: colors.brand, borderColor: colors.brand },
  dotActive: { transform: [{ scale: 1.12 }] },
  stepLabel: { fontSize: 10, fontFamily: font.regular, color: colors.muted, marginTop: 4, textAlign: "center" },
  stepLabelDone: { color: colors.onSurface, fontFamily: font.medium },
});
