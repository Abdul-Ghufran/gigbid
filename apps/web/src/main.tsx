import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./lib/auth";
import { DegradedBanner } from "./components/DegradedBanner";
import { Loading } from "./components/ui";
import LoginPage from "./app/login/page";
import OnboardingPage from "./app/onboarding/page";
import InboxPage from "./app/inbox/page";
import JobDetailPage from "./app/jobs/[id]/page";
import StudioPage from "./app/studio/[id]/page";
import PipelinePage from "./app/pipeline/page";
import MessagesPage from "./app/messages/page";
import RunPage, { RunsListPage } from "./app/runs/[id]/page";
import AnalyticsPage from "./app/analytics/page";
import SettingsPage from "./app/settings/page";
import "./styles.css";

const NAV = [["/inbox", "Inbox"], ["/pipeline", "Pipeline"], ["/messages", "Messages"], ["/runs", "Runs"], ["/analytics", "Analytics"], ["/settings", "Settings"]];

function Shell({ children }: { children: React.ReactNode }) {
  const { user, signOut } = useAuth();
  return (
    <>
      <a href="#main" className="skip">Skip to content</a>
      <header className="topbar">
        <NavLink to="/inbox" className="brand" aria-label="GigBid home">GigBid</NavLink>
        <nav aria-label="Main"><ul>{NAV.map(([to, label]) => <li key={to}><NavLink to={to}>{label}</NavLink></li>)}</ul></nav>
        <div className="row gap small"><span className="muted hide-sm">{user?.display_name}</span><button className="btn btn-small" onClick={signOut}>Sign out</button></div>
      </header>
      <DegradedBanner />
      <div id="main">{children}</div>
    </>
  );
}

function Guard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" replace />;
  if (!user.onboarded && loc.pathname !== "/onboarding") return <Navigate to="/onboarding" replace />;
  return <Shell>{children}</Shell>;
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/onboarding" element={<Guard><OnboardingPage /></Guard>} />
      <Route path="/inbox" element={<Guard><InboxPage /></Guard>} />
      <Route path="/jobs/:id" element={<Guard><JobDetailPage /></Guard>} />
      <Route path="/studio/:id" element={<Guard><StudioPage /></Guard>} />
      <Route path="/pipeline" element={<Guard><PipelinePage /></Guard>} />
      <Route path="/messages" element={<Guard><MessagesPage /></Guard>} />
      <Route path="/messages/:thread" element={<Guard><MessagesPage /></Guard>} />
      <Route path="/runs" element={<Guard><RunsListPage /></Guard>} />
      <Route path="/runs/:id" element={<Guard><RunPage /></Guard>} />
      <Route path="/analytics" element={<Guard><AnalyticsPage /></Guard>} />
      <Route path="/settings" element={<Guard><SettingsPage /></Guard>} />
      <Route path="*" element={<Navigate to="/inbox" replace />} />
    </Routes>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><BrowserRouter><AuthProvider><App /></AuthProvider></BrowserRouter></React.StrictMode>,
);
