import type { JobHuntApi } from "./api/client";
import { AppShell } from "./components/AppShell";

interface AppProps {
  api: JobHuntApi;
}

export default function App({ api }: AppProps) {
  return <AppShell api={api} />;
}
