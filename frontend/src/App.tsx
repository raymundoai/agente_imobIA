import { useState } from "react";
import { useAuth } from "./auth/AuthContext";
import { AppShell } from "./components/AppShell";
import { ConversationsPage } from "./pages/ConversationsPage";
import { ContactsPage } from "./pages/ContactsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { PropertiesPage } from "./pages/PropertiesPage";
import { SettingsPage } from "./pages/SettingsPage";

export function App() {
  const { isAuthenticated } = useAuth();
  const [page, setPage] = useState("dashboard");

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return (
    <AppShell
      activePage={page}
      onNavigate={(nextPage) => {
        setPage(nextPage);
      }}
    >
      {renderPage(page)}
    </AppShell>
  );
}

function renderPage(page: string) {
  switch (page) {
    case "conversations":
      return <ConversationsPage />;
    case "contacts":
      return <ContactsPage />;
    case "properties":
      return <PropertiesPage />;
    case "settings":
      return <SettingsPage />;
    default:
      return <DashboardPage />;
  }
}
