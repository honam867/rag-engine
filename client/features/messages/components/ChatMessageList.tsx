import { MESSAGE_ROLES } from "@/lib/constants";
import { Message, Citation } from "../api/messages";
import { cn } from "@/lib/utils";
import { Bot, User, Loader2, FileText } from "lucide-react";
import { Fragment } from "react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

interface Props {
  messages: Message[];
  onCitationClick?: (citation: Citation) => void;
}

export function ChatMessageList({ messages, onCitationClick }: Props) {
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
        const sections = msg.metadata?.sections;

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
                "max-w-[85%] rounded-lg px-4 py-3 text-sm min-h-[44px] flex flex-col justify-center",
                isUser
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-foreground"
              )}
            >
              {isPending && !isUser && !msg.content ? (
                <div className="flex items-center gap-2">
                   <Loader2 className="h-4 w-4 animate-spin" />
                   <span className="text-xs opacity-70">Thinking...</span>
                </div>
              ) : (
                <div className="whitespace-pre-wrap leading-relaxed space-y-3">
                  {sections && sections.length > 0 ? (
                    sections.map((section, idx) => (
                      <div key={idx} className="relative">
                         <span>{section.text}</span>
                         {section.citations && section.citations.length > 0 && (
                            <span className="inline-flex gap-1 ml-1 align-super text-xs font-medium">
                              {section.citations.map((citation, cIdx) => {
                                const hasSource = Boolean(citation.document_id) && citation.segment_index !== null;
                                return (
                                  <TooltipProvider key={cIdx}>
                                    <Tooltip>
                                        <TooltipTrigger asChild>
                                            <button
                                            disabled={!hasSource}
                                            onClick={() => hasSource && onCitationClick?.(citation)}
                                            className={cn(
                                                "inline-flex items-center justify-center h-4 w-4 rounded-full border text-[10px] shadow-sm transition-colors",
                                                hasSource 
                                                    ? "bg-background border-border text-foreground hover:bg-primary hover:text-primary-foreground cursor-pointer" 
                                                    : "bg-muted border-transparent text-muted-foreground cursor-default opacity-50"
                                            )}
                                            >
                                            {/* Show segment_index + 1 if available, else show ? */}
                                            {citation.segment_index !== null && citation.segment_index !== undefined ? citation.segment_index + 1 : "?"}
                                            </button>
                                        </TooltipTrigger>
                                        <TooltipContent className="max-w-[300px] text-xs bg-popover text-popover-foreground border shadow-md p-2">
                                            {citation.snippet_preview || (hasSource ? "Click to view source" : "Source unavailable")}
                                        </TooltipContent>
                                    </Tooltip>
                                  </TooltipProvider>
                                );
                              })}
                            </span>
                         )}
                      </div>
                    ))
                  ) : (
                     <div className="whitespace-pre-wrap leading-relaxed">{msg.content}</div>
                  )}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
