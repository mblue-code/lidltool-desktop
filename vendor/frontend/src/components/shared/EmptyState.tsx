import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";

type EmptyStateProps = {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: { label: string; href?: string; onClick?: () => void };
};

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
      {icon && <div className="text-muted-foreground">{icon}</div>}
      <h3 className="text-sm font-medium">{title}</h3>
      {description && <p className="max-w-sm text-sm text-muted-foreground">{description}</p>}
      {action && (
        action.href ? (
          <Button variant="outline" size="sm" asChild>
            <Link to={action.href}>{action.label}</Link>
          </Button>
        ) : action.onClick ? (
          <Button variant="outline" size="sm" onClick={action.onClick}>
            {action.label}
          </Button>
        ) : null
      )}
    </div>
  );
}
