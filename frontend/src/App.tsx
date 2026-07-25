import { useEffect, useState } from "react";
import { useAuth } from "./auth/AuthContext";
import { AppShell } from "./components/AppShell";
import { ConversationsPage } from "./pages/ConversationsPage";
import { ContactsPage } from "./pages/ContactsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { PropertiesPage } from "./pages/PropertiesPage";
import { SettingsPage } from "./pages/SettingsPage";
import { type AppPage, navigateToPage, pageFromPath, subscribeToPageChanges } from "./lib/appNavigation";

export function App() {
  const { isAuthenticated } = useAuth();
  const [page, setPage] = useState<AppPage>(() => pageFromPath(window.location.pathname));

  useEffect(() => {
    return subscribeToPageChanges(setPage);
  }, []);

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return (
    <AppShell
      activePage={page}
      onNavigate={(nextPage) => {
        navigateToPage(nextPage as AppPage);
      }}
    >
      {renderPage(page)}
    </AppShell>
  );
}

function renderPage(page: AppPage) {
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
