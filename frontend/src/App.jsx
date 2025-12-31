import { BrowserRouter, Routes, Route } from "react-router-dom";
import MapView from "./components/MapView";
import AdminPanel from "./components/AdminPanel";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MapView />} />
        <Route path="/admin" element={<AdminPanel />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
