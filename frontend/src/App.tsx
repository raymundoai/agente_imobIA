import { useState } from "react";
import { useAuth } from "./auth/AuthContext";
import { AppShell } from "./components/AppShell";
import { ConversationDetailPage } from "./pages/ConversationDetailPage";
import { ConversationsPage } from "./pages/ConversationsPage";
import { ContactsPage } from "./pages/ContactsPage";
import { CapturePage } from "./pages/CapturePage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { PropertiesPage } from "./pages/PropertiesPage";
import { SettingsPage } from "./pages/SettingsPage";

export function App() {
  const { isAuthenticated } = useAuth();
  const [page, setPage] = useState("dashboard");
  const [conversationId, setConversationId] = useState<string | null>(null);

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  const activePage = conversationId ? "conversations" : page;

  return (
    <AppShell
      activePage={activePage}
      onNavigate={(nextPage) => {
        setConversationId(null);
        setPage(nextPage);
      }}
    >
      {conversationId ? (
        <ConversationDetailPage id={conversationId} onBack={() => setConversationId(null)} />
      ) : (
        renderPage(page)
      )}
    </AppShell>
  );
}

function renderPage(page: string) {
  switch (page) {
    case "capture":
      return <CapturePage />;
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
