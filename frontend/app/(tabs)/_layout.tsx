import React from "react";
import { Text } from "react-native";
import { Tabs } from "expo-router";
import { useLang } from "@/src/context/LanguageContext";
import { colors, font, fsize } from "@/src/theme";

function TabEmoji({ emoji, focused }: { emoji: string; focused: boolean }) {
  return <Text style={{ fontSize: 22, opacity: focused ? 1 : 0.55 }}>{emoji}</Text>;
}

export default function TabsLayout() {
  const { t } = useLang();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: {
          backgroundColor: colors.surfaceSecondary,
          borderTopColor: colors.border,
          height: 86,
          paddingTop: 8,
          paddingBottom: 28,
        },
        tabBarLabelStyle: { fontFamily: font.medium, fontSize: fsize.sm },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ title: t("home"), tabBarIcon: ({ focused }) => <TabEmoji emoji="🏠" focused={focused} /> }}
      />
      <Tabs.Screen
        name="richieste"
        options={{ title: t("richieste"), tabBarIcon: ({ focused }) => <TabEmoji emoji="📋" focused={focused} /> }}
      />
      <Tabs.Screen
        name="chat"
        options={{ title: t("chat"), tabBarIcon: ({ focused }) => <TabEmoji emoji="💬" focused={focused} /> }}
      />
      <Tabs.Screen
        name="profile"
        options={{ title: t("profile"), tabBarIcon: ({ focused }) => <TabEmoji emoji="👤" focused={focused} /> }}
      />
    </Tabs>
  );
}
