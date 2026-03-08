import type { CurrentUser } from "@/api/users";
import { AppShell } from "@/components/shared/AppShell";

type AppProps = {
  user: CurrentUser;
};

export default function App({ user }: AppProps) {
  return <AppShell user={user} />;
}
