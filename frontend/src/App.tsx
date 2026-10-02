import { useEffect, useState } from "react";
import { request } from "./api/client";
import type { BillingOverview, Tenant } from "./api/types";
import { useAuth } from "./auth/AuthContext";
import { getTokenClaims } from "./auth/tokenClaims";
import { AppShell } from "./components/AppShell";
import { TrialBanner } from "./components/TrialBanner";
import { ConversationsPage } from "./pages/ConversationsPage";
import { ContactsPage } from "./pages/ContactsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { InviteAcceptancePage } from "./pages/InviteAcceptancePage";
import { OnboardingWizard } from "./pages/OnboardingWizard";
import { PropertiesPage } from "./pages/PropertiesPage";
import { PropertySearchPage } from "./pages/PropertySearchPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SignupPage } from "./pages/SignupPage";
import { type AppPage, navigateToPage, pageFromPath, subscribeToPageChanges } from "./lib/appNavigation";

type PendingOnboarding = { tenant: Tenant; trialEndsAt: string | null };

export function App() {
  const { isAuthenticated, token } = useAuth();
  const [page, setPage] = useState<AppPage>(() => pageFromPath(window.location.pathname));
  const [onboarding, setOnboarding] = useState<PendingOnboarding | null>(null);

  useEffect(() => {
    return subscribeToPageChanges(setPage);
  }, []);

  const claims = getTokenClaims(token);
  const tenantId = claims?.tenantId;
  const isAdmin = claims?.role === "admin";

  useEffect(() => {
    setOnboarding(null);
    if (!isAuthenticated || !tenantId || !isAdmin) return;
    let cancelled = false;
    void request<Tenant>(`/tenants/${tenantId}`, {}, token)
      .then(async (tenant) => {
        const status = (tenant.settings.onboarding as { status?: string } | undefined)?.status;
        if (status !== "pending") return;
        const billing = await request<BillingOverview>("/billing", {}, token).catch(() => null);
        if (!cancelled) setOnboarding({ tenant, trialEndsAt: billing?.trial_ends_at ?? null });
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
    // Only re-check when the account changes, not on every token refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, tenantId, isAdmin]);

  if (window.location.pathname === "/aceitar-convite") {
    return <InviteAcceptancePage />;
  }

  if (!isAuthenticated) {
    return window.location.pathname === "/criar-conta" ? <SignupPage /> : <LoginPage />;
  }

  if (onboarding) {
    return (
      <OnboardingWizard
        onFinished={(_tenant, destination) => {
          setOnboarding(null);
          if (destination) {
            window.history.pushState({}, "", destination);
            window.dispatchEvent(new PopStateEvent("popstate"));
          }
        }}
        tenant={onboarding.tenant}
        token={token}
        trialEndsAt={onboarding.trialEndsAt}
      />
    );
  }

  return (
    <AppShell
      activePage={page}
      onNavigate={(nextPage) => {
        navigateToPage(nextPage as AppPage);
      }}
    >
      <TrialBanner />
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
    case "propertySearch":
      return <PropertySearchPage />;
    case "settings":
      return <SettingsPage />;
    default:
      return <DashboardPage />;
  }
}
