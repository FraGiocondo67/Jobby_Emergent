import React, { useRef, forwardRef, useImperativeHandle } from "react";
import { View, StyleSheet, Pressable, Text } from "react-native";
import SignatureScreen, { SignatureViewRef } from "react-native-signature-canvas";
import { colors, radius, spacing, font, fsize } from "@/src/theme";

/** BLOCCO 9 (fix "la firma con il dito non viene memorizzata, sparisce
 * appena viene fatta"): la prima versione era disegnata a mano con
 * PanResponder + react-native-svg, dentro una ScrollView — il gesture
 * responder dello scroll intercettava/terminava il tocco a metà tratto (RN
 * non garantisce che un PanResponder annidato in una ScrollView mantenga la
 * responsabilità del gesto), perdendo il disegno prima ancora del rilascio.
 * Sostituito con react-native-signature-canvas: usa una WebView isolata
 * (dipendenza già presente nel progetto, react-native-webview, unico peer
 * richiesto — nessun nuovo modulo nativo, resta compatibile con Expo Go)
 * che gestisce il canvas HTML5 al suo interno, fuori dalla catena di
 * gesture RN — niente più conflitto con lo scroll del genitore. L'output è
 * un vero PNG rasterizzato (data URI base64), non più un SVG vettoriale. */

export type SignaturePadHandle = {
  getDataUri: () => Promise<string | null>;
  clear: () => void;
};

const WIDTH = 320;
const HEIGHT = 160;

const SignaturePad = forwardRef<SignaturePadHandle, { testID?: string }>(({ testID }, ref) => {
  const sigRef = useRef<SignatureViewRef>(null);
  const resolverRef = useRef<((v: string | null) => void) | null>(null);

  useImperativeHandle(ref, () => ({
    getDataUri: () =>
      new Promise<string | null>((resolve) => {
        resolverRef.current = resolve;
        // readSignature() è asincrono: il risultato arriva via onOK/onEmpty
        // (postMessage dalla WebView), non come valore di ritorno diretto.
        sigRef.current?.readSignature();
      }),
    clear: () => sigRef.current?.clearSignature(),
  }));

  return (
    <View>
      <View testID={testID} style={styles.wrap}>
        <SignatureScreen
          ref={sigRef}
          onOK={(sig: string) => {
            resolverRef.current?.(sig);
            resolverRef.current = null;
          }}
          onEmpty={() => {
            resolverRef.current?.(null);
            resolverRef.current = null;
          }}
          autoClear={false}
          descriptionText=""
          webStyle=".m-signature-pad--footer { display: none; margin: 0; } .m-signature-pad--body { border: none; } .m-signature-pad { box-shadow: none; border: none; margin: 0; } body,html { background-color: #ffffff; height: 100%; }"
        />
      </View>
      <Pressable testID={testID ? `${testID}-clear` : undefined} onPress={() => sigRef.current?.clearSignature()} style={styles.clearBtn}>
        <Text style={styles.clearText}>Cancella firma</Text>
      </Pressable>
    </View>
  );
});

SignaturePad.displayName = "SignaturePad";
export default SignaturePad;

const styles = StyleSheet.create({
  wrap: {
    width: WIDTH,
    height: HEIGHT,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    alignSelf: "center",
    overflow: "hidden",
  },
  clearBtn: { alignSelf: "center", marginTop: spacing.sm },
  clearText: { color: colors.brand, fontSize: fsize.sm, fontFamily: font.medium },
});
