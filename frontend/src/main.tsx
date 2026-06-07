import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./index.css";
import App from "./App.tsx";
import { ErrorBoundary } from "./components/ErrorBoundary.tsx";
import { initTheme } from "./theme.ts";

initTheme();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      // This is a live trading dashboard. When the browser tab regains focus,
      // refresh stale broker data instead of leaving the user on a cached view.
      refetchOnWindowFocus: true,
      // Keep the short polling queries alive even if the user temporarily
      // switches browser tabs, so pending orders/positions stay current.
      refetchIntervalInBackground: true,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ErrorBoundary>
          <App />
        </ErrorBoundary>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
