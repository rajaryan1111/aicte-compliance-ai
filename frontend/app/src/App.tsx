import { Suspense, lazy } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { Layout } from "./components/Layout";
import { DashboardPage } from "./pages/DashboardPage";
import { ValidatePage } from "./pages/ValidatePage";
import { AboutPage } from "./pages/AboutPage";
import { PrivacyPage } from "./pages/PrivacyPage";
import { TermsPage } from "./pages/TermsPage";
import { HistoryPage } from "./pages/HistoryPage";
import { CadreCalculatorPage } from "./pages/CadreCalculatorPage";
import { SignInPage } from "./pages/SignInPage";
import { RequireAuth } from "./components/RequireAuth";

// The consistency workbench is code-split so it is downloaded only when a
// signed-in user opens the route.
const ConsistencyPage = lazy(() => import("./pages/ConsistencyPage"));

function RouteFallback() {
  return <p className="py-12 text-center text-sm text-text-secondary" role="status">Loading…</p>;
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/validate" element={<ValidatePage />} />
        <Route path="/cadre-calculator" element={<CadreCalculatorPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route path="/signin" element={<SignInPage />} />
        <Route path="/history" element={<RequireAuth><HistoryPage /></RequireAuth>} />
        <Route path="/history/:runId" element={<RequireAuth><HistoryPage /></RequireAuth>} />
        <Route
          path="/consistency"
          element={
            <RequireAuth>
              <Suspense fallback={<RouteFallback />}>
                <ConsistencyPage />
              </Suspense>
            </RequireAuth>
          }
        />
        <Route
          path="/consistency/:checkId"
          element={
            <RequireAuth>
              <Suspense fallback={<RouteFallback />}>
                <ConsistencyPage />
              </Suspense>
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
