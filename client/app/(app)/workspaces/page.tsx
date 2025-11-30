"use client";

import { CreateWorkspaceForm } from "@/features/workspaces/components/CreateWorkspaceForm";
import { WorkspaceList } from "@/features/workspaces/components/WorkspaceList";
import { useWorkspacesList } from "@/features/workspaces/hooks/useWorkspaces";
import { Loader2 } from "lucide-react";

export default function WorkspacesPage() {
  const { data, isLoading, isError } = useWorkspacesList();

  return (
    <div className="space-y-8 max-w-5xl mx-auto">
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-bold tracking-tight">Workspaces</h1>
        <p className="text-muted-foreground">
          Manage your knowledge bases and collections.
        </p>
      </div>

      <div className="grid gap-8 lg:grid-cols-[1fr_300px]">
        <div className="space-y-6">
          <div>
            <h2 className="text-lg font-semibold mb-4">Your Workspaces</h2>
            {isLoading && (
              <div className="flex justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            )}
            {isError && (
              <p className="text-sm text-destructive">Failed to load workspaces.</p>
            )}
            {data ? <WorkspaceList workspaces={data} /> : null}
          </div>
        </div>

        <div>
          <CreateWorkspaceForm />
        </div>
      </div>
    </div>
  );
}
