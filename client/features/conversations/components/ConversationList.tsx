import Link from "next/link";
import { Conversation } from "../api/conversations";
import { ROUTES } from "@/lib/routes";
import { MessageSquare } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

interface Props {
  workspaceId: string;
  conversations: Conversation[];
}

export function ConversationList({ workspaceId, conversations }: Props) {
  if (!conversations.length) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center border border-dashed rounded-lg">
        <MessageSquare className="h-8 w-8 text-muted-foreground mb-2" />
        <p className="text-sm text-muted-foreground">No conversations started.</p>
      </div>
    );
  }
  return (
    <div className="grid gap-2">
      {conversations.map((conv) => (
        <Link
          key={conv.id}
          href={ROUTES.conversationDetail(workspaceId, conv.id)}
          className="block group"
        >
          <Card className="shadow-none border hover:bg-muted/30 transition-colors">
            <CardContent className="p-3 flex items-center gap-3">
              <MessageSquare className="h-4 w-4 text-primary" />
              <div className="text-sm font-medium group-hover:text-primary transition-colors">
                {conv.title || "Untitled Conversation"}
              </div>
            </CardContent>
          </Card>
        </Link>
      ))}
    </div>
  );
}
