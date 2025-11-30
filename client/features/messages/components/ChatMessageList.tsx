import { MESSAGE_ROLES } from "@/lib/constants";
import { Message } from "../api/messages";
import { cn } from "@/lib/utils";
import { Bot, User } from "lucide-react";

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
        return (
          <div
            key={msg.id}
            className={cn(
              "flex w-full items-start gap-3",
              isUser ? "flex-row-reverse" : "flex-row"
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
                "max-w-[80%] rounded-lg px-4 py-3 text-sm",
                isUser
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-foreground"
              )}
            >
              <div className="whitespace-pre-wrap leading-relaxed">{msg.content}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
