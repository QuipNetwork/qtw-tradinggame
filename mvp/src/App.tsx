import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import ErrorBoundary from './components/ErrorBoundary';
import KioskGate from './routes/Kiosk/KioskGate';
import TeamGate from './routes/Team/TeamGate';

// Routes are code-split so each surface ships its own chunk — the QR-opened
// phone profile no longer downloads the kiosk QR generator or the TV states.
const Landing = lazy(() => import('./routes/Public/Landing'));
const TeamDirectory = lazy(() => import('./routes/Team/Directory'));
const KioskSignUp = lazy(() => import('./routes/Kiosk/SignUp'));
const KioskWelcome = lazy(() => import('./routes/Kiosk/Welcome'));
const PhoneProfile = lazy(() => import('./routes/Phone/Profile'));
const BoothTV = lazy(() => import('./routes/TV/BoothTV'));

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Suspense fallback={<div className="route-fallback" aria-busy="true" />}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/team" element={<TeamGate><TeamDirectory /></TeamGate>} />
            <Route path="/kiosk" element={<KioskGate><KioskSignUp /></KioskGate>} />
            <Route path="/kiosk/welcome" element={<KioskWelcome />} />
            <Route path="/p/:agentId" element={<PhoneProfile />} />
            <Route path="/tv" element={<BoothTV />} />
            <Route path="*" element={<div style={{ padding: 40 }}>404 — surface not found</div>} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
