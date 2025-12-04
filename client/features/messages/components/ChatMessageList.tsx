import { MESSAGE_ROLES } from "@/lib/constants";
import { Message } from "../api/messages";
import { cn } from "@/lib/utils";
import { Bot, User, Loader2 } from "lucide-react";

export function ChatMessageList({ messages }: { messages: Message[] }) {
  if (!messages.length) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center h-64">
        <Bot className="h-12 w-12 text-muted-foreground mb-4" />
        <p className="text-sm text-muted-foreground">Start a conversation to ask questions about your documents.</p>
      </div>
    );
  }
  return (
    <div className="space-y-6 py-4">
      {messages.map((msg) => {
        const isUser = msg.role === MESSAGE_ROLES.user;
        const isPending = msg.status === "pending";

        return (
          <div
            key={msg.id}
            className={cn(
              "flex w-full items-start gap-3 transition-opacity duration-200",
              isUser ? "flex-row-reverse" : "flex-row",
              isUser && isPending ? "opacity-70" : "opacity-100"
            )}
          >
            <div
              className={cn(
                "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border",
                isUser ? "bg-primary text-primary-foreground border-primary" : "bg-muted border-border"
              )}
            >
              {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
            </div>
            
            <div
              className={cn(
                "max-w-[80%] rounded-lg px-4 py-3 text-sm min-h-[44px] flex items-center",
                isUser
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-foreground"
              )}
            >
              {isPending && !isUser ? (
                <div className="flex items-center gap-2">
                   <Loader2 className="h-4 w-4 animate-spin" />
                   <span className="text-xs opacity-70">Thinking...</span>
                </div>
              ) : (
                <div className="whitespace-pre-wrap leading-relaxed">{msg.content}</div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
