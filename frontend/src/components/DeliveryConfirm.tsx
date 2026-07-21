import React, { useCallback, useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import QRCode from "react-native-qrcode-svg";
import { CameraView, useCameraPermissions } from "expo-camera";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize } from "@/src/theme";

/**
 * Consegna verificata (QR / codice a 6 cifre).
 * - ClientDeliveryQR: mostrato al CLIENTE (proprietario). Espone il QR + codice da far leggere/inserire.
 * - EarnerConfirm: mostrato al PROVIDER/ATTIVITÀ. Scansiona il QR del cliente o inserisce il codice.
 */

export function ClientDeliveryQR({ refId, onReleased }: { refId: string; onReleased?: () => void }) {
  const [conf, setConf] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const c = await api.deliveryRef(refId);
      setConf(c);
    } catch {
      setConf(null);
      onReleased?.();
    } finally {
      setLoading(false);
    }
  }, [refId]);

  useEffect(() => {
    load();
    const iv = setInterval(async () => {
      try {
        const s = await api.deliveryStatus(refId);
        if (!s.pending) { onReleased?.(); }
      } catch {}
    }, 5000);
    return () => clearInterval(iv);
  }, [load, refId]);

  if (loading) return <View style={styles.card}><ActivityIndicator color={colors.brand} /></View>;
  if (!conf) return null;

  return (
    <View style={styles.card} testID="client-delivery-qr">
      <View style={styles.rowTitle}>
        <Ionicons name="qr-code-outline" size={20} color={colors.brand} />
        <Text style={styles.title}>Conferma consegna</Text>
      </View>
      <Text style={styles.sub}>Mostra questo QR (o il codice) al professionista per liberare il pagamento.</Text>
      <View style={styles.qrWrap}>
        <QRCode value={`JOBBY:${conf.token}`} size={160} />
      </View>
      <Text style={styles.codeLabel}>Codice</Text>
      <Text style={styles.code} testID="delivery-code">{(conf.code || "").replace(/(\d{3})(\d{3})/, "$1 $2")}</Text>
    </View>
  );
}

export function EarnerConfirm({ refId, onConfirmed }: { refId: string; onConfirmed?: () => void }) {
  const [mode, setMode] = useState<"idle" | "scan" | "code">("idle");
  const [permission, requestPermission] = useCameraPermissions();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const scannedRef = useRef(false);

  const doToken = async (token: string) => {
    if (busy) return;
    setBusy(true); setErr("");
    try {
      await api.deliveryConfirmToken(token);
      onConfirmed?.();
    } catch (e: any) {
      setErr("QR non valido o non associato a questo lavoro.");
      scannedRef.current = false;
    } finally { setBusy(false); }
  };

  const doCode = async () => {
    if (busy || code.trim().length < 6) return;
    setBusy(true); setErr("");
    try {
      await api.deliveryConfirmCode(refId, code.trim());
      onConfirmed?.();
    } catch (e: any) {
      setErr("Codice errato. Riprova.");
    } finally { setBusy(false); }
  };

  const openScanner = async () => {
    if (!permission?.granted) {
      const res = await requestPermission();
      if (!res.granted) {
        if (!res.canAskAgain) {
          setErr("Permesso fotocamera negato.");
        }
        return;
      }
    }
    scannedRef.current = false;
    setMode("scan");
  };

  if (mode === "scan") {
    return (
      <View style={styles.card} testID="earner-scan">
        <Text style={styles.title}>Inquadra il QR del cliente</Text>
        <View style={styles.scanBox}>
          <CameraView
            style={StyleSheet.absoluteFill}
            facing="back"
            barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
            onBarcodeScanned={({ data }) => {
              if (scannedRef.current) return;
              scannedRef.current = true;
              const token = (data || "").startsWith("JOBBY:") ? data.slice(6) : data;
              doToken(token);
            }}
          />
        </View>
        {err ? <Text style={styles.err}>{err}</Text> : null}
        <Pressable style={styles.ghostBtn} onPress={() => setMode("idle")}>
          <Text style={styles.ghostTxt}>Annulla</Text>
        </Pressable>
      </View>
    );
  }

  if (mode === "code") {
    return (
      <View style={styles.card} testID="earner-code">
        <Text style={styles.title}>Inserisci il codice del cliente</Text>
        <TextInput
          testID="earner-code-input"
          style={styles.input}
          value={code}
          onChangeText={(v) => setCode(v.replace(/\D/g, "").slice(0, 6))}
          keyboardType="number-pad"
          placeholder="6 cifre"
          placeholderTextColor={colors.muted}
          maxLength={6}
        />
        {err ? <Text style={styles.err}>{err}</Text> : null}
        <Pressable testID="earner-code-submit" style={[styles.primaryBtn, (busy || code.length < 6) && { opacity: 0.5 }]} onPress={doCode} disabled={busy || code.length < 6}>
          {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryTxt}>Conferma pagamento</Text>}
        </Pressable>
        <Pressable style={styles.ghostBtn} onPress={() => setMode("idle")}>
          <Text style={styles.ghostTxt}>Indietro</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View style={styles.card} testID="earner-confirm">
      <View style={styles.rowTitle}>
        <Ionicons name="shield-checkmark-outline" size={20} color={colors.brand} />
        <Text style={styles.title}>Conferma consegna</Text>
      </View>
      <Text style={styles.sub}>Il cliente ha attivato la conferma con QR. Scansiona il suo QR o inserisci il codice a 6 cifre per liberare il pagamento.</Text>
      {err ? <Text style={styles.err}>{err}</Text> : null}
      <Pressable testID="earner-scan-btn" style={styles.primaryBtn} onPress={openScanner}>
        <Ionicons name="qr-code-outline" size={18} color="#fff" />
        <Text style={styles.primaryTxt}>Scansiona QR</Text>
      </Pressable>
      <Pressable testID="earner-code-btn" style={styles.secondaryBtn} onPress={() => { setErr(""); setMode("code"); }}>
        <Text style={styles.secondaryTxt}>Inserisci codice a mano</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, marginVertical: spacing.md, alignItems: "center", gap: spacing.sm },
  rowTitle: { flexDirection: "row", alignItems: "center", gap: 8 },
  title: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  sub: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, textAlign: "center" },
  qrWrap: { padding: spacing.md, backgroundColor: "#fff", borderRadius: radius.md, marginTop: spacing.sm },
  codeLabel: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: spacing.sm },
  code: { fontSize: 30, fontFamily: font.bold, color: colors.brand, letterSpacing: 3 },
  scanBox: { width: "100%", aspectRatio: 1, borderRadius: radius.md, overflow: "hidden", backgroundColor: "#000", marginVertical: spacing.sm },
  input: { width: "100%", backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: 22, fontFamily: font.bold, color: colors.onSurface, textAlign: "center", letterSpacing: 4 },
  primaryBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: colors.brand, borderRadius: radius.pill, paddingVertical: spacing.md, paddingHorizontal: spacing.xl, width: "100%", marginTop: spacing.sm },
  primaryTxt: { color: "#fff", fontSize: fsize.base, fontFamily: font.bold },
  secondaryBtn: { paddingVertical: spacing.sm, width: "100%", alignItems: "center" },
  secondaryTxt: { color: colors.brand, fontSize: fsize.base, fontFamily: font.medium },
  ghostBtn: { paddingVertical: spacing.sm, alignItems: "center" },
  ghostTxt: { color: colors.muted, fontSize: fsize.base, fontFamily: font.medium },
  err: { color: colors.error, fontSize: fsize.sm, fontFamily: font.medium, textAlign: "center" },
});
