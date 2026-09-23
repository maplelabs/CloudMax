import { lazy, Suspense } from "react";
import { BrowserRouter as Router, Routes, Route, Navigate, useParams, useLocation, useNavigate } from "react-router-dom";
import { AppShell } from "./components/app-shell";
import { TimeRange } from "./components/time-range-selector";
import { ProtectedRoute } from "./components/protected-route";
import { AppProviders } from "./providers/AppProviders";
import { Toaster } from "./components/ui/sonner";
import { Alert } from "./types/alerts";
import { useTimeRangePersistence } from "./hooks/useTimeRangePersistence";

// Lazy loaded components
const Overview = lazy(() => import("./components/pages/overview").then(module => ({ default: module.Overview })));
const AlertsUnified = lazy(() => import("./components/pages/alerts-unified").then(module => ({ default: module.AlertsUnified })));
const AlertDetails = lazy(() => import("./components/pages/alert-details").then(module => ({ default: module.AlertDetails })));
const AlertGroupDetails = lazy(() => import("./components/pages/alert-group-details").then(module => ({ default: module.AlertGroupDetails })));
const Runbooks = lazy(() => import("./components/pages/runbooks").then(module => ({ default: module.Runbooks })));
const RunbookView = lazy(() => import("./components/pages/runbook-view").then(module => ({ default: module.RunbookView })));
const Setup = lazy(() => import("./components/pages/setup").then(module => ({ default: module.Setup })));
const Login = lazy(() => import("./components/pages/login").then(module => ({ default: module.Login })));
const Register = lazy(() => import("./components/pages/register").then(module => ({ default: module.Register })));
const Profile = lazy(() => import("./components/pages/profile").then(module => ({ default: module.Profile })));
const Users = lazy(() => import("./components/pages/users").then(module => ({ default: module.Users })));

// Import types for components that are lazy loaded
import type { LegacyRunbook } from "./components/pages/runbooks";

// Loading fallback component
function LoadingFallback() {
  return (
    <div className="flex items-center justify-center h-32">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900"></div>
    </div>
  );
}

// Route components
function AppWithRouter() {
  const { timeRange, customTimeRange, handleTimeRangeChange } = useTimeRangePersistence();

  return (
    <div className="min-h-screen">
      <Routes>
        <Route path="/login" element={
          <Suspense fallback={<LoadingFallback />}>
            <Login />
          </Suspense>
        } />
        <Route path="/register" element={
          <Suspense fallback={<LoadingFallback />}>
            <Register />
          </Suspense>
        } />
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <AppShell>
                <Suspense fallback={<LoadingFallback />}>
                  <Routes>
                    <Route
                      path="/"
                      element={<Navigate to="/overview" replace />}
                    />
                    <Route
                      path="/overview"
                      element={
                        <Overview
                          timeRange={timeRange}
                          onTimeRangeChange={handleTimeRangeChange}
                          customTimeRange={customTimeRange}
                        />
                      }
                    />
                    <Route path="/alerts" element={<AlertsRoute timeRange={timeRange} onTimeRangeChange={handleTimeRangeChange} customTimeRange={customTimeRange} />} />
                    <Route path="/alerts/:alertId" element={<AlertDetailsRoute />} />
                    <Route path="/alert-groups/:groupId" element={<AlertGroupDetailsRoute />} />
                    <Route path="/runbooks" element={<RunbooksRoute />} />
                    <Route path="/runbooks/:runbookId" element={<RunbookViewRoute />} />
                    <Route path="/setup" element={<Setup />} />
                    <Route path="/profile" element={<Profile />} />
                    <Route path="/users" element={<Users />} />
                  </Routes>
                </Suspense>
              </AppShell>
            </ProtectedRoute>
          }
        />
      </Routes>
      <Toaster />
    </div>
  );
}

// Route component for Alerts
function AlertsRoute({ timeRange, onTimeRangeChange, customTimeRange }: {
  timeRange: TimeRange;
  onTimeRangeChange: (range: TimeRange, customRange?: { start: Date; end: Date }) => void;
  customTimeRange: { start: Date; end: Date } | undefined;
}) {
  const navigate = useNavigate();

  const handleAlertClick = (alert: Alert) => {
    navigate(`/alerts/${alert.id}`, { state: { alert } });
  };

  const handleGroupClick = (groupId: number) => {
    navigate(`/alert-groups/${groupId}`);
  };

  return (
    <AlertsUnified
      timeRange={timeRange}
      onTimeRangeChange={onTimeRangeChange}
      customTimeRange={customTimeRange}
      onAlertClick={handleAlertClick}
      onGroupClick={handleGroupClick}
    />
  );
}

// Route component for Alert Details
function AlertDetailsRoute() {
  const { alertId } = useParams();
  const navigate = useNavigate();

  const handleBack = () => {
    navigate('/alerts');
  };

  return (
    <AlertDetails
      alertId={alertId ?? ""}
      onBack={handleBack}
      defaultTab={"alert-info"}
    />
  );
}

// Route component for Alert Group Details
function AlertGroupDetailsRoute() {
  return <AlertGroupDetails />;
}

// Route component for Runbooks
function RunbooksRoute() {
  const navigate = useNavigate();

  const handleViewRunbook = (runbook: LegacyRunbook) => {
    navigate(`/runbooks/${runbook.id}`, { state: { runbook } });
  };

  return <Runbooks onViewRunbook={handleViewRunbook} />;
}

// Route component for Runbook View
function RunbookViewRoute() {
  const navigate = useNavigate();
  const location = useLocation();
  
  const runbook = location.state?.runbook;
  
  const handleBack = () => {
    navigate('/runbooks');
  };

  if (!runbook) {
    return <Navigate to="/runbooks" replace />;
  }

  return <RunbookView runbook={runbook} onBack={handleBack} />;
}

export default function App() {
  return (
    <AppProviders>
      <Router>
        <AppWithRouter />
      </Router>
    </AppProviders>
  );
}