import { Bot, Database, ShieldCheck, Users } from "lucide-react";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const SECTIONS = [
  {
    title: "Connector management",
    description: "Install packs, check retailer auth state, and manage one-off sync surfaces.",
    to: "/connectors",
    icon: Database
  },
  {
    title: "AI assistant",
    description: "Adjust provider settings and desktop-safe assistant behavior.",
    to: "/settings/ai",
    icon: Bot
  },
  {
    title: "Users and access",
    description: "Review desktop-local users and session boundaries.",
    to: "/settings/users",
    icon: Users
  },
  {
    title: "Desktop posture",
    description: "Keep the packaged app local-first and aligned with the control center model.",
    to: "/setup",
    icon: ShieldCheck
  }
];

export function SettingsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        description="Keep operational controls off the main finance rail while leaving every desktop-specific surface one click away."
      />

      <div className="grid gap-4 xl:grid-cols-2">
        {SECTIONS.map((section) => (
          <Card key={section.title} className="app-dashboard-surface border-border/60">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <section.icon className="h-4 w-4" />
                {section.title}
              </CardTitle>
              <CardDescription>{section.description}</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="outline">
                <Link to={section.to}>Open</Link>
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
