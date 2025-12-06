"use client";

import { useWorkspacesList, useDeleteWorkspace } from "../hooks/useWorkspaces";
import { cn } from "@/lib/utils";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Folder, FolderPlus, Loader2, ChevronDown, ChevronRight, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { CreateWorkspaceDialog } from "./CreateWorkspaceDialog";
import { DeleteConfirmDialog } from "@/components/ui/delete-confirm-dialog";
import { useState } from "react";
import { toast } from "sonner";
import { ROUTES } from "@/lib/routes";

export function WorkspaceSidebar() {
  const { data: workspaces, isLoading } = useWorkspacesList();
  const { mutateAsync: deleteWorkspace, isPending: isDeleting } = useDeleteWorkspace();
  const pathname = usePathname();
  const router = useRouter();
  const [isExpanded, setIsExpanded] = useState(true);
  
  // Delete State
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const toggleExpand = () => setIsExpanded(!isExpanded);

  const handleDelete = async () => {
    if (!deleteId) return;
    try {
      await deleteWorkspace(deleteId);
      toast.success("Workspace deleted");
      
      // If deleted workspace is active, redirect to workspaces root
      if (pathname.startsWith(`/workspaces/${deleteId}`)) {
        router.push(ROUTES.workspaces);
      }
    } catch (error) {
      toast.error("Failed to delete workspace");
    } finally {
      setDeleteId(null);
    }
  };

  if (isLoading) {
    return (
      <div className="flex h-full w-full flex-col bg-muted/10 p-4">
        <div className="flex items-center gap-2 mb-4">
          <div className="h-6 w-6 rounded bg-muted animate-pulse" />
          <div className="h-4 w-24 rounded bg-muted animate-pulse" />
        </div>
        <div className="space-y-2">
            {[1, 2, 3].map((i) => (
                <div key={i} className="h-9 rounded bg-muted animate-pulse" />
            ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full w-full flex-col bg-muted/10">
      {/* Header / New Workspace */}
      <div className="flex items-center justify-between p-4 border-b">
        <h2 className="text-sm font-semibold tracking-tight">Workspaces</h2>
        <CreateWorkspaceDialog>
            <Button variant="ghost" size="icon" className="h-8 w-8">
                <FolderPlus className="h-4 w-4" />
                <span className="sr-only">New Workspace</span>
            </Button>
        </CreateWorkspaceDialog>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-2">
            <div className="flex items-center px-2 py-2">
                <Button variant="ghost" size="sm" className="h-6 w-6 p-0 mr-1" onClick={toggleExpand}>
                    {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                </Button>
                <span className="text-xs font-semibold text-muted-foreground uppercase">
                    Your Workspaces
                </span>
            </div>
            
            {isExpanded && (
                <div className="grid gap-1 px-2">
                    {workspaces?.map((ws) => {
                        const isActive = pathname.startsWith(`/workspaces/${ws.id}`);
                        return (
                            <div key={ws.id} className="group relative w-full flex items-center pr-9 rounded-md hover:bg-accent hover:text-accent-foreground transition-colors min-w-0">
                                <Link
                                    href={`/workspaces/${ws.id}`}
                                    className={cn(
                                        "flex-1 flex items-center gap-2 py-2 pl-3 text-sm font-medium min-w-0 overflow-hidden",
                                        isActive ? "text-accent-foreground" : "text-muted-foreground"
                                    )}
                                    title={ws.name}
                                >
                                    <Folder className={cn("h-4 w-4 shrink-0", isActive ? "fill-current" : "")} />
                                    <span className="truncate flex-1 min-w-0">{ws.name}</span>
                                </Link>
                                
                                {/* Delete Button (Visible on Hover) */}
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive hover:bg-destructive/10 z-10"
                                    onClick={(e) => {
                                        e.preventDefault();
                                        e.stopPropagation();
                                        setDeleteId(ws.id);
                                    }}
                                >
                                    <Trash2 className="h-3.5 w-3.5" />
                                    <span className="sr-only">Delete</span>
                                </Button>
                            </div>
                        );
                    })}
                    
                    {workspaces?.length === 0 && (
                        <div className="text-center py-8 text-sm text-muted-foreground">
                            No workspaces yet.
                        </div>
                    )}
                </div>
            )}
        </div>
      </ScrollArea>
      
      <DeleteConfirmDialog
        open={!!deleteId}
        onOpenChange={(open) => !open && setDeleteId(null)}
        onConfirm={handleDelete}
        title="Delete Workspace?"
        description="This action cannot be undone. All documents and conversations within this workspace will be permanently deleted."
        isDeleting={isDeleting}
      />
    </div>
  );
}
