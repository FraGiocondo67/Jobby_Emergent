import React, { useCallback, useMemo, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl, Alert, Platform } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { api } from "@/src/api";
import { colors, spacing, radius, font, fsize, shadow } from "@/src/theme";
import { ClientDeliveryQR } from "@/src/components/DeliveryConfirm";

export default function RichiesteTab() {
  const { user } = useAuth();
  return (user?.role === "provider" || user?.role === "business") ? <ProviderJobs /> : <CustomerRequests />;
}

function StatusPill({ status }: { status: string }) {
  const { t } = useLang();
  const map: Record<string, string> = { pending: colors.warning, matched: "#E07B39", confirmed: colors.blue, in_progress: colors.brand, completed: colors.success, booked: colors.brand, disputed: colors.error, cancelled: colors.muted, declined: colors.error, pubblicata: colors.warning, in_matching: "#E07B39", con_proposte: colors.blue, confermata: colors.success, in_corso: colors.brand, completata: colors.success, recensita: colors.muted, scaduta: colors.error, annullata: colors.muted, preventivo: colors.blue };
  const c = map[status] || colors.muted;
  const label = (t as any)(`status_${status}`) || status;
  return <View style={[styles.pill, { backgroundColor: c + "22" }]}><Text style={[styles.pillText, { color: c }]}>{label}</Text></View>;
}

