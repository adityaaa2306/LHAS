import { useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { HomeScreen } from '@/pages/HomeScreen';
import { MissionDetailPage } from '@/pages/MissionDetailPage';
// import { initializeEventBridge } from '@/services/eventBridge'; // Disabled - no WebSocket endpoint on backend
import './App.css'

function App() {
  useEffect(() => {
    // Initialize real-time event bridge on app load
    // NOTE: Disabled because backend doesn't implement /ws/events endpoint yet
    // App continues to work with REST API polling instead
    // initializeEventBridge().catch(error => {
    //   console.warn('Event bridge initialization failed, app will continue without real-time updates:', error);
    // });
  }, []);

  return (
    <Router>
      <Routes>
        <Route path="/" element={<HomeScreen />} />
        <Route path="/missions/:missionId" element={<MissionDetailPage />} />
      </Routes>
    </Router>
  );
}

export default App
