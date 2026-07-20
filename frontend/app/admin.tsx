import { Redirect } from "expo-router";

// Il pannello admin NON è più nell'app mobile: è un backoffice WEB separato
// (servito dal backend a /api/admin/ui, protetto da login + 2FA).
// Questa rotta reindirizza chiunque vi arrivi alla home.
export default function AdminRemoved() {
  return <Redirect href="/(tabs)" />;
}
