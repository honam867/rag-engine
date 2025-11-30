"use client";

import { useState } from "react";
import { useCreateConversation } from "../hooks/useConversations";
import { Card, CardContent, CardFooter, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loader2, MessageSquarePlus } from "lucide-react";

export function CreateConversationForm({ workspaceId }: { workspaceId: string }) {
  const { mutateAsync, isPending } = useCreateConversation(workspaceId);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setError("Title is required");
      return;
    }
    setError(null);
    await mutateAsync({ title: title.trim() });
    setTitle("");
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>New Chat</CardTitle>
        <CardDescription>Start a new conversation context.</CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit}>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label htmlFor="title" className="text-sm font-medium leading-none">
              Title
            </label>
            <Input
              id="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Q4 Financials"
              disabled={isPending}
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </CardContent>
        <CardFooter>
          <Button type="submit" className="w-full" disabled={isPending}>
            {isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <MessageSquarePlus className="mr-2 h-4 w-4" />}
            Create Chat
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
