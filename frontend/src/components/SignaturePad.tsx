import React, { useRef, useState, forwardRef, useImperativeHandle } from "react";
import { View, StyleSheet, PanResponder, Pressable, Text } from "react-native";
import Svg, { Path } from "react-native-svg";
import { colors, radius, spacing, font, fsize } from "@/src/theme";

/** BLOCCO 9 (fix "la delega all'intermediario deve essere firmata col dito,
 * come una vera firma a penna, non solo un nome digitato"): pad di firma
 * disegnata a mano libera. Nessuna nuova dipendenza — usa PanResponder
 * (core React Native) + react-native-svg (già installato nel progetto,
 * vedi package.json) per disegnare i tratti come un vero Path SVG, non
 * WebView/librerie esterne mai verificate in questo ambiente.
 *
 * Il risultato non viene rasterizzato (avrebbe richiesto react-native-
 * view-shot, non installato e non prebuildabile in Expo Go senza un dev
 * build) — viene esportato come SVG vettoriale vero e proprio, incapsulato
 * in una data URI (`data:image/svg+xml;utf8,...`), compatibile sia con
 * <img src> nel pannello admin sia con qualunque viewer SVG. */

const WIDTH = 320;
const HEIGHT = 160;

export type SignaturePadHandle = {
  isEmpty: () => boolean;
  clear: () => void;
  toDataUri: () => string | null;
};

function pointsToPath(points: { x: number; y: number }[]): string {
  if (points.length === 0) return "";
  if (points.length === 1) {
    const p = points[0];
    return `M ${p.x} ${p.y} L ${p.x + 0.1} ${p.y + 0.1}`;
  }
  return points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
}

const SignaturePad = forwardRef<SignaturePadHandle, { testID?: string }>(({ testID }, ref) => {
  const [strokes, setStrokes] = useState<{ x: number; y: number }[][]>([]);
  const currentStroke = useRef<{ x: number; y: number }[]>([]);
  const [, forceRender] = useState(0);

  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: (e) => {
        currentStroke.current = [{ x: e.nativeEvent.locationX, y: e.nativeEvent.locationY }];
        forceRender((n) => n + 1);
      },
      onPanResponderMove: (e) => {
        currentStroke.current = [...currentStroke.current, { x: e.nativeEvent.locationX, y: e.nativeEvent.locationY }];
        forceRender((n) => n + 1);
      },
      onPanResponderRelease: () => {
        if (currentStroke.current.length > 0) {
          setStrokes((prev) => [...prev, currentStroke.current]);
          currentStroke.current = [];
        }
      },
    })
  ).current;

  useImperativeHandle(ref, () => ({
    isEmpty: () => strokes.length === 0,
    clear: () => {
      setStrokes([]);
      currentStroke.current = [];
      forceRender((n) => n + 1);
    },
    toDataUri: () => {
      if (strokes.length === 0) return null;
      const paths = strokes
        .map((s) => `<path d="${pointsToPath(s)}" stroke="#111827" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`)
        .join("");
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${WIDTH}" height="${HEIGHT}" viewBox="0 0 ${WIDTH} ${HEIGHT}"><rect width="${WIDTH}" height="${HEIGHT}" fill="#ffffff"/>${paths}</svg>`;
      return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
    },
  }));

  const allStrokes = currentStroke.current.length > 0 ? [...strokes, currentStroke.current] : strokes;

  return (
    <View>
      <View testID={testID} style={styles.pad} {...panResponder.panHandlers}>
        <Svg width={WIDTH} height={HEIGHT} viewBox={`0 0 ${WIDTH} ${HEIGHT}`}>
          {allStrokes.map((s, i) => (
            <Path key={i} d={pointsToPath(s)} stroke="#111827" strokeWidth={2.5} fill="none" strokeLinecap="round" strokeLinejoin="round" />
          ))}
        </Svg>
        {allStrokes.length === 0 ? <Text style={styles.hint}>Firma qui</Text> : null}
      </View>
      <Pressable
        testID={testID ? `${testID}-clear` : undefined}
        onPress={() => {
          setStrokes([]);
          currentStroke.current = [];
          forceRender((n) => n + 1);
        }}
        style={styles.clearBtn}
      >
        <Text style={styles.clearText}>Cancella firma</Text>
      </Pressable>
    </View>
  );
});

SignaturePad.displayName = "SignaturePad";
export default SignaturePad;

const styles = StyleSheet.create({
  pad: {
    width: WIDTH,
    height: HEIGHT,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    alignSelf: "center",
    overflow: "hidden",
    alignItems: "center",
    justifyContent: "center",
  },
  hint: { position: "absolute", color: colors.muted, fontSize: fsize.base, fontFamily: font.regular },
  clearBtn: { alignSelf: "center", marginTop: spacing.sm },
  clearText: { color: colors.brand, fontSize: fsize.sm, fontFamily: font.medium },
});
