import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator } from "react-native";
import { Image } from "expo-image";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { Button, Stars } from "@/src/components/UI";

// Route a provider's request to the right configurator (best-effort by primary service).
const CFG_ROUTE: Record<string, string> = {
  pulizie: "/pulizie/configura",
  babysitting: "/babysitting/configura",
  driver: "/driver/configura",
  artigiani: "/artigiani/configura",
};

export default function ProviderDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { t, lang } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [p, setP] = useState<any>(null);
  const [products, setProducts] = useState<any[]>([]);
  const [cats, setCats] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [prof, catRes] = await Promise.all([api.providerPublic(id as string), api.categories()]);
        setP(prof);
        const all = [...(catRes.standard || []), ...(catRes.proximity || []), ...(catRes.payment || [])];
        const map: Record<string, any> = {};
        all.forEach((c: any) => { map[c.cat_id] = c.label; });
        setCats(map);
        if (prof.role === "business") {
          try { setProducts(await api.businessListino(id as string)); } catch {}
        }
      } catch {} finally { setLoading(false); }
    })();
  }, [id]);

  if (loading) return <View style={[styles.container, styles.center]}><ActivityIndicator color={colors.brand} /></View>;
  if (!p) return <View style={[styles.container, styles.center]}><Text style={styles.sub}>{t("error")}</Text></View>;

  const isBusiness = p.role === "business";
  const title = p.business_name || p.name;
  const catLabel = (c: string) => cats[c]?.[lang] || c;

  const request = () => {
    if (isBusiness) {
      // Prefer a category that actually has products, else the first service.
      const cat = products[0]?.category || p.services?.[0] || "";
      router.push(`/business-request/${id}?category=${cat}&name=${encodeURIComponent(title)}&label=${encodeURIComponent(catLabel(cat))}`);
    } else {
      const cat = (p.services || []).find((s: string) => CFG_ROUTE[s]) || p.services?.[0];
      const base = CFG_ROUTE[cat] || `/request/${cat}?type=service`;
      const sep = base.includes("?") ? "&" : "?";
      router.push(`${base}${sep}provider=${id}&providerName=${encodeURIComponent(title)}` as any);
    }
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="prov-back" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.primary} />
          <Text style={styles.backText}>Back</Text>
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 110 }} showsVerticalScrollIndicator={false}>
        {/* Profile header */}
        <View style={styles.profRow}>
          {p.picture ? (
            <Image source={{ uri: p.picture }} style={styles.avatar} contentFit="cover" />
          ) : (
            <View style={[styles.avatar, styles.avFallback, { backgroundColor: isBusiness ? colors.purple : colors.blue }]}>
              <Text style={styles.avInit}>{title[0]}</Text>
            </View>
          )}
          <View style={{ flex: 1 }}>
            <Text style={styles.name}>{title}</Text>
            <Text style={styles.sub}>{(p.services || []).map(catLabel).join(" · ")}</Text>
            <View style={styles.metaRow}>
              <Stars rating={p.rating} size={14} />
              <Text style={styles.rating}>{Number(p.rating).toFixed(1)}</Text>
              <Text style={styles.count}>({p.reviews_count} {t("reviewsLabel")})</Text>
            </View>
          </View>
        </View>

        <View style={styles.chipsRow}>
          <View style={[styles.statusPill, { backgroundColor: p.online ? "#E4F4E8" : "#F0F0F0" }]}>
            <View style={[styles.dot, { backgroundColor: p.online ? colors.success : colors.muted }]} />
            <Text style={[styles.statusText, { color: p.online ? colors.success : colors.muted }]}>{p.online ? t("active") : t("inactive")}</Text>
          </View>
          <Text style={styles.trust}>🛡️ {t("trustScore")} {Math.round(p.trust_score)}</Text>
          {p.verified ? <Text style={styles.verified}>✓ {t("verified")}</Text> : null}
        </View>

        {p.bio ? <Text style={styles.bio}>{p.bio}</Text> : null}
        {p.address ? <Text style={styles.address}>📍 {p.address}</Text> : null}

        {/* Products (business) */}
        {isBusiness ? (
          <View style={{ marginTop: spacing.xl }}>
            <Text style={styles.section}>🛒 {t("productsSection")}</Text>
            {products.length === 0 ? (
              <Text style={styles.sub}>{t("noListinoBusiness")}</Text>
            ) : (
              products.slice(0, 8).map((pr) => (
                <View key={pr.item_id} style={styles.prodRow} testID={`prof-prod-${pr.item_id}`}>
                  {pr.foto ? <Image source={{ uri: pr.foto }} style={styles.prodThumb} contentFit="cover" /> : <View style={[styles.prodThumb, styles.prodThumbFallback]}><Ionicons name="cube-outline" size={20} color={colors.muted} /></View>}
                  <View style={{ flex: 1 }}>
                    <Text style={styles.prodName}>{pr.descrizione}</Text>
                    <Text style={styles.prodMeta}>{t(`unit_${pr.unita}` as any)}</Text>
                  </View>
                  <Text style={styles.prodPrice}>€{Number(pr.prezzo).toFixed(2)}</Text>
                </View>
              ))
            )}
          </View>
        ) : null}

        {/* Reviews */}
        <View style={{ marginTop: spacing.xl }}>
          <Text style={styles.section}>⭐ {t("reviewsSection")} ({p.reviews_count})</Text>
          {(!p.reviews || p.reviews.length === 0) ? (
            <Text style={styles.sub}>{t("noReviews")}</Text>
          ) : (
            p.reviews.map((r: any, i: number) => (
              <View key={i} style={styles.reviewCard} testID={`review-${i}`}>
                <View style={styles.reviewTop}>
                  <Stars rating={r.rating} size={12} />
                  {r.categoria ? <Text style={styles.reviewCat}>{catLabel(r.categoria)}</Text> : null}
                </View>
                {r.comment ? <Text style={styles.reviewText}>{r.comment}</Text> : null}
                {r.reply ? <Text style={styles.reviewReply}>↳ {r.reply}</Text> : null}
              </View>
            ))
          )}
        </View>
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
        <Button testID="prov-request" label={isBusiness ? t("viewAndOrder") : t("requestService")} icon={isBusiness ? "cart" : "add"} onPress={request} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  center: { alignItems: "center", justifyContent: "center" },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  backBtn: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start" },
  backText: { color: colors.primary, fontSize: fsize.xl, fontFamily: font.medium },
  profRow: { flexDirection: "row", gap: spacing.md, alignItems: "center" },
  avatar: { width: 76, height: 76, borderRadius: 38 },
  avFallback: { alignItems: "center", justifyContent: "center" },
  avInit: { color: "#fff", fontSize: 30, fontFamily: font.bold },
  name: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface },
  sub: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: 2, textTransform: "capitalize" },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 6 },
  rating: { fontSize: fsize.base, fontFamily: font.bold, color: colors.onSurface },
  count: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted },
  chipsRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, marginTop: spacing.md, flexWrap: "wrap" },
  statusPill: { flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.pill },
  dot: { width: 8, height: 8, borderRadius: 4 },
  statusText: { fontSize: fsize.sm, fontFamily: font.medium },
  trust: { fontSize: fsize.base, fontFamily: font.medium, color: colors.brand },
  verified: { fontSize: fsize.base, fontFamily: font.medium, color: colors.success },
  bio: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurfaceTertiary, marginTop: spacing.md, lineHeight: 22 },
  address: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted, marginTop: spacing.sm },
  section: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface, marginBottom: spacing.md },
  prodRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.sm, borderWidth: 1, borderColor: colors.border },
  prodThumb: { width: 44, height: 44, borderRadius: radius.sm },
  prodThumbFallback: { backgroundColor: colors.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  prodName: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onSurface },
  prodMeta: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted },
  prodPrice: { fontSize: fsize.base, fontFamily: font.bold, color: colors.brand },
  reviewCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.sm, borderWidth: 1, borderColor: colors.border },
  reviewTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  reviewCat: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.muted, textTransform: "capitalize" },
  reviewText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.onSurface, marginTop: 6 },
  reviewReply: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.brand, marginTop: 4, fontStyle: "italic" },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.lg, paddingTop: spacing.md, backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderTopColor: colors.divider },
});
