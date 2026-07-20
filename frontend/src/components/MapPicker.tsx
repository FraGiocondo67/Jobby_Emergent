import React, { useEffect, useMemo, useRef, useState } from "react";
import { View, Text, StyleSheet, Modal, Pressable, Platform } from "react-native";
import { WebView } from "react-native-webview";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors, spacing, font, fsize } from "@/src/theme";
import { Button } from "@/src/components/UI";

type Props = {
  visible: boolean;
  center?: { lat: number; lng: number };
  title?: string;
  hint?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onCancel: () => void;
  onPick: (coord: { lat: number; lng: number }) => void;
};

const DEFAULT = { lat: 45.6669, lng: 12.2433 };

/**
 * Interactive map: tap anywhere to drop a pin, then confirm.
 * Works on native (WebView + postMessage) and web (iframe + window message).
 */
export default function MapPicker({ visible, center, title, hint, confirmLabel, cancelLabel, onCancel, onPick }: Props) {
  const insets = useSafeAreaInsets();
  const c = center && center.lat ? center : DEFAULT;
  const [picked, setPicked] = useState<{ lat: number; lng: number } | null>(null);
  const iframeRef = useRef<any>(null);

  useEffect(() => { if (visible) setPicked(null); }, [visible]);

  const html = useMemo(() => `<!DOCTYPE html><html><head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body,#map{height:100%;width:100%;margin:0;padding:0;background:#E9EEE9;}
.pin{width:34px;height:34px;display:flex;align-items:center;justify-content:center;font-size:28px;}</style>
</head><body><div id="map"></div><script>
var map=L.map('map',{zoomControl:true,attributionControl:false}).setView([${c.lat},${c.lng}],14);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19}).addTo(map);
var marker=null;
function send(lat,lng){var msg=JSON.stringify({lat:lat,lng:lng});
 if(window.ReactNativeWebView){window.ReactNativeWebView.postMessage(msg);}
 else if(window.parent){window.parent.postMessage(msg,'*');}}
var pinIcon=L.divIcon({className:'',html:'<div class="pin">📍</div>',iconSize:[34,34],iconAnchor:[17,32]});
map.on('click',function(e){
 if(marker){marker.setLatLng(e.latlng);}else{marker=L.marker(e.latlng,{icon:pinIcon}).addTo(map);}
 send(e.latlng.lat,e.latlng.lng);});
</script></body></html>`, [c.lat, c.lng]);

  useEffect(() => {
    if (Platform.OS !== "web" || !visible) return;
    const handler = (ev: any) => {
      try {
        const d = typeof ev.data === "string" ? JSON.parse(ev.data) : ev.data;
        if (d && typeof d.lat === "number") setPicked({ lat: d.lat, lng: d.lng });
      } catch {}
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, [visible]);

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onCancel}>
      <View style={styles.container}>
        <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
          <Text style={styles.title}>{title || "Segna sulla mappa"}</Text>
          <Pressable testID="mp-close" onPress={onCancel} hitSlop={12}><Text style={styles.close}>✕</Text></Pressable>
        </View>
        <Text style={styles.hint}>{hint || "Tocca la mappa per posizionare il punto"}</Text>
        <View style={{ flex: 1 }}>
          {Platform.OS === "web"
            ? React.createElement("iframe", { ref: iframeRef, srcDoc: html, style: { border: "none", width: "100%", height: "100%" } })
            : (
              <WebView
                originWhitelist={["*"]}
                source={{ html }}
                javaScriptEnabled
                domStorageEnabled
                onMessage={(e) => { try { const d = JSON.parse(e.nativeEvent.data); if (typeof d.lat === "number") setPicked({ lat: d.lat, lng: d.lng }); } catch {} }}
                {...(Platform.OS === "android" ? { androidLayerType: "hardware" as const } : {})}
              />
            )}
        </View>
        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          {picked ? <Text style={styles.picked}>📍 {picked.lat.toFixed(5)}, {picked.lng.toFixed(5)}</Text> : null}
          <Button testID="mp-confirm" label={confirmLabel || "Conferma posizione"} disabled={!picked} onPress={() => picked && onPick(picked)} />
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  title: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  close: { fontSize: 22, color: colors.onSurface },
  hint: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  footer: { paddingHorizontal: spacing.lg, paddingTop: spacing.md, backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderTopColor: colors.divider, gap: spacing.sm },
  picked: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.success, textAlign: "center" },
});