function CustomerRequests() {
  const { lang, t } = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [missions, setMissions] = useState<any[]>([]);
  const [payments, setPayments] = useState<any[]>([]);
  const [bookings, setBookings] = useState<any[]>([]);
  const [bizReqs, setBizReqs] = useState<any[]>([]);
  const [richieste, setRichieste] = useState<any[]>([]);
  const [bsReqs, setBsReqs] = useState<any[]>([]);
  const [drvReqs, setDrvReqs] = useState<any[]>([]);
  const [artReqs, setArtReqs] = useState<any[]>([]);
  const [genReqs, setGenReqs] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<"all" | "active" | "completed">("active");
  const [sortDir, setSortDir] = useState<"newest" | "oldest">("newest");

  // BLOCCO 9: prima un solo Promise.all racchiudeva anche api.requests()/
  // api.bookings() — due endpoint MAI montati su questo backend (/requests
  // e /bookings appartengono a wallet.py/bookings.py, ritirati nel Blocco
  // 5). Bastava che uno dei due fallisse (sempre, con 404) perché l'intero
  // Promise.all rigettasse e il catch esterno ingoiasse TUTTO, comprese le
  // 4 verticali funzionanti — "Le mie richieste" poteva restare vuota anche
  // per pulizie/babysitting/driver/artigiani a seconda dei tempi di rete.
  // Promise.allSettled isola ogni fetch: una fallisce, le altre restano.
  const load = useCallback(async () => {
    const [r, b, br, rq, bs, dr, art, gen] = await Promise.allSettled([
      api.requests(), api.bookings(), api.businessRequests(), api.myRichieste(),
      api.bsMyRichieste(), api.drvMyRichieste(), api.artMyRichieste(), api.myGenericRequests(),
    ]);
    if (r.status === "fulfilled") { setMissions((r.value.missions || []).filter((m: any) => m.status !== "booked")); setPayments(r.value.payments || []); }
    if (b.status === "fulfilled") setBookings(b.value || []);
    if (br.status === "fulfilled") setBizReqs(br.value || []);
    if (rq.status === "fulfilled") setRichieste(rq.value || []);
    if (bs.status === "fulfilled") setBsReqs(bs.value || []);
    if (dr.status === "fulfilled") setDrvReqs(dr.value || []);
    if (art.status === "fulfilled") setArtReqs(art.value || []);
    if (gen.status === "fulfilled") setGenReqs(gen.value || []);
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const merged = useMemo(() => {
    const list: any[] = [];
    missions.forEach((m) => list.push({ key: `m-${m.mission_id}`, type: "mission", created_at: m.created_at, status: m.status, data: m }));
    richieste.forEach((r) => list.push({ key: `rq-${r.richiesta_id}`, type: "pulizie", created_at: r.created_at, status: r.stato, data: r }));
    bsReqs.forEach((r) => list.push({ key: `bs-${r.richiesta_id}`, type: "babysitting", created_at: r.created_at, status: r.stato, data: r }));
    drvReqs.forEach((r) => list.push({ key: `drv-${r.richiesta_id}`, type: "driver", created_at: r.created_at, status: r.stato, data: r }));
    artReqs.forEach((r) => list.push({ key: `art-${r.richiesta_id}`, type: "artigiani", created_at: r.created_at, status: r.stato, data: r }));
    genReqs.forEach((r) => list.push({ key: `gen-${r.id}`, type: "generic", created_at: r.created_at, status: (r.brief_answers || {}).stato, data: r }));
    bizReqs.forEach((r) => list.push({ key: `b-${r.request_id}`, type: "biz", created_at: r.created_at, status: r.status, data: r }));
    bookings.forEach((b) => list.push({ key: `k-${b.booking_id}`, type: "booking", created_at: b.created_at, status: b.status, data: b }));
    payments.forEach((p) => list.push({ key: `p-${p.request_id}`, type: "payment", created_at: p.created_at, status: "completed", data: p }));
    const activeStatuses = ["pending", "matched", "confirmed", "in_progress", "booked", "pubblicata", "in_matching", "con_proposte", "confermata", "in_corso", "preventivo"];
    const phase = (s: string) => (activeStatuses.includes(s) ? "active" : "completed");
    let out = list;
    if (filter === "active") out = list.filter((x) => phase(x.status) === "active");
    else if (filter === "completed") out = list.filter((x) => phase(x.status) === "completed");
    return [...out].sort((a, b) => {
      const da = new Date(a.created_at || 0).getTime();
      const dbt = new Date(b.created_at || 0).getTime();
      return sortDir === "newest" ? dbt - da : da - dbt;
    });
  }, [missions, richieste, bsReqs, drvReqs, artReqs, genReqs, bizReqs, bookings, payments, filter, sortDir]);

  const empty = merged.length === 0;

  const openChat = async (otherId: string) => {
    try {
      const convos = await api.conversations();
      const c = convos.find((x: any) => x.other_id === otherId);
      if (c) router.push(`/chat/${c.conversation_id}`);
      else router.push("/(tabs)/chat");
    } catch {
      router.push("/(tabs)/chat");
    }
  };

  const confirmCancel = (fn: () => Promise<void>) => {
    if (Platform.OS === "web") {
      if (typeof window !== "undefined" && window.confirm(t("cancelRequest") + "?")) fn().catch(() => {});
      return;
    }
    Alert.alert(t("cancelRequest"), "", [
      { text: t("cancel"), style: "cancel" },
      { text: t("cancelRequest"), style: "destructive", onPress: () => { fn().catch(() => {}); } },
    ]);
  };
  const doCancelMission = (id: string) => confirmCancel(async () => { await api.cancelMission(id); load(); });
  const doCancelBiz = (id: string) => confirmCancel(async () => { await api.cancelBusinessRequest(id); load(); });
  const doCancelOrder = (id: string) => confirmCancel(async () => { await api.cancelOrder(id); load(); });
  const doCancelGeneric = (id: string) => confirmCancel(async () => { await api.cancelGenericRequest(id); load(); });

  const renderPulizie = (r: any) => (
    <Pressable key={`rq-${r.richiesta_id}`} testID={`req-pulizie-${r.richiesta_id}`} style={[styles.card, shadow.card]} onPress={() => router.push(`/pulizie/${r.richiesta_id}`)}>
      <Text style={{ fontSize: 26 }}>🧹</Text>
      <View style={{ flex: 1 }}>
        <Text style={styles.cardTitle}>{t("cleaning")} · {r.binario === "impresa" ? t("trackImpresa") : t("trackLF")}</Text>
        <Text style={styles.cardSub}>{r.config?.mq_band?.replace("_", "–")} m² · {r.config?.durata_ore}h · {(r.proposte || []).length} {t("proposalsLabel")}</Text>
        <View style={{ marginTop: 6 }}><StatusPill status={r.stato} /></View>
      </View>
      {r.prezzo_finale ? <Text style={styles.cardPrice}>€{r.prezzo_finale.toFixed(2)}</Text> : null}
    </Pressable>
  );

  const renderBabysitting = (r: any) => (
    <Pressable key={`bs-${r.richiesta_id}`} testID={`req-babysitting-${r.richiesta_id}`} style={[styles.card, shadow.card]} onPress={() => router.push(`/babysitting/${r.richiesta_id}`)}>
      <Text style={{ fontSize: 26 }}>🧸</Text>
      <View style={{ flex: 1 }}>
        <Text style={styles.cardTitle}>{t("babysitting")}{r.urgente ? " ⚡" : ""}</Text>
        <Text style={styles.cardSub}>{r.config?.durata_ore}h · {r.config?.n_bambini} 🧒 · {(r.proposte || []).length} {t("proposalsLabel")}</Text>
        <View style={{ marginTop: 6 }}><StatusPill status={r.stato} /></View>
      </View>
      {r.prezzo_finale ? <Text style={styles.cardPrice}>€{r.prezzo_finale.toFixed(2)}</Text> : null}
    </Pressable>
  );

  const renderDriver = (r: any) => {
    const isTaxi = r.config?.tipo === "taxi";
    return (
      <Pressable key={`drv-${r.richiesta_id}`} testID={`req-driver-${r.richiesta_id}`} style={[styles.card, shadow.card]} onPress={() => router.push(`/driver/${r.richiesta_id}`)}>
        <Text style={{ fontSize: 26 }}>{isTaxi ? "🚕" : "🚘"}</Text>
        <View style={{ flex: 1 }}>
          <Text style={styles.cardTitle} numberOfLines={1}>{r.partenza?.label} → {r.destinazione?.label}</Text>
          <Text style={styles.cardSub}>{r.config?.route?.distance_km} km · {(r.proposte || []).length} {t("proposalsLabel")}</Text>
          <View style={{ marginTop: 6 }}><StatusPill status={r.stato} /></View>
        </View>
        {r.prezzo_finale ? <Text style={styles.cardPrice}>€{r.prezzo_finale.toFixed(2)}</Text> : null}
      </Pressable>
    );
  };

  const renderArtigiani = (r: any) => {
    const m = r.config?.mestiere || "";
    const isDiag = r.config?.modalita === "diagnosi";
    return (
      <Pressable key={`art-${r.richiesta_id}`} testID={`req-artigiani-${r.richiesta_id}`} style={[styles.card, shadow.card]} onPress={() => router.push(`/artigiani/${r.richiesta_id}`)}>
        <Text style={{ fontSize: 26 }}>🔧</Text>
        <View style={{ flex: 1 }}>
          <Text style={styles.cardTitle} numberOfLines={1}>{m}{r.urgente ? " ⚡" : ""}</Text>
          <Text style={styles.cardSub}>{isDiag ? t("artDiagnosi") : t("artPaniere")} · {(r.proposte || []).length} {t("proposalsLabel")}</Text>
          <View style={{ marginTop: 6 }}><StatusPill status={r.stato} /></View>
        </View>
        {r.importo_totale ? <Text style={styles.cardPrice}>€{r.importo_totale.toFixed(2)}</Text> : null}
      </Pressable>
    );
  };

  const renderMission = (m: any) => (
    <Pressable key={`m-${m.mission_id}`} testID={`req-mission-${m.mission_id}`} style={[styles.card, shadow.card]} onPress={() => router.push(`/mission/radar?id=${m.mission_id}`)}>
      <Text style={{ fontSize: 26 }}>🔎</Text>
      <View style={{ flex: 1 }}>
        <Text style={styles.cardTitle}>{m.category}</Text>
        <Text style={styles.cardSub}>{m.date} · {m.time} · {m.accepted?.length || 0} {t("accepted")}</Text>
        {m.budget ? <Text style={styles.budgetSub}>💰 {t("budgetLabel")}: €{Number(m.budget).toFixed(0)}</Text> : null}
        <View style={{ marginTop: 6 }}><StatusPill status={m.status} /></View>
        {(m.status === "pending" || m.status === "matched") ? (
          <Pressable testID={`cancel-mission-${m.mission_id}`} style={styles.cancelBtn} onPress={() => doCancelMission(m.mission_id)}>
            <Text style={styles.cancelText}>✕ {t("cancelRequest")}</Text>
          </Pressable>
        ) : null}
      </View>
    </Pressable>
  );

  // BLOCCO 9: card per il flusso "a preventivo" delle 5 categorie senza
  // verticale dedicata (sarta/pet-sitting/hospitality/assistenza/tecnico).
  const renderGeneric = (r: any) => {
    const brief = r.brief_answers || {};
    const proposte = brief.proposte || [];
    return (
      <Pressable key={`gen-${r.id}`} testID={`req-generic-${r.id}`} style={[styles.card, shadow.card]} onPress={() => router.push(`/requests/${r.id}`)}>
        <Text style={{ fontSize: 26 }}>{r.category?.icon || "🧩"}</Text>
        <View style={{ flex: 1 }}>
          <Text style={styles.cardTitle}>{r.category?.name_it || r.title}</Text>
          <Text style={styles.cardSub}>{brief.note || ""} · {proposte.length} {t("proposalsLabel")}</Text>
          <View style={{ marginTop: 6 }}><StatusPill status={brief.stato} /></View>
          {brief.stato === "pubblicata" ? (
            <Pressable testID={`cancel-generic-${r.id}`} style={styles.cancelBtn} onPress={() => doCancelGeneric(r.id)}>
              <Text style={styles.cancelText}>✕ {t("cancelRequest")}</Text>
            </Pressable>
          ) : null}
        </View>
        {r.price_agreed ? <Text style={styles.cardPrice}>€{Number(r.price_agreed).toFixed(2)}</Text> : null}
      </Pressable>
    );
  };

  const renderBiz = (r: any) => (
    <View key={`b-${r.request_id}`} testID={`req-biz-${r.request_id}`} style={[styles.card, { flexDirection: "column", alignItems: "stretch" }, shadow.card]}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
        <Text style={{ fontSize: 26 }}>🏪</Text>
        <View style={{ flex: 1 }}>
          <Text style={styles.cardTitle}>{r.business_name}</Text>
          {r.order && r.items?.length ? (
            <>
              <Text style={styles.cardSub}>{r.category_label?.[lang] || r.category}</Text>
              {r.items.map((it: any, i: number) => (
                <Text key={i} style={styles.budgetSub}>{it.qty}× {it.descrizione} · €{Number(it.line_total).toFixed(2)}</Text>
              ))}
              <Text style={[styles.budgetSub, { color: colors.brand, fontFamily: font.bold }]}>🔒 €{Number(r.total).toFixed(2)} {t("heldInEscrow")}</Text>
            </>
          ) : (
            <Text style={styles.cardSub}>{r.category_label?.[lang] || r.category} · {r.note}</Text>
          )}
          {!r.order && r.budget ? <Text style={styles.budgetSub}>💰 {t("budgetLabel")}: €{Number(r.budget).toFixed(0)}</Text> : null}
          <View style={{ marginTop: 6 }}><StatusPill status={r.status} /></View>
        </View>
      </View>
      {r.status === "pending" ? (
        <Pressable testID={`cancel-biz-${r.request_id}`} style={[styles.cancelBtn, { alignSelf: "flex-start" }]} onPress={() => (r.order ? doCancelOrder(r.request_id) : doCancelBiz(r.request_id))}>
          <Text style={styles.cancelText}>✕ {t("cancelRequest")}</Text>
        </Pressable>
      ) : null}
      {r.status === "confirmed" && r.order && r.response ? (
        <>
          <Text style={styles.bizInfo}>
            {r.response.mode === "delivery" ? t("mode_delivery") : t("mode_pickup")} · {r.response.eta || "—"} · €{Number(r.total).toFixed(2)}
          </Text>
          <Pressable testID={`biz-chat-${r.request_id}`} style={styles.chatBtn} onPress={() => openChat(r.business_id)}>
            <Text style={styles.chatBtnText}>💬 {t("chat")}</Text>
          </Pressable>
        </>
      ) : null}
      {r.status === "confirmed" && !r.order && r.response ? (
        <>
          <Text style={styles.bizInfo}>
            {r.response.mode === "delivery" ? t("mode_delivery") : t("mode_pickup")} · {r.response.eta || "—"} · €{(r.response.price || 0).toFixed(2)}
            {r.response.delivery_cost ? ` + €${r.response.delivery_cost.toFixed(2)}` : ""}
          </Text>
          <Pressable testID={`biz-chat-${r.request_id}`} style={styles.chatBtn} onPress={() => openChat(r.business_id)}>
            <Text style={styles.chatBtnText}>💬 {t("chat")}</Text>
          </Pressable>
        </>
      ) : null}
      {r.conferma_pending ? <ClientDeliveryQR refId={r.request_id} /> : null}
    </View>
  );

  const renderBooking = (b: any) => (
    <Pressable key={`k-${b.booking_id}`} testID={`req-booking-${b.booking_id}`} style={[styles.card, shadow.card]} onPress={() => router.push(`/booking/${b.booking_id}`)}>
      <Text style={{ fontSize: 26 }}>🧾</Text>
      <View style={{ flex: 1 }}>
        <Text style={styles.cardTitle}>{b.provider_name}</Text>
        <Text style={styles.cardSub}>{b.category} · {b.date} · {b.time}</Text>
        <View style={{ marginTop: 6 }}><StatusPill status={b.status} /></View>
      </View>
      <Text style={styles.cardPrice}>€{b.total.toFixed(2)}</Text>
    </Pressable>
  );

  const renderPayment = (p: any) => (
    <View key={`p-${p.request_id}`} style={[styles.card, shadow.card]} testID={`req-payment-${p.request_id}`}>
      <Text style={{ fontSize: 26 }}>💳</Text>
      <View style={{ flex: 1 }}>
        <Text style={styles.cardTitle}>{p.label}</Text>
        <Text style={styles.cardSub}>{new Date(p.created_at).toLocaleDateString()}</Text>
        <View style={{ marginTop: 6 }}><StatusPill status="completed" /></View>
      </View>
      <Text style={styles.cardPrice}>€{p.amount.toFixed(2)}</Text>
    </View>
  );

  const FILTERS: { id: "all" | "active" | "completed"; key: any }[] = [
    { id: "all", key: "filterAll" }, { id: "active", key: "filterActive" }, { id: "completed", key: "filterCompleted" },
  ];

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}><Text style={styles.headerTitle}>{t("richieste")}</Text></View>
      <View style={styles.filterBar}>
        <View style={styles.filterChips}>
          {FILTERS.map((f) => (
            <Pressable key={f.id} testID={`filter-${f.id}`} style={[styles.chip, filter === f.id && styles.chipOn]} onPress={() => setFilter(f.id)}>
              <Text style={[styles.chipText, filter === f.id && styles.chipTextOn]}>{t(f.key)}</Text>
            </Pressable>
          ))}
        </View>
        <Pressable testID="sort-toggle" style={styles.sortBtn} onPress={() => setSortDir((s) => (s === "newest" ? "oldest" : "newest"))}>
          <Text style={styles.sortText}>{sortDir === "newest" ? "↓ " + t("sortNewest") : "↑ " + t("sortOldest")}</Text>
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 100 }} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />} showsVerticalScrollIndicator={false}>
        {empty ? (
          <View style={styles.empty}><Text style={{ fontSize: 40 }}>📋</Text><Text style={styles.emptyText}>{t("noRequests")}</Text></View>
        ) : null}

        {merged.map((item) =>
          item.type === "mission" ? renderMission(item.data)
            : item.type === "pulizie" ? renderPulizie(item.data)
            : item.type === "babysitting" ? renderBabysitting(item.data)
            : item.type === "driver" ? renderDriver(item.data)
            : item.type === "artigiani" ? renderArtigiani(item.data)
            : item.type === "generic" ? renderGeneric(item.data)
            : item.type === "biz" ? renderBiz(item.data)
            : item.type === "booking" ? renderBooking(item.data)
            : renderPayment(item.data)
        )}
      </ScrollView>
    </View>
  );
}

