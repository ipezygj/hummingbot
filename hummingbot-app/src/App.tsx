import { Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import { AppProvider } from "@/lib/AppContext";
import { Header } from "@/components/layout/Header";
import { Sidebar } from "@/components/layout/Sidebar";
import { Dashboard } from "@/components/pages/Dashboard";
import { Connectors } from "@/components/pages/Connectors";
import { Strategies } from "@/components/pages/Strategies";
import { Logs } from "@/components/pages/Logs";
import { Settings } from "@/components/pages/Settings";

function App() {
  return (
    <AppProvider>
      <div className="min-h-screen bg-background">
        <Header />
        <div className="flex">
          <Sidebar />
          <main className="flex-1 p-6 overflow-auto">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/connectors" element={<Connectors />} />
              <Route path="/strategies" element={<Strategies />} />
              <Route path="/logs" element={<Logs />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </main>
        </div>
        <Toaster position="bottom-right" />
      </div>
    </AppProvider>
  );
}

export default App;
