import { Workspace } from "../api/workspaces";
import Link from "next/link";
import { ROUTES } from "@/lib/routes";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

interface Props {
  workspaces: Workspace[];
}

export function WorkspaceList({ workspaces }: Props) {
  if (!workspaces.length) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center border rounded-lg border-dashed">
        <p className="text-sm text-muted-foreground">No workspaces yet. Create one to get started.</p>
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      {workspaces.map((ws) => (
        <Link key={ws.id} href={ROUTES.workspaceDetail(ws.id)} className="block group">
          <Card className="h-full transition-colors hover:bg-muted/50 hover:border-primary/50">
            <CardHeader>
              <CardTitle className="text-lg group-hover:text-primary transition-colors">
                {ws.name}
              </CardTitle>
              {ws.description && (
                <CardDescription className="line-clamp-2">
                  {ws.description}
                </CardDescription>
              )}
            </CardHeader>
            {/* Optional: Add usage stats or dates here later */}
          </Card>
        </Link>
      ))}
    </div>
  );
}
