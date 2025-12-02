"use client";

import { useWorkspacesList } from "@/features/workspaces/hooks/useWorkspaces";
import { Folder } from "lucide-react";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function WorkspacesPage() {
  const { data: workspaces, isLoading } = useWorkspacesList();
  const router = useRouter();

  useEffect(() => {
    if (workspaces && workspaces.length > 0) {
      router.replace(`/workspaces/${workspaces[0].id}`);
    }
  }, [workspaces, router]);

  if (isLoading) {
      return (
        <div className="flex items-center justify-center h-full">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        </div>
      );
  }

  return (
    <div className="flex flex-col items-center justify-center h-full text-muted-foreground p-8 text-center">
      <Folder className="h-16 w-16 mb-4 opacity-20" />
      <h2 className="text-xl font-medium mb-2">No Workspace Selected</h2>
      <p>Create a new workspace to get started.</p>
    </div>
  );
}