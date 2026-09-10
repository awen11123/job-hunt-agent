import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { HttpJobHuntApi } from "./api/client";
import "./styles.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("缺少应用挂载节点。");
}

const api = new HttpJobHuntApi(rootElement.dataset.sessionToken ?? "");

createRoot(rootElement).render(
  <StrictMode>
    <App api={api} />
  </StrictMode>,
);
