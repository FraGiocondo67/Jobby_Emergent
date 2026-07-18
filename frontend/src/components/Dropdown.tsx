import React, { useState } from "react";
import { View, Text, StyleSheet, Pressable, Modal, ScrollView } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";

export type DropdownOption = { value: string; label: string };

type Props = {
  value: string | null;
  options: DropdownOption[];
  placeholder?: string;
  onChange: (value: string) => void;
  testID?: string;
};

export default function Dropdown({ value, options, placeholder = "Select…", onChange, testID }: Props) {
  const [open, setOpen] = useState(false);
  const selected = options.find((o) => o.value === value);

  return (
    <>
      <Pressable testID={testID} style={[styles.field, shadow.card]} onPress={() => setOpen(true)}>
        <Text style={[styles.value, !selected && styles.placeholder]}>{selected ? selected.label : placeholder}</Text>
        <Ionicons name="chevron-down" size={20} color={colors.muted} />
      </Pressable>
      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <Pressable style={styles.overlay} onPress={() => setOpen(false)}>
          <View style={styles.sheet}>
            <View style={styles.handle} />
            <ScrollView>
              {options.map((o) => {
                const active = o.value === value;
                return (
                  <Pressable
                    key={o.value}
                    testID={`${testID}-opt-${o.value}`}
                    style={[styles.option, active && styles.optionActive]}
                    onPress={() => { onChange(o.value); setOpen(false); }}
                  >
                    <Text style={[styles.optionText, active && { color: colors.brand, fontFamily: font.bold }]}>{o.label}</Text>
                    {active ? <Ionicons name="checkmark" size={20} color={colors.brand} /> : null}
                  </Pressable>
                );
              })}
            </ScrollView>
          </View>
        </Pressable>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  field: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 14 },
  value: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
  placeholder: { color: colors.muted, fontFamily: font.regular },
  overlay: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: 24, borderTopRightRadius: 24, paddingBottom: 30, paddingHorizontal: spacing.lg, paddingTop: spacing.md, maxHeight: "60%" },
  handle: { width: 44, height: 5, borderRadius: 3, backgroundColor: colors.borderStrong, alignSelf: "center", marginBottom: spacing.md },
  option: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider },
  optionActive: {},
  optionText: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface },
});
