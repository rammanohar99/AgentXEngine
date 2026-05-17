import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ChatPage } from "@/pages/ChatPage";
import "./index.css";

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("Root element not found");

createRoot(rootElement).render(
  <StrictMode>
    <ChatPage />
  </StrictMode>,
);
