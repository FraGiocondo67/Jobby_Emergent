import React, { useMemo } from "react";
import { View, StyleSheet, Platform } from "react-native";
import { WebView } from "react-native-webview";
import { radius as themeRadius, colors } from "@/src/theme";

export type MapMarker = {
  lat: number;
  lng: number;
  label?: string;
  emoji?: string;
  color?: string; // hex, defaults to brand orange
};

type Props = {
  center: { lat: number; lng: number };
  markers?: MapMarker[];
  radiusKm?: number; // draws a coverage circle around center
  height?: number | string;
  zoom?: number;
};

/**
 * Real interactive map using Leaflet + OpenStreetMap tiles inside a WebView.
 * Works on iOS, Android and web preview (no API key required).
 */
export default function RealMap({ center, markers = [], radiusKm, height = 240, zoom = 13 }: Props) {
  const html = useMemo(() => {
    const markersJson = JSON.stringify(markers);
    const circle = radiusKm
      ? `L.circle([${center.lat}, ${center.lng}], {radius: ${radiusKm * 1000}, color: '#4A7B59', weight: 1, fillColor: '#4A7B59', fillOpacity: 0.08}).addTo(map);`
      : "";
    return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html, body, #map { height: 100%; width: 100%; margin: 0; padding: 0; background: #E9EEE9; }
  .you-dot { width: 18px; height: 18px; background: #4A7B59; border: 3px solid #fff; border-radius: 50%; box-shadow: 0 0 0 6px rgba(74,123,89,0.2); }
  .prov-pin { display:flex; align-items:center; justify-content:center; width: 34px; height: 34px; background: #fff; border-radius: 50%; box-shadow: 0 2px 6px rgba(0,0,0,0.25); font-size: 18px; }
  .leaflet-popup-content { font-family: -apple-system, Roboto, sans-serif; font-size: 13px; }
</style>
</head>
<body>
<div id="map"></div>
<script>
  var map = L.map('map', { zoomControl: false, attributionControl: false }).setView([${center.lat}, ${center.lng}], ${zoom});
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);
  ${circle}
  var youIcon = L.divIcon({ className: '', html: '<div class="you-dot"></div>', iconSize: [18,18], iconAnchor: [9,9] });
  L.marker([${center.lat}, ${center.lng}], { icon: youIcon }).addTo(map);
  var markers = ${markersJson};
  var group = [[${center.lat}, ${center.lng}]];
  markers.forEach(function(m){
    var col = m.color || '#E07A3F';
    var html = '<div class="prov-pin" style="border:2.5px solid ' + col + '">' + (m.emoji || '📍') + '</div>';
    var icon = L.divIcon({ className: '', html: html, iconSize: [36,36], iconAnchor: [18,18] });
    var mk = L.marker([m.lat, m.lng], { icon: icon }).addTo(map);
    if (m.label) { mk.bindPopup(m.label); }
    group.push([m.lat, m.lng]);
  });
  if (group.length > 1) {
    try { map.fitBounds(group, { padding: [40,40], maxZoom: 15 }); } catch(e) {}
  }
</script>
</body>
</html>`;
  }, [center.lat, center.lng, markers, radiusKm, zoom]);

  return (
    <View style={[styles.wrap, { height: height as any }]} testID="real-map">
      {Platform.OS === "web" ? (
        // react-native-webview has no web build; use a native iframe (react-dom) instead.
        React.createElement("iframe", {
          srcDoc: html,
          style: { border: "none", width: "100%", height: "100%", background: "#E9EEE9" },
        })
      ) : (
        <WebView
          originWhitelist={["*"]}
          source={{ html }}
          style={styles.web}
          scrollEnabled={false}
          javaScriptEnabled
          domStorageEnabled
          {...(Platform.OS === "android" ? { androidLayerType: "hardware" as const } : {})}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    width: "100%",
    borderRadius: themeRadius.lg,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: "#E9EEE9",
  },
  web: { flex: 1, backgroundColor: "#E9EEE9" },
});