function ProviderJobs() {
  const { t } = useLang();
  const insets = useSafeAreaInsets();
  const [data, setData] = useState<any>(null);
  const [jobs, setJobs] = useState<any[]>([]);
  // BLOCCO 9: richieste "a preventivo" (sarta/pet-sitting/hospitality/
  // assistenza/tecnico) nelle categorie che il provider ha tra le skills —
  // separate da /provider/jobs (che copre solo le 4 verticali dedicate,
  // vedi richieste.py) perché usano un matching diverso (skills.contains,
  // non provider_invitati precalcolato).
  const [genAvailable, setGenAvailable] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<"active" | "completed">("active");
  const router = useRouter();

  const load = useCallback(async () => {
    const [e, j, ga] = await Promise.allSettled([api.earnings(), api.providerJobs(), api.availableGenericRequests()]);
    if (e.status === "fulfilled") setData(e.value);
    if (j.status === "fulfilled") setJobs(j.value || []);
    if (ga.status === "fulfilled") setGenAvailable(ga.value || []);
  }, []);
  useFocusEffect(useCallback(() => { load(); const iv = setInterval(load, 6000); return () => clearInterval(iv); }, [load]));

  const ACTIVE = ["pubblicata", "in_matching", "con_proposte", "preventivo", "confermata", "in_corso"];
  const shown = jobs.filter((j) => (filter === "active" ? ACTIVE.includes(j.stato) : ["completata", "recensita", "annullata"].includes(j.stato)));

  const emoji = (cat: string, cfg: any) => cat === "driver" ? (cfg?.tipo === "taxi" ? "🚕" : "🚘") : cat === "pulizie" ? "🧹" : cat === "babysitting" ? "🧸" : "🔧";
  const title = (j: any) => {
    if (j.cat === "driver") return `${j.partenza?.label || ""} → ${j.destinazione?.label || ""}`;
    if (j.cat === "pulizie") return `${t("cleaning")} · ${j.config?.durata_ore || ""}h`;
    if (j.cat === "babysitting") return `${t("babysitting")} · ${j.config?.n_bambini || ""}🧒`;
    return `${j.config?.mestiere || t("artigiani")}`;
  };
  const when = (j: any) => (j.data_ora || j.pickup_at || j.updated_at || "").toString().replace("T", " ").slice(0, 16);
  const price = (j: any) => j.prezzo_finale ?? j.importo_totale ?? null;

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}><Text style={styles.headerTitle}>{t("earnings")}</Text></View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 100 }} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />} showsVerticalScrollIndicator={false}>
        <View style={styles.earnHero}>
          <Text style={styles.earnLabel}>{t("totalEarned")}</Text>
          <Text style={styles.earnValue}>€{(data?.total_earned || 0).toFixed(2)}</Text>
          <View style={styles.earnStats}>
            <View style={styles.stat}><Text style={styles.statVal}>{data?.jobs_count || 0}</Text><Text style={styles.statLbl}>{t("jobs")}</Text></View>
            <View style={styles.stat}><Text style={styles.statVal}>{data?.completed_count || 0}</Text><Text style={styles.statLbl}>{t("completed")}</Text></View>
            <View style={styles.stat}><Text style={styles.statVal}>€{(data?.pending || 0).toFixed(0)}</Text><Text style={styles.statLbl}>{t("pending")}</Text></View>
          </View>
        </View>

        {genAvailable.length > 0 ? (
          <>
            <Text style={styles.sectionLabel}>{t("availableRequests")}</Text>
            {genAvailable.map((r: any) => (
              <Pressable key={`gen-av-${r.id}`} testID={`gen-available-${r.id}`} style={[styles.card, shadow.card]} onPress={() => router.push(`/requests/${r.id}` as any)}>
                <Text style={{ fontSize: 26 }}>{r.category?.icon || "🧩"}</Text>
                <View style={{ flex: 1 }}>
                  <Text style={styles.cardTitle} numberOfLines={1}>{r.category?.name_it || r.title}</Text>
                  <Text style={styles.cardSub}>{r.brief_answers?.note || ""}{r.my_proposal ? ` · ${t("proposalSent")}` : ""}</Text>
                </View>
                <Ionicons name="chevron-forward" size={18} color={colors.muted} />
              </Pressable>
            ))}
          </>
        ) : null}

        <View style={styles.jobFilter}>
          {(["active", "completed"] as const).map((f) => (
            <Pressable key={f} testID={`jobfilter-${f}`} style={[styles.chip, filter === f && styles.chipOn]} onPress={() => setFilter(f)}>
              <Text style={[styles.chipText, filter === f && styles.chipTextOn]}>{f === "active" ? t("filterActive") : t("filterCompleted")}</Text>
            </Pressable>
          ))}
        </View>

        {shown.length === 0 ? (
          <View style={styles.empty}><Text style={{ fontSize: 40 }}>☕</Text><Text style={styles.emptyText}>{filter === "active" ? t("noActiveJobs") : t("noRequests")}</Text></View>
        ) : shown.map((j) => (
          <Pressable key={`${j.cat}-${j.richiesta_id}`} testID={`job-${j.richiesta_id}`} style={[styles.card, shadow.card]} onPress={() => router.push(`/${j.cat}/${j.richiesta_id}` as any)}>
            <Text style={{ fontSize: 26 }}>{emoji(j.cat, j.config)}</Text>
            <View style={{ flex: 1 }}>
              <Text style={styles.cardTitle} numberOfLines={1}>{title(j)}{j.urgente ? " ⚡" : ""}</Text>
              <Text style={styles.cardSub}>{when(j)}{j.is_chosen ? ` · ${j.cliente_nome || t("clientLabel")}` : j.my_proposal ? ` · ${t("proposalSent")}` : ""}</Text>
              <View style={{ marginTop: 6 }}><StatusPill status={j.stato} /></View>
            </View>
            <View style={{ alignItems: "flex-end", gap: 4 }}>
              {price(j) != null ? <Text style={styles.cardPrice}>€{Number(price(j)).toFixed(2)}</Text> : null}
              <Ionicons name="chevron-forward" size={18} color={colors.muted} />
            </View>
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.divider },
  headerTitle: { fontSize: fsize["2xl"], fontFamily: font.bold, color: colors.onSurface },
  sectionLabel: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: spacing.sm, marginTop: spacing.sm },
  empty: { alignItems: "center", padding: spacing["3xl"], gap: spacing.md },
  emptyText: { fontSize: fsize.base, fontFamily: font.regular, color: colors.muted },
  card: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.lg, marginBottom: spacing.md, gap: spacing.md },
  cardTitle: { fontSize: fsize.lg, fontFamily: font.medium, color: colors.onSurface, textTransform: "capitalize" },
  cardSub: { fontSize: fsize.sm, fontFamily: font.regular, color: colors.muted, marginTop: 1 },
  budgetSub: { fontSize: fsize.sm, fontFamily: font.bold, color: colors.green, marginTop: 2 },
  cancelBtn: { marginTop: spacing.sm, alignSelf: "flex-start", paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.error },
  cancelText: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.error },
  filterBar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingVertical: spacing.md, backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.divider, gap: spacing.sm },
  filterChips: { flexDirection: "row", gap: spacing.sm, flex: 1 },
  chip: { paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  chipOn: { backgroundColor: colors.brand, borderColor: colors.brand },
  chipText: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.onSurfaceTertiary },
  chipTextOn: { color: "#fff" },
  sortBtn: { paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill, backgroundColor: colors.surfaceTertiary },
  sortText: { fontSize: fsize.sm, fontFamily: font.medium, color: colors.onSurface },
  cardPrice: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface },
  bizInfo: { fontSize: fsize.base, fontFamily: font.medium, color: colors.success, marginTop: spacing.md },
  chatBtn: { marginTop: spacing.md, alignSelf: "flex-start", backgroundColor: colors.purpleBg, paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, borderRadius: radius.pill },
  chatBtnText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.purple },
  pill: { alignSelf: "flex-start", paddingHorizontal: spacing.sm, paddingVertical: 3, borderRadius: radius.pill },
  pillText: { fontSize: fsize.sm, fontFamily: font.medium },
  earnHero: { backgroundColor: colors.brand, borderRadius: radius.lg, padding: spacing.xl, marginBottom: spacing.lg },
  hintCard: { backgroundColor: colors.brandTertiary, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.lg },
  hintCardText: { fontSize: fsize.base, fontFamily: font.medium, color: colors.onBrandTertiary, textAlign: "center" },
  jobFilter: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.md },
  earnLabel: { color: "rgba(255,255,255,0.85)", fontSize: fsize.base, fontFamily: font.regular },
  earnValue: { color: "#fff", fontSize: 40, fontFamily: font.bold, marginTop: 4 },
  earnStats: { flexDirection: "row", marginTop: spacing.lg, gap: spacing.lg },
  stat: { flex: 1 },
  statVal: { color: "#fff", fontSize: fsize.xl, fontFamily: font.medium },
  statLbl: { color: "rgba(255,255,255,0.8)", fontSize: fsize.sm, fontFamily: font.regular },
  sectionHdr: { fontSize: fsize.lg, fontFamily: font.bold, color: colors.onSurface, marginBottom: spacing.md, marginTop: spacing.sm },
});
