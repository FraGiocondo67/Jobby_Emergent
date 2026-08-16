import React, { useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, Modal, ScrollView } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, spacing, radius, font, fsize } from "@/src/theme";
import type { Lang } from "@/src/i18n";

const MONTHS = {
  it: ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"],
  en: ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
};
const DOW = ["L", "M", "M", "G", "V", "S", "D"];

const pad = (n: number) => (n < 10 ? `0${n}` : `${n}`);

function parseDate(v: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec((v || "").trim());
  if (!m) return null;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return isNaN(d.getTime()) ? null : d;
}

function daysInMonth(y: number, m: number) {
  return new Date(y, m + 1, 0).getDate();
}

export function DateField({
  value, onChange, testID, lang = "it", placeholder = "YYYY-MM-DD",
}: { value: string; onChange: (v: string) => void; testID?: string; lang?: Lang; placeholder?: string }) {
  const [open, setOpen] = useState(false);
  const base = parseDate(value) || new Date();
  const [viewY, setViewY] = useState(base.getFullYear());
  const [viewM, setViewM] = useState(base.getMonth());
  const selected = parseDate(value);

  const openCal = () => {
    const b = parseDate(value) || new Date();
    setViewY(b.getFullYear());
    setViewM(b.getMonth());
    setOpen(true);
  };

  const changeMonth = (delta: number) => {
    let m = viewM + delta;
    let y = viewY;
    if (m < 0) { m = 11; y -= 1; }
    if (m > 11) { m = 0; y += 1; }
    setViewM(m); setViewY(y);
  };

  const pick = (day: number) => {
    onChange(`${viewY}-${pad(viewM + 1)}-${pad(day)}`);
    setOpen(false);
  };

  const firstDow = (new Date(viewY, viewM, 1).getDay() + 6) % 7; // Monday-first
  const total = daysInMonth(viewY, viewM);
  const cells: (number | null)[] = [];
  for (let i = 0; i < firstDow; i++) cells.push(null);
  for (let d = 1; d <= total; d++) cells.push(d);
  while (cells.length % 7 !== 0) cells.push(null);

  const isSel = (d: number) => selected && selected.getFullYear() === viewY && selected.getMonth() === viewM && selected.getDate() === d;

  return (
    <>
      <View style={styles.fieldRow}>
        <TextInput
          testID={testID}
          style={styles.fieldInput}
          value={value}
          onChangeText={onChange}
          placeholder={placeholder}
          placeholderTextColor={colors.muted}
          keyboardType="numbers-and-punctuation"
        />
        <Pressable testID={testID ? `${testID}-cal` : undefined} style={styles.iconBtn} onPress={openCal} hitSlop={8}>
          <Ionicons name="calendar-outline" size={20} color={colors.brand} />
        </Pressable>
      </View>

      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <Pressable style={styles.backdrop} onPress={() => setOpen(false)}>
          <Pressable style={styles.sheet} onPress={() => {}}>
            <View style={styles.calHeader}>
              <Pressable testID="cal-prev" onPress={() => changeMonth(-1)} hitSlop={10} style={styles.navBtn}>
                <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
              </Pressable>
              {/* BLOCCO 9: MONTHS ha solo it/en — per le 5 nuove lingue
                  (zh/ru/de/es/fr) mostra i nomi mese in inglese finché non
                  vengono aggiunte traduzioni dedicate qui, invece di andare
                  in errore/undefined. */}
              <Text style={styles.calTitle}>{(MONTHS[lang as "it" | "en"] || MONTHS.en)[viewM]} {viewY}</Text>
              <Pressable testID="cal-next" onPress={() => changeMonth(1)} hitSlop={10} style={styles.navBtn}>
                <Ionicons name="chevron-forward" size={22} color={colors.onSurface} />
              </Pressable>
            </View>
            <View style={styles.dowRow}>
              {DOW.map((d, i) => (<Text key={i} style={styles.dowText}>{d}</Text>))}
            </View>
            <View style={styles.grid}>
              {cells.map((c, i) => (
                <View key={i} style={styles.cell}>
                  {c ? (
                    <Pressable
                      testID={`cal-day-${c}`}
                      style={[styles.dayBtn, isSel(c) && styles.dayBtnSel]}
                      onPress={() => pick(c)}
                    >
                      <Text style={[styles.dayText, isSel(c) && styles.dayTextSel]}>{c}</Text>
                    </Pressable>
                  ) : null}
                </View>
              ))}
            </View>
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}

export function TimeField({
  value, onChange, testID,
}: { value: string; onChange: (v: string) => void; testID?: string }) {
  const [open, setOpen] = useState(false);
  const m = /^(\d{1,2}):(\d{2})$/.exec((value || "").trim());
  const curH = m ? Math.min(23, Number(m[1])) : 10;
  const curMin = m ? Math.min(59, Number(m[2])) : 0;
  const hours = Array.from({ length: 24 }, (_, i) => i);
  const mins = Array.from({ length: 12 }, (_, i) => i * 5);

  const setPart = (h: number, mm: number) => onChange(`${pad(h)}:${pad(mm)}`);

  return (
    <>
      <View style={styles.fieldRow}>
        <TextInput
          testID={testID}
          style={styles.fieldInput}
          value={value}
          onChangeText={onChange}
          placeholder="HH:MM"
          placeholderTextColor={colors.muted}
          keyboardType="numbers-and-punctuation"
        />
        <Pressable testID={testID ? `${testID}-clock` : undefined} style={styles.iconBtn} onPress={() => setOpen(true)} hitSlop={8}>
          <Ionicons name="time-outline" size={20} color={colors.brand} />
        </Pressable>
      </View>

      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <Pressable style={styles.backdrop} onPress={() => setOpen(false)}>
          <Pressable style={styles.sheet} onPress={() => {}}>
            <Text style={styles.calTitle}>{pad(curH)}:{pad(curMin)}</Text>
            <View style={styles.timeCols}>
              <ScrollView style={styles.timeCol} showsVerticalScrollIndicator={false}>
                {hours.map((h) => (
                  <Pressable key={h} testID={`hh-${h}`} style={[styles.timeItem, h === curH && styles.timeItemSel]} onPress={() => setPart(h, curMin)}>
                    <Text style={[styles.timeItemText, h === curH && styles.timeItemTextSel]}>{pad(h)}</Text>
                  </Pressable>
                ))}
              </ScrollView>
              <Text style={styles.timeSep}>:</Text>
              <ScrollView style={styles.timeCol} showsVerticalScrollIndicator={false}>
                {mins.map((mm) => (
                  <Pressable key={mm} testID={`mm-${mm}`} style={[styles.timeItem, mm === curMin && styles.timeItemSel]} onPress={() => setPart(curH, mm)}>
                    <Text style={[styles.timeItemText, mm === curMin && styles.timeItemTextSel]}>{pad(mm)}</Text>
                  </Pressable>
                ))}
              </ScrollView>
            </View>
            <Pressable testID="time-done" style={styles.doneBtn} onPress={() => setOpen(false)}>
              <Text style={styles.doneText}>OK</Text>
            </Pressable>
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  fieldRow: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md },
  fieldInput: { flex: 1, padding: spacing.md, fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  iconBtn: { paddingHorizontal: spacing.md, paddingVertical: spacing.md },
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", alignItems: "center", justifyContent: "center", padding: spacing.lg },
  sheet: { width: "100%", maxWidth: 360, backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg },
  calHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  navBtn: { padding: 6 },
  calTitle: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface, textAlign: "center" },
  dowRow: { flexDirection: "row", marginBottom: 4 },
  dowText: { flex: 1, textAlign: "center", fontSize: fsize.sm, fontFamily: font.medium, color: colors.muted },
  grid: { flexDirection: "row", flexWrap: "wrap" },
  cell: { width: `${100 / 7}%`, aspectRatio: 1, alignItems: "center", justifyContent: "center", padding: 2 },
  dayBtn: { width: 38, height: 38, borderRadius: 19, alignItems: "center", justifyContent: "center" },
  dayBtnSel: { backgroundColor: colors.brand },
  dayText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface },
  dayTextSel: { color: "#fff", fontFamily: font.bold },
  timeCols: { flexDirection: "row", alignItems: "center", justifyContent: "center", height: 200, marginVertical: spacing.md },
  timeCol: { width: 80 },
  timeSep: { fontSize: fsize.xl, fontFamily: font.bold, color: colors.onSurface, marginHorizontal: spacing.sm },
  timeItem: { paddingVertical: spacing.sm, alignItems: "center", borderRadius: radius.md },
  timeItemSel: { backgroundColor: colors.brandTertiary },
  timeItemText: { fontSize: fsize.lg, fontFamily: font.regular, color: colors.onSurface },
  timeItemTextSel: { color: colors.onBrandTertiary, fontFamily: font.bold },
  doneBtn: { height: 46, borderRadius: radius.md, backgroundColor: colors.brand, alignItems: "center", justifyContent: "center", marginTop: spacing.sm },
  doneText: { color: "#fff", fontSize: fsize.lg, fontFamily: font.bold },
});
