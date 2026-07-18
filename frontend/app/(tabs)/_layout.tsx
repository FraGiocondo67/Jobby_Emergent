import React from "react";
import { Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "@/src/context/AuthContext";
import { useLang } from "@/src/context/LanguageContext";
import { colors, font, fsize } from "@/src/theme";

export default function TabsLayout() {
  const { user } = useAuth();
  const { t } = useLang();
  const isProvider = user?.role === "provider";

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.brand,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: {
          backgroundColor: colors.surfaceSecondary,
          borderTopColor: colors.border,
          height: 84,
          paddingTop: 8,
          paddingBottom: 28,
        },
        tabBarLabelStyle: { fontFamily: font.medium, fontSize: fsize.sm },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: isProvider ? t("missions") : t("home"),
          tabBarIcon: ({ color, size }) => (
            <Ionicons name={isProvider ? "flash" : "home"} size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="bookings"
        options={{
          title: isProvider ? t("earnings") : t("bookings"),
          tabBarIcon: ({ color, size }) => (
            <Ionicons name={isProvider ? "wallet" : "calendar"} size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: t("profile"),
          tabBarIcon: ({ color, size }) => <Ionicons name="person" size={size} color={color} />,
        }}
      />
    </Tabs>
  );
}
