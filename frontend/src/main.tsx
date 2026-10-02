import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import App from "./App";
import { AuthProvider } from "./auth";
import { ServerGate } from "./components/ServerGate";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ServerGate>
      <AuthProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </AuthProvider>
    </ServerGate>
  </StrictMode>,
);
