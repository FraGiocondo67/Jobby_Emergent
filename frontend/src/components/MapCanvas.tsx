import React, { useEffect, useRef } from "react";
import { View, StyleSheet, Animated, Easing, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, radius, font, fsize } from "@/src/theme";

type Pin = { lat: number; lng: number; label?: string; highlight?: boolean };

/**
 * Lightweight stylized map that works on all platforms (incl. web preview).
 * Projects lat/lng around a center into relative screen positions.
 */
export default function MapCanvas({
  center,
  pins = [],
  radar = false,
  height = 260,
}: {
  center: { lat: number; lng: number };
  pins?: Pin[];
  radar?: boolean;
  height?: number;
}) {
  const pulse = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!radar) return;
    const loop = Animated.loop(
      Animated.timing(pulse, {
        toValue: 1,
        duration: 2200,
        easing: Easing.out(Easing.ease),
        useNativeDriver: true,
      })
    );
    loop.start();
    return () => loop.stop();
  }, [radar, pulse]);

  const project = (p: { lat: number; lng: number }) => {
    const scale = 2600;
    const x = 50 + (p.lng - center.lng) * scale;
    const y = 50 - (p.lat - center.lat) * scale;
    return {
      left: `${Math.max(6, Math.min(94, x))}%` as any,
      top: `${Math.max(8, Math.min(90, y))}%` as any,
    };
  };

  return (
    <View style={[styles.map, { height }]} testID="map-canvas">
      {/* grid */}
      {[...Array(5)].map((_, i) => (
        <View key={`h${i}`} style={[styles.gridLine, { top: `${(i + 1) * 16}%` }]} />
      ))}
      {[...Array(5)].map((_, i) => (
        <View key={`v${i}`} style={[styles.gridLineV, { left: `${(i + 1) * 16}%` }]} />
      ))}

      {radar &&
        [0, 1].map((i) => (
          <Animated.View
            key={i}
            style={[
              styles.pulse,
              {
                opacity: pulse.interpolate({ inputRange: [0, 1], outputRange: [0.5, 0] }),
                transform: [
                  { scale: pulse.interpolate({ inputRange: [0, 1], outputRange: [0.3, 3.4] }) },
                ],
              },
            ]}
          />
        ))}

      {/* center (you) */}
      <View style={[styles.pinWrap, { left: "50%", top: "50%" }]}>
        <View style={styles.you}>
          <View style={styles.youDot} />
        </View>
      </View>

      {pins.map((p, idx) => {
        const pos = project(p);
        return (
          <View key={idx} style={[styles.pinWrap, pos]}>
            <View style={[styles.pin, p.highlight && styles.pinHighlight]}>
              <Ionicons
                name="location"
                size={p.highlight ? 22 : 18}
                color={p.highlight ? colors.brandSecondary : colors.brand}
              />
            </View>
            {p.label ? <Text style={styles.pinLabel}>{p.label}</Text> : null}
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  map: {
    width: "100%",
    backgroundColor: "#E9EEE9",
    borderRadius: radius.lg,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: colors.border,
  },
  gridLine: { position: "absolute", left: 0, right: 0, height: 1, backgroundColor: "rgba(74,123,89,0.08)" },
  gridLineV: { position: "absolute", top: 0, bottom: 0, width: 1, backgroundColor: "rgba(74,123,89,0.08)" },
  pinWrap: { position: "absolute", alignItems: "center", marginLeft: -16, marginTop: -16 },
  you: {
    width: 26, height: 26, borderRadius: 13, backgroundColor: "rgba(74,123,89,0.2)",
    alignItems: "center", justifyContent: "center",
  },
  youDot: { width: 14, height: 14, borderRadius: 7, backgroundColor: colors.brand, borderWidth: 2, borderColor: "#fff" },
  pin: {
    width: 32, height: 32, borderRadius: 16, backgroundColor: "#fff",
    alignItems: "center", justifyContent: "center",
    shadowColor: "#000", shadowOpacity: 0.15, shadowRadius: 4, shadowOffset: { width: 0, height: 2 }, elevation: 3,
  },
  pinHighlight: { transform: [{ scale: 1.15 }] },
  pinLabel: {
    fontSize: fsize.sm, fontFamily: font.medium, color: colors.onSurface,
    backgroundColor: "#fff", paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6, marginTop: 2, overflow: "hidden",
  },
  pulse: {
    position: "absolute", left: "50%", top: "50%", width: 60, height: 60, borderRadius: 30,
    marginLeft: -30, marginTop: -30, backgroundColor: colors.brand,
  },
});
