import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Index from './routes/Index';
import KioskSignUp from './routes/Kiosk/SignUp';
import KioskWelcome from './routes/Kiosk/Welcome';
import PhoneProfile from './routes/Phone/Profile';
import BoothTV from './routes/TV/BoothTV';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Index />} />
        <Route path="/kiosk" element={<KioskSignUp />} />
        <Route path="/kiosk/welcome" element={<KioskWelcome />} />
        <Route path="/p/:agentId" element={<PhoneProfile />} />
        <Route path="/tv" element={<BoothTV />} />
        <Route path="*" element={<div style={{ padding: 40 }}>404 — surface not found</div>} />
      </Routes>
    </BrowserRouter>
  );
}
