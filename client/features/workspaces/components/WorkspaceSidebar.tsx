"use client";

import { useWorkspacesList } from "../hooks/useWorkspaces";
import { cn } from "@/lib/utils";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Folder, FolderPlus, Loader2, ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { CreateWorkspaceDialog } from "./CreateWorkspaceDialog";
import { useState } from "react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

export function WorkspaceSidebar() {
  const { data: workspaces, isLoading } = useWorkspacesList();
  const pathname = usePathname();
  const [isExpanded, setIsExpanded] = useState(true);

  const toggleExpand = () => setIsExpanded(!isExpanded);

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
                            <Link
                                key={ws.id}
                                href={`/workspaces/${ws.id}`}
                                className={cn(
                                    "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors",
                                    isActive ? "bg-accent text-accent-foreground" : "text-muted-foreground"
                                )}
                            >
                                <Folder className={cn("h-4 w-4", isActive ? "fill-current" : "")} />
                                <span className="truncate">{ws.name}</span>
                            </Link>
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
      
      {/* User profile or footer could go here */}
    </div>
  );
}
